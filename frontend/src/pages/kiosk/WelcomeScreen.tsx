import { useEffect, useRef, useState, type FormEvent } from "react";
import { SuccessAnimation } from "../../components/kiosk/KioskAnimations";
import { KIOSK_TIMING, wait } from "../../config/kioskRuntime";
import { useTextToSpeech } from "../../hooks/useTextToSpeech";
import type { FaceRegistrationFields, KioskUser, WelcomeContext } from "../../types/kiosk";

export function welcomeMessage(user: KioskUser | null, context: WelcomeContext | null) {
  if (context === "new_enrollment" && user) return `Chào mừng ${user.full_name} lần đầu tiên đến với Trợ lý Thư viện AI`;
  if (context === "reenrollment" && user) return `Face ID của ${user.full_name} đã được đăng ký lại thành công.`;
  return user ? `Xin chào ${user.full_name}. Chào mừng bạn quay trở lại.` : "Xin chào bạn. Rất vui được gặp bạn.";
}

export default function WelcomeScreen({ user, welcomeContext, announce = true, frozenFrameUrl, onContinue, onSave, onReregister, onDeleteFaceId }: {
  user: KioskUser | null; frozenFrameUrl?: string | null; onContinue: () => void;
  welcomeContext: WelcomeContext | null; announce?: boolean;
  onSave: (fields: FaceRegistrationFields) => Promise<KioskUser>;
  onReregister: () => void; onDeleteFaceId: () => Promise<void>;
}) {
  const tts = useTextToSpeech();
  const started = useRef(false);
  const speakRef = useRef(tts.speak);
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState<FaceRegistrationFields>({ full_name: user?.full_name ?? "" });
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  speakRef.current = tts.speak;
  useEffect(() => {
    if (started.current || !announce) return;
    started.current = true;
    let active = true;
    void (async () => {
      await wait(KIOSK_TIMING.welcomeDisplayMs);
      if (!active) return;
      await speakRef.current(welcomeMessage(user, welcomeContext));
      await wait(KIOSK_TIMING.postSpeechSilenceMs);
    })();
    return () => { active = false; started.current = false; tts.stop(); };
  }, [announce, user, welcomeContext]);
  const beginEdit = () => {
    if (!user) return;
    setFields({ full_name: user.full_name, student_code: user.student_code ?? undefined, email: user.email ?? undefined,
      phone: user.phone ?? undefined, faculty: user.faculty ?? undefined, major: user.major ?? undefined,
      admission_year: user.admission_year ?? undefined });
    setStatus(""); setEditing(true);
  };
  const update = (name: keyof FaceRegistrationFields, value: string) => setFields(current => ({
    ...current, [name]: name === "admission_year" ? (value ? Number(value) : undefined) : value,
  }));
  const save = async (event: FormEvent) => {
    event.preventDefault();
    if (!fields.full_name.trim()) { setStatus("Vui lòng nhập họ và tên."); return; }
    setBusy(true); setStatus("");
    try { await onSave(fields); setEditing(false); setStatus("Đã lưu thông tin thành công."); }
    catch (reason) { setStatus(reason instanceof Error ? reason.message : "Không thể lưu thông tin."); }
    finally { setBusy(false); }
  };
  const removeFaceId = async () => {
    if (!window.confirm("Bạn có chắc muốn xóa Face ID? Thao tác này không tự động đăng ký lại.")) return;
    setBusy(true); setStatus("");
    try { await onDeleteFaceId(); }
    catch (reason) { setStatus(reason instanceof Error ? reason.message : "Không thể xóa Face ID."); setBusy(false); }
  };
  const reregister = () => {
    if (window.confirm("Bạn muốn đăng ký lại Face ID? Face ID hiện tại chỉ được thay thế sau khi đăng ký mới thành công.")) onReregister();
  };
  return <div className="welcome-experience">
    {frozenFrameUrl && <div className="welcome-frozen-frame"><img src={frozenFrameUrl} alt="Khung hình nhận diện thành công"/><div className="frozen-success-ring"><span>✓</span></div></div>}
    <div className="kiosk-center welcome-smile"><SuccessAnimation/>
    <span className="kiosk-kicker">NHẬN DIỆN THÀNH CÔNG</span>
    <h1>Xin chào</h1>
    <h2>{user?.full_name?.toLocaleUpperCase("vi-VN")}</h2>
    <p>{welcomeContext === "new_enrollment" ? `Chào mừng ${user?.full_name ?? "bạn"} lần đầu tiên đến với Trợ lý Thư viện AI`
      : welcomeContext === "reenrollment" ? "Face ID đã được đăng ký lại thành công."
      : "Chào mừng bạn quay trở lại."}</p>
    {editing ? <form className="welcome-profile-form" onSubmit={save}>
      <h3>Chỉnh sửa thông tin</h3>
      <div className="wizard-fields">
        <label>Họ và tên *<input required value={fields.full_name} onChange={e => update("full_name", e.target.value)}/></label>
        <label>Mã số sinh viên<input value={fields.student_code ?? ""} onChange={e => update("student_code", e.target.value)}/></label>
        <label>Email<input type="email" value={fields.email ?? ""} onChange={e => update("email", e.target.value)}/></label>
        <label>Số điện thoại<input value={fields.phone ?? ""} onChange={e => update("phone", e.target.value)}/></label>
        <label>Khoa<input value={fields.faculty ?? ""} onChange={e => update("faculty", e.target.value)}/></label>
        <label>Ngành học<input value={fields.major ?? ""} onChange={e => update("major", e.target.value)}/></label>
        <label>Năm nhập học<input type="number" min="1990" max="2100" value={fields.admission_year ?? ""} onChange={e => update("admission_year", e.target.value)}/></label>
      </div>
      {status && <div className="registration-error" role="alert">{status}</div>}
      <div className="registration-actions"><button disabled={busy}>Lưu</button><button type="button" className="kiosk-ghost" disabled={busy} onClick={() => { setEditing(false); setStatus(""); }}>Hủy</button></div>
    </form> : <>{user && <div className="student-card"><div className="student-avatar">{user.full_name.split(" ").at(-1)?.[0]}</div>
      <div><strong>{user.full_name}</strong><span>Mã số sinh viên: {user.student_code || "Chưa cập nhật"}</span></div><dl>
        <div><dt>Khoa</dt><dd>{user.faculty || "Chưa cập nhật"}</dd></div>
        <div><dt>Ngành</dt><dd>{user.major || "Chưa cập nhật"}</dd></div>
        <div><dt>Khóa tuyển sinh</dt><dd>{user.admission_year ?? "Chưa cập nhật"}</dd></div>
        <div><dt>Sinh viên năm</dt><dd>{user.student_year ?? "Chưa cập nhật"}</dd></div>
      </dl></div>}
    {status && <div className="profile-success" role="status">{status}</div>}
    <div className="registration-actions profile-actions"><button onClick={onContinue}>Tiếp tục</button><button className="kiosk-ghost" onClick={beginEdit}>Chỉnh sửa thông tin</button><button className="kiosk-ghost" onClick={reregister}>Đăng ký lại Face ID</button><button className="kiosk-danger" disabled={busy} onClick={removeFaceId}>Xóa Face ID</button></div></>}
    <small>{tts.notice ?? (tts.isSpeaking ? "Trợ lý đang chào bạn…" : "Chọn Tiếp tục khi thông tin đã chính xác")}</small>
    </div>
  </div>;
}
