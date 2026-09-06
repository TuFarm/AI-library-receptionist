import { useCallback, useEffect, useRef, useState } from "react";

type SpeechResultEventLike = Event & { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string; confidence: number } }> };
type SpeechErrorEventLike = Event & { error: string };
type SpeechRecognitionLike = {
  lang: string; continuous: boolean; interimResults: boolean; start: () => void; stop: () => void; abort: () => void;
  onresult: ((event: SpeechResultEventLike) => void) | null; onerror: ((event: SpeechErrorEventLike) => void) | null; onend: (() => void) | null;
};
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

export function useSpeechRecognition(onFinalTranscript?: (transcript: string, confidence?: number) => void) {
  const recognitionRef = useRef<SpeechRecognitionLike | null>(null);
  const listeningRef = useRef(false);
  const desiredRef = useRef(false);
  const generationRef = useRef(0);
  const restartRef = useRef<number | undefined>(undefined);
  const startRef = useRef<() => void>(() => undefined);
  const callbackRef = useRef(onFinalTranscript);
  const [transcript, setTranscript] = useState("");
  const [interimTranscript, setInterimTranscript] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [confidence, setConfidence] = useState<number>();
  const [error, setError] = useState<string | null>(null);
  callbackRef.current = onFinalTranscript;
  const speechWindow = window as Window & { SpeechRecognition?: SpeechRecognitionConstructor; webkitSpeechRecognition?: SpeechRecognitionConstructor };
  const Recognition = speechWindow.SpeechRecognition ?? speechWindow.webkitSpeechRecognition;
  const isSupported = Boolean(Recognition);

  const stopListening = useCallback(() => {
    desiredRef.current = false;
    generationRef.current++;
    window.clearTimeout(restartRef.current);
    listeningRef.current = false;
    recognitionRef.current?.abort();
    recognitionRef.current = null;
    setIsListening(false);
  }, []);
  const startListening = useCallback(() => {
    if (!Recognition) {
      setError("Trình duyệt hiện không hỗ trợ nhận dạng giọng nói. Vui lòng nhập câu hỏi bằng bàn phím.");
      return;
    }
    if (listeningRef.current) return;
    desiredRef.current = true;
    const generation = ++generationRef.current;
    listeningRef.current = true;
    setTranscript(""); setInterimTranscript(""); setError(null);
    const recognition = new Recognition();
    recognition.lang = "vi-VN"; recognition.continuous = false; recognition.interimResults = true;
    recognition.onresult = (event) => {
      if (generation !== generationRef.current) return;
      let finalText = ""; let interimText = ""; let finalConfidence: number | undefined;
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.isFinal) { finalText += result[0].transcript; finalConfidence = result[0].confidence; }
        else interimText += result[0].transcript;
      }
      setInterimTranscript(interimText);
      if (finalText.trim()) {
        const clean = finalText.trim();
        setTranscript(clean); setConfidence(finalConfidence); setInterimTranscript("");
        callbackRef.current?.(clean, finalConfidence);
      }
    };
    recognition.onerror = (event) => {
      if (generation !== generationRef.current) return;
      if (event.error === "no-speech") return;
      desiredRef.current = false;
      listeningRef.current = false;
      setIsListening(false);
      setError(event.error === "not-allowed"
        ? "Micro chưa được cấp quyền. Bạn vẫn có thể nhập câu hỏi bằng bàn phím."
        : "Không thể nhận dạng giọng nói. Vui lòng thử lại hoặc nhập câu hỏi.");
    };
    recognition.onend = () => {
      if (generation !== generationRef.current) return;
      listeningRef.current = false; setIsListening(false);
      if (desiredRef.current) restartRef.current = window.setTimeout(() => startRef.current(), 500);
    };
    recognitionRef.current = recognition;
    try { recognition.start(); setIsListening(true); } catch { listeningRef.current = false; setError("Micro đang bận. Vui lòng đợi một chút rồi thử lại."); }
  }, [Recognition]);
  startRef.current = startListening;
  useEffect(() => () => { desiredRef.current = false; generationRef.current++; window.clearTimeout(restartRef.current); recognitionRef.current?.abort(); }, []);
  return { startListening, stopListening, transcript, interimTranscript, isListening, isSupported, confidence, error };
}
