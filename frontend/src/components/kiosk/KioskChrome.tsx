import type { ReactNode } from "react";

const stateLabels: Record<string, string> = {
  IDLE: "SẴN SÀNG", PRESENCE_DETECTED: "XIN CHÀO", CAMERA_PREPARING: "CAMERA",
  WAKE_UP: "XIN CHÀO", FACE_TRACKING: "ĐANG NHẬN DIỆN", FACE_RECOGNIZING: "ĐANG NHẬN DIỆN",
  VERIFYING: "XÁC MINH", FACE_RECOGNIZED: "THÀNH CÔNG", GREETING: "CHÀO MỪNG", WELCOME: "CHÀO MỪNG", STOP_CAMERA: "CHÀO MỪNG", AI_GREETING: "TRỢ LÝ ĐANG NÓI",
  UNKNOWN_FACE: "KHÁCH MỚI", REGISTER: "ĐĂNG KÝ", REGISTER_PROCESSING: "ĐANG XỬ LÝ",
  REGISTER_SUCCESS: "HOÀN TẤT", VOICE_GREETING: "TRỢ LÝ ĐANG NÓI", VOICE_LISTENING: "ĐANG LẮNG NGHE",
  USER_SPEAKING: "ĐANG LẮNG NGHE", PROCESSING: "ĐANG SUY NGHĨ", AI_SPEAKING: "TRỢ LÝ ĐANG NÓI",
  LISTENING: "ĐANG LẮNG NGHE", SURVEY: "KHẢO SÁT", THANK_YOU: "CẢM ƠN", RETURN_IDLE: "TẠM BIỆT",
};

export function KioskChrome({ children, state, onExit }: { children: ReactNode; state: string; onExit?: () => void }) {
  return <section className={`kiosk-screen state-${state.toLowerCase()}`}>
    <header className="kiosk-top"><div className="kiosk-brand"><span>NL</span><div><strong>NLU Library</strong><small>Trợ lý lễ tân AI</small></div></div>
      <div className="kiosk-status" aria-live="polite"><i/> {stateLabels[state] ?? "ĐANG HOẠT ĐỘNG"}</div>
      {onExit && <button className="kiosk-exit" onClick={onExit}>Kết thúc</button>}
    </header>
    <div className="kiosk-content">{children}</div>
    <footer>NLU Library · Trợ lý AI luôn sẵn sàng hỗ trợ</footer>
  </section>;
}
