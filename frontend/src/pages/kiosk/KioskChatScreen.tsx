import { useEffect, useState, type FormEvent } from "react";
import { VoiceInputButton } from "../../components/kiosk/VoiceInputButton";
import { useKioskFlow } from "../../hooks/useKioskFlow";
import { useSpeechRecognition } from "../../hooks/useSpeechRecognition";
import ChatBubble from "../../components/kiosk/ChatBubble";

const quickQuestions = [
  "Thư viện mở cửa lúc mấy giờ?", "Wifi thư viện là gì?", "Khu vực học nhóm ở đâu?",
  "Tôi muốn tìm sách theo chủ đề", "Làm sao để liên hệ lễ tân?",
];

export default function KioskChatScreen({ flow }: { flow: ReturnType<typeof useKioskFlow> }) {
  const [input, setInput] = useState("");
  const speech = useSpeechRecognition((text, confidence) => { setInput(""); void flow.submitMessage(text, "VOICE", confidence); });

  useEffect(() => {
    if (!speech.isSupported) flow.setMicStatus("UNSUPPORTED");
    else if (speech.isListening) flow.setMicStatus("LISTENING");
    else if (speech.error?.includes("cấp quyền")) flow.setMicStatus("DENIED");
    else flow.setMicStatus("IDLE");
  }, [speech.isSupported, speech.isListening, speech.error, flow.setMicStatus]);

  async function send(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text) return;
    setInput("");
    await flow.submitMessage(text, "TEXT");
  }

  return <div className="kiosk-chat">
    <div className="chat-heading"><span className="assistant-avatar">✦</span><div>
      <span className="kiosk-kicker">TRỢ LÝ AI THƯ VIỆN</span><h1>Bạn muốn hỏi gì về thư viện?</h1>
    </div><button className="kiosk-ghost" onClick={flow.openBooks}>◇ Gợi ý sách</button></div>
    <div className="kiosk-chat-log" aria-live="polite">
      {flow.messages.map((message) => <ChatBubble key={message.id} message={message} icon="✦"/>)}
      {flow.isProcessing && <div className="kiosk-bubble assistant"><span>✦</span><p>Đang tìm câu trả lời…</p></div>}
    </div>
    <div className="kiosk-chips">{quickQuestions.map((question) =>
      <button key={question} onClick={() => { setInput(question); flow.touch(); }}>{question}</button>)}</div>
    {(speech.interimTranscript || speech.isListening) && <div className="speech-preview">
      <i/> {speech.interimTranscript || "Đang nghe… Hãy nói câu hỏi của bạn."}
    </div>}
    <form className="kiosk-input" onSubmit={send}>
      <VoiceInputButton isListening={speech.isListening} isProcessing={flow.isProcessing}
        disabled={!speech.isSupported} onStart={speech.startListening} onStop={speech.stopListening}/>
      <input value={input} onChange={(event) => { setInput(event.target.value); flow.touch(); }}
        placeholder="Nhập câu hỏi của bạn..." aria-label="Câu hỏi cho trợ lý thư viện"/>
      <button disabled={flow.isProcessing || !input.trim()}>Gửi câu hỏi ↑</button>
    </form>
    <div className="kiosk-chat-foot">
      <span>{!speech.isSupported
        ? "Trình duyệt hiện không hỗ trợ nhận dạng giọng nói. Bạn có thể nhập nội dung bằng bàn phím."
        : speech.error ?? (flow.mockFallbackActive ? "Đang dùng phản hồi dự phòng vì backend chưa sẵn sàng." : "Micro sử dụng nhận dạng giọng nói của trình duyệt.")}</span>
      <button className="text-action" onClick={flow.openSurvey}>Kết thúc & đánh giá →</button>
    </div>
  </div>;
}
