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
  const completeRef = useRef(onComplete);
  completeRef.current = onComplete;
  const message = welcomeMessage(user, welcomeContext);
  useEffect(() => {
    let active = true;
    const speech = Promise.race([tts.speak(message), wait(KIOSK_TIMING.registrationSpeechMaxMs)]);
    void Promise.all([speech, wait(KIOSK_TIMING.registrationSuccessMs)]).then(() => {
      if (active) completeRef.current();
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
