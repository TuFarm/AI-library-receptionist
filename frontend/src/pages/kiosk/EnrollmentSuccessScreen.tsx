import { useEffect, useRef } from "react";
import { SuccessAnimation } from "../../components/kiosk/KioskAnimations";
import { KIOSK_TIMING, wait } from "../../config/kioskRuntime";
import { useTextToSpeech } from "../../hooks/useTextToSpeech";
import type { KioskUser, WelcomeContext } from "../../types/kiosk";
import { welcomeMessage } from "./WelcomeScreen";

export default function EnrollmentSuccessScreen({ user, welcomeContext, onComplete }: {
  user: KioskUser | null; welcomeContext: WelcomeContext | null; onComplete: () => void;
}) {
  const tts = useTextToSpeech();
  const spoken = useRef(false);
  const message = welcomeMessage(user, welcomeContext);
  useEffect(() => {
    if (spoken.current) return;
    spoken.current = true;
    let active = true;
    void Promise.all([tts.speak(message), wait(KIOSK_TIMING.registrationSuccessMs)]).then(() => {
      if (active) onComplete();
    });
    return () => { active = false; tts.stop(); };
  }, [message]);
  return <div className="kiosk-center enrollment-success-screen">
    <SuccessAnimation/>
    <span className="kiosk-kicker">ĐĂNG KÝ FACE ID THÀNH CÔNG</span>
    <h1>{message}</h1>
    <p>{welcomeContext === "reenrollment" ? "Bạn có thể tiếp tục sử dụng trợ lý với Face ID mới." : "Hồ sơ của bạn đã sẵn sàng."}</p>
    <small>{tts.notice ?? (tts.isSpeaking ? "Trợ lý đang chào bạn…" : "Đang chuyển sang hồ sơ của bạn…")}</small>
  </div>;
}
