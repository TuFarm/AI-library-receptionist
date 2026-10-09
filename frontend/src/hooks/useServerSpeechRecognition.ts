import { useCallback, useEffect, useRef, useState } from "react";
import { MOCK_FALLBACK_ENABLED, voiceApi } from "../services/apiClient";

/** Voice input source: Web Speech in the browser, or recording + server STT where Web Speech is unavailable (e.g. Firefox). */
export type VoiceInputMode = "browser" | "server";

export function chooseVoiceInput(setting: string | undefined, env: { browserSpeech: boolean; mediaRecorder: boolean }): VoiceInputMode | null {
  const mode = (setting ?? "auto").toLowerCase();
  if (mode === "browser") return env.browserSpeech ? "browser" : null;
  if (mode === "server") return env.mediaRecorder ? "server" : null;
  if (env.browserSpeech) return "browser";
  return env.mediaRecorder ? "server" : null;
}

/** Tells the visitor where their voice goes before they speak. Neither mode keeps audio on the kiosk. */
export function voicePrivacyNotice(mode: VoiceInputMode | null, userAgent: string): string | null {
  if (mode === "server") return "Giọng nói của bạn được gửi qua máy chủ thư viện tới Google Gemini để chuyển thành chữ; thư viện không lưu bản ghi âm, chỉ lưu nội dung câu hỏi.";
  if (mode === "browser") {
    const service = /\bEdg\//.test(userAgent) ? "Microsoft" : "Google";
    return `Giọng nói của bạn được trình duyệt gửi tới dịch vụ nhận dạng của ${service} để chuyển thành chữ; thư viện chỉ lưu nội dung câu hỏi.`;
  }
  return null;
}

const SAMPLE_MS = 100;
const SPEECH_RMS = 0.035;        // level treated as speech
const SILENCE_AFTER_SPEECH_MS = 1200;
const MAX_UTTERANCE_MS = 15000;
const MAX_WAIT_FOR_SPEECH_MS = 10000;

/**
 * Records one utterance with MediaRecorder, ends it after a pause in speech, and sends it to
 * POST /voice/transcribe. Same surface as useSpeechRecognition so the voice screen can use either.
 * Audio goes to the backend only for transcription; it is not stored or sent over the WebSocket.
 */
export function useServerSpeechRecognition(onFinalTranscript?: (transcript: string, confidence?: number) => void) {
  const callbackRef = useRef(onFinalTranscript);
  callbackRef.current = onFinalTranscript;
  const desiredRef = useRef(false);
  const generationRef = useRef(0);
  const cleanupRef = useRef<() => void>(() => undefined);
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isSupported = typeof window !== "undefined" && typeof window.MediaRecorder !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);

  const stopListening = useCallback(() => {
    desiredRef.current = false;
    generationRef.current++;
    cleanupRef.current();
    setIsListening(false);
    setInterimTranscript("");
  }, []);

  const startListening = useCallback(async () => {
    if (!isSupported) { setError("Thiết bị không hỗ trợ ghi âm. Vui lòng nhập câu hỏi bằng bàn phím."); return; }
    if (desiredRef.current && isListening) return;
    desiredRef.current = true;
    const generation = ++generationRef.current;
    setError(null); setTranscript(""); setInterimTranscript("");
    let stream: MediaStream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } }); }
    catch { desiredRef.current = false; setError("Micro chưa được cấp quyền. Bạn vẫn có thể nhập câu hỏi bằng bàn phím."); return; }
    if (generation !== generationRef.current) { stream.getTracks().forEach((track) => track.stop()); return; }

    const context = new AudioContext();
    const analyser = context.createAnalyser(); analyser.fftSize = 1024;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const mimeType = MediaRecorder.isTypeSupported?.("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
    const recorder = new MediaRecorder(stream, { mimeType });
    const chunks: Blob[] = [];
    let heardSpeech = false; let lastSpeechAt = 0; const startedAt = performance.now();
    recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };

    const timer = window.setInterval(() => {
      analyser.getFloatTimeDomainData(samples);
      const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
      const now = performance.now();
      if (rms > SPEECH_RMS) { heardSpeech = true; lastSpeechAt = now; setInterimTranscript("Đang nghe…"); }
      const pauseEnded = heardSpeech && now - lastSpeechAt > SILENCE_AFTER_SPEECH_MS;
      const tooLong = now - startedAt > MAX_UTTERANCE_MS;
      const nobodySpoke = !heardSpeech && now - startedAt > MAX_WAIT_FOR_SPEECH_MS;
      if ((pauseEnded || tooLong || nobodySpoke) && recorder.state === "recording") recorder.stop();
    }, SAMPLE_MS);
    const release = () => { window.clearInterval(timer); stream.getTracks().forEach((track) => track.stop()); void context.close().catch(() => undefined); };
    cleanupRef.current = () => { recorder.onstop = null; if (recorder.state !== "inactive") recorder.stop(); release(); };

    recorder.onstop = async () => {
      release();
      if (generation !== generationRef.current) return;
      setIsListening(false);
      if (!heardSpeech) {  // silence: keep waiting while the screen still wants to listen
        if (desiredRef.current) void startRef.current();
        return;
      }
      setInterimTranscript("Đang nhận dạng…");
      try {
        const result = await voiceApi.transcribe(new Blob(chunks, { type: "audio/webm" }));
        if (generation !== generationRef.current) return;
        setInterimTranscript("");
        // A mock provider returns a canned sentence; never submit it as the visitor's question.
        if (result.provider === "mock" && !MOCK_FALLBACK_ENABLED) { desiredRef.current = false; setError("Máy chủ chưa bật nhận dạng giọng nói. Vui lòng nhập câu hỏi bằng bàn phím."); return; }
        if (!result.transcript.trim()) { setError("Chưa nghe rõ câu hỏi. Vui lòng nói lại hoặc nhập bằng bàn phím."); desiredRef.current = false; return; }
        setTranscript(result.transcript);
        callbackRef.current?.(result.transcript, result.confidence_score ?? undefined);
      } catch {
        if (generation !== generationRef.current) return;
        desiredRef.current = false; setInterimTranscript("");
        setError("Không thể nhận dạng giọng nói. Vui lòng thử lại hoặc nhập câu hỏi.");
      }
    };
    recorder.start(250);
    setIsListening(true);
  }, [isSupported, isListening]);
  const startRef = useRef(startListening);
  startRef.current = startListening;

  useEffect(() => () => { desiredRef.current = false; generationRef.current++; cleanupRef.current(); }, []);
  const start = useCallback(() => { void startListening(); }, [startListening]);
  return { startListening: start, stopListening, transcript, interimTranscript, isListening, isSupported, confidence: undefined as number | undefined, error };
}
