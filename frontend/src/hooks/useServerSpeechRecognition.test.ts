import { afterEach, describe, expect, it, vi } from "vitest";
import { chooseVoiceInput } from "./useServerSpeechRecognition";
import { voiceApi } from "../services/apiClient";

afterEach(() => { vi.unstubAllGlobals(); });

describe("voice input selection", () => {
  const browser = { browserSpeech: true, mediaRecorder: true, electron: false };
  const electron = { browserSpeech: true, mediaRecorder: true, electron: true };
  it("auto uses Web Speech in browsers and server STT in Electron", () => {
    expect(chooseVoiceInput(undefined, browser)).toBe("browser");
    expect(chooseVoiceInput("auto", electron)).toBe("server");
    expect(chooseVoiceInput("auto", { ...browser, browserSpeech: false })).toBe("server");
    expect(chooseVoiceInput("auto", { browserSpeech: false, mediaRecorder: false, electron: false })).toBeNull();
  });
  it("honours an explicit mode only when the device supports it", () => {
    expect(chooseVoiceInput("server", browser)).toBe("server");
    expect(chooseVoiceInput("BROWSER", electron)).toBe("browser");
    expect(chooseVoiceInput("server", { ...browser, mediaRecorder: false })).toBeNull();
    expect(chooseVoiceInput("browser", { ...browser, browserSpeech: false })).toBeNull();
  });
});

describe("server transcription request", () => {
  it("uploads one webm utterance with the device key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ success: true, data: { transcript: "Xin chào", provider: "gemini" } })));
    vi.stubGlobal("fetch", fetchMock);
    const result = await voiceApi.transcribe(new Blob([new Uint8Array([0x1a, 0x45, 0xdf, 0xa3])], { type: "audio/webm" }));
    expect(result.transcript).toBe("Xin chào");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/voice\/transcribe$/);
    const file = (options.body as FormData).get("audio_file") as File;
    expect(file.name).toBe("utterance.webm");
    expect(file.type).toBe("audio/webm");  // the backend allow-list has no codec suffix
  });
});
