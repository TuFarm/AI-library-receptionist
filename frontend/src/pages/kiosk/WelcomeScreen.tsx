import { useEffect, useRef } from "react";
import { SuccessAnimation } from "../../components/kiosk/KioskAnimations";
import { KIOSK_TIMING, wait } from "../../config/kioskRuntime";
import { useTextToSpeech } from "../../hooks/useTextToSpeech";
import type { KioskUser } from "../../types/kiosk";
export default function WelcomeScreen({ user, frozenFrameUrl, onContinue }: { user: KioskUser | null; frozenFrameUrl?: string | null; onContinue: () => void }) {
  const tts = useTextToSpeech();
  const started = useRef(false);
  const speakRef = useRef(tts.speak);
  speakRef.current = tts.speak;
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    let active = true;
    void (async () => {
      await wait(KIOSK_TIMING.welcomeDisplayMs);
      if (!active) return;
      await speakRef.current(user ? `Xin chào ${user.full_name}. Rất vui được gặp lại bạn.` : "Xin chào bạn. Rất vui được gặp bạn.");
      await wait(KIOSK_TIMING.postSpeechSilenceMs);
      if (active) onContinue();
    })();
    return () => { active = false; started.current = false; tts.stop(); };
  }, []);
  return <div className="welcome-experience">
    {frozenFrameUrl && <div className="welcome-frozen-frame"><img src={frozenFrameUrl} alt="Khung hình nhận diện thành công"/><div className="frozen-success-ring"><span>✓</span></div></div>}
    <div className="kiosk-center welcome-smile"><SuccessAnimation/>
    <span className="kiosk-kicker">NHẬN DIỆN THÀNH CÔNG</span>
    <h1>Xin chào</h1>
    <h2>{user?.full_name?.toLocaleUpperCase("vi-VN")}</h2>
    <p>Chào mừng bạn quay trở lại.</p>
    {user && <div className="student-card"><div className="student-avatar">{user.full_name.split(" ").at(-1)?.[0]}</div>
      <div><strong>{user.full_name}</strong><span>Mã số sinh viên: {user.student_code || "Chưa cập nhật"}</span></div><dl>
        <div><dt>Khoa</dt><dd>{user.faculty || "Chưa cập nhật"}</dd></div>
        <div><dt>Ngành</dt><dd>{user.major || "Chưa cập nhật"}</dd></div>
        <div><dt>Khóa tuyển sinh</dt><dd>{user.admission_year ?? "Chưa cập nhật"}</dd></div>
        <div><dt>Sinh viên năm</dt><dd>{user.student_year ?? "Chưa cập nhật"}</dd></div>
      </dl></div>}
    <small>{tts.notice ?? (tts.isSpeaking ? "Trợ lý đang chào bạn…" : "Tự động chuyển sang trò chuyện giọng nói")}</small>
    </div>
  </div>;
}
