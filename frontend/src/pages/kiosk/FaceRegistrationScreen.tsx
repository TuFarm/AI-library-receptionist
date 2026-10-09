import { useEffect, useRef, useState, type FormEvent, type Ref } from "react";
import { CountdownAnimation, ScanningAnimation } from "../../components/kiosk/KioskAnimations";
import { CameraPreview } from "../../components/kiosk/CameraPreview";
import type { CameraStatus, FaceGuideRect, FaceRegistrationFields, KioskUser } from "../../types/kiosk";

type WizardStep = "identity" | "academic" | "consent" | "capture" | "processing";
const newUserProgress = ["Thông tin", "Đồng ý", "Nhận diện khuôn mặt", "Xử lý", "Hoàn tất"];
const reenrollmentProgress = ["Đồng ý", "Nhận diện khuôn mặt", "Xử lý", "Hoàn tất"];

/** Must match the backend FACE_CONSENT_VERSION; bump both whenever this text changes. */
export const FACE_CONSENT_VERSION = "2026-10b";
export const FACE_CONSENT_POINTS = [
  "Thư viện chỉ lưu một mẫu số hóa của khuôn mặt (không lưu ảnh chụp), được mã hóa trên máy chủ thư viện, để nhận ra bạn ở các lần sau.",
  "Mẫu khuôn mặt chỉ dùng để chào và cá nhân hóa trợ lý tại kiosk, không dùng cho mục đích khác.",
  "Chỉ chính bạn mới xóa được Face ID của mình: sau khi kiosk nhận ra bạn, chọn \"Xóa Face ID\" trong mục hồ sơ, bất cứ lúc nào.",
  "Không đồng ý thì bạn vẫn dùng trợ lý bình thường với tư cách khách.",
];

export function registrationFieldsForUser(user: KioskUser): FaceRegistrationFields {
  return {
    // The kiosk only holds a masked email, so it is never sent back.
    full_name: user.full_name, student_code: user.student_code ?? undefined,
    faculty: user.faculty ?? undefined, major: user.major ?? undefined,
    admission_year: user.admission_year ?? undefined,
  };
}

export default function FaceRegistrationScreen({ videoRef, cameraStatus, cameraError, busy, qualityReady, faceCount = 0,
  faceGuideRects = [], multipleFacesDetected = false, capturePrepared = false, captureCountdown = 3, captureFrame,
  existingUser, onCaptureStart, onCaptureEnd, onEnroll, onCancel }: {
  videoRef: Ref<HTMLVideoElement>; cameraStatus: CameraStatus; cameraError?: string | null; busy: boolean; qualityReady?: boolean;
  faceCount?: number; faceGuideRects?: FaceGuideRect[]; multipleFacesDetected?: boolean; capturePrepared?: boolean; captureCountdown?: number;
  existingUser?: KioskUser | null;
  captureFrame: () => Promise<Blob>; onEnroll: (fields: FaceRegistrationFields, image: Blob) => Promise<unknown>;
  onCaptureStart: () => void; onCaptureEnd: () => void;
  onCancel: () => void;
}) {
  const reenrollment = Boolean(existingUser);
  const [step, setStep] = useState<WizardStep>(() => reenrollment ? "consent" : "identity");
  const [consented, setConsented] = useState(false);
  const [fields, setFields] = useState<FaceRegistrationFields>(() => existingUser
    ? registrationFieldsForUser(existingUser) : { full_name: "" });
  const enrolling = useRef(false);
  const [error, setError] = useState("");
  const progressSteps = reenrollment ? reenrollmentProgress : newUserProgress;
  const order: WizardStep[] = reenrollment ? ["consent", "capture", "processing"] : ["academic", "consent", "capture", "processing"];
  const activeStep = Math.max(order.indexOf(step), 0) + 1;
  const update = (name: keyof FaceRegistrationFields, value: string) => setFields((current) => ({
    ...current, [name]: name === "admission_year" ? (value ? Number(value) : undefined) : value,
  }));

  function next(event: FormEvent) {
    event.preventDefault(); setError("");
    if (!fields.full_name.trim()) { setError("Vui lòng nhập họ và tên."); return; }
    setStep(step === "identity" ? "academic" : "consent");
  }

  async function capture() {
    if (!consented || enrolling.current || busy || cameraStatus !== "READY" || !capturePrepared || !qualityReady || faceCount !== 1 || multipleFacesDetected) return;
    enrolling.current = true;
    setError(""); setStep("processing");
    try { await onEnroll({ ...fields, face_consent: true }, await captureFrame()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể đăng ký khuôn mặt."); setStep("capture"); }
    finally { enrolling.current = false; }
  }

  useEffect(() => {
    if (step !== "capture") return;
    onCaptureStart();
    return onCaptureEnd;
  }, [step]);

  useEffect(() => { if (step === "capture" && capturePrepared && qualityReady && faceCount === 1 && !multipleFacesDetected && !error) void capture();
  }, [step, capturePrepared, qualityReady, faceCount, multipleFacesDetected, error]);

  return <div className="registration-wizard">
    <ol className="wizard-progress" aria-label="Tiến trình đăng ký">{progressSteps.map((label, index) => <li key={label} className={index + 1 <= activeStep ? "active" : ""}><span>{index + 1}</span>{label}</li>)}</ol>
    {step === "processing" ? <div className="kiosk-center registration-processing"><ScanningAnimation/><span className="kiosk-kicker">BƯỚC 3 · ĐANG XỬ LÝ</span><h1>Đang tạo Face ID…</h1><p>Vui lòng chờ trong giây lát và không rời khỏi kiosk.</p></div> : null}
    {(step === "identity" || step === "academic") ? <form className="registration-step-card" onSubmit={next}>
      <span className="kiosk-kicker">BƯỚC 1 · THÔNG TIN</span>
      <h1>{step === "identity" ? "Cho chúng tôi biết về bạn" : "Thông tin học tập"}</h1>
      <p>{step === "identity" ? "Chỉ họ và tên là bắt buộc. Các thông tin còn lại giúp lời chào trở nên phù hợp hơn." : "Bạn có thể bỏ trống những thông tin chưa muốn cung cấp."}</p>
      <div className="wizard-fields">
        {step === "identity" ? <>
          <label>Họ và tên *<input autoFocus required value={fields.full_name} onChange={(event) => update("full_name", event.target.value)} placeholder="Nguyễn Văn An"/></label>
          <label>Mã số sinh viên<input value={fields.student_code ?? ""} onChange={(event) => update("student_code", event.target.value)} placeholder="MSSV"/></label>
          <label>Email<input type="email" value={fields.email ?? ""} onChange={(event) => update("email", event.target.value)} placeholder="email@student.hcmuaf.edu.vn"/></label>
        </> : <>
          <label>Khoa<input value={fields.faculty ?? ""} onChange={(event) => update("faculty", event.target.value)} placeholder="Khoa Công nghệ Thông tin"/></label>
          <label>Ngành<input value={fields.major ?? ""} onChange={(event) => update("major", event.target.value)} placeholder="Công nghệ thông tin"/></label>
          <label>Khóa tuyển sinh<input type="number" min="1990" max="2100" value={fields.admission_year ?? ""} onChange={(event) => update("admission_year", event.target.value)} placeholder="2024"/></label>
        </>}
      </div>
      {error && <div className="registration-error" role="alert">{error}</div>}
      <div className="registration-actions">{step === "academic" && <button type="button" className="kiosk-ghost" onClick={() => setStep("identity")}>Quay lại</button>}<button>Tiếp tục</button><button type="button" className="kiosk-ghost" onClick={onCancel}>Hủy đăng ký</button></div>
    </form> : null}
    {step === "consent" ? <form className="registration-step-card consent-card" onSubmit={(event) => { event.preventDefault(); if (consented) setStep("capture"); }}>
      <span className="kiosk-kicker">{reenrollment ? "ĐĂNG KÝ LẠI FACE ID" : "BƯỚC 2 · ĐỒNG Ý"}</span>
      <h1>Đồng ý lưu mẫu khuôn mặt</h1>
      {reenrollment && <p>Đang thay Face ID cho {existingUser?.full_name}. Thông tin hồ sơ hiện tại sẽ được giữ nguyên.</p>}
      <ul className="consent-points">{FACE_CONSENT_POINTS.map((point) => <li key={point}>{point}</li>)}</ul>
      <label className="consent-check"><input type="checkbox" checked={consented} onChange={(event) => setConsented(event.target.checked)}/>
        <span>Tôi đã đọc và đồng ý cho thư viện lưu mẫu khuôn mặt của tôi theo các điều trên (phiên bản {FACE_CONSENT_VERSION}).</span></label>
      <div className="registration-actions">{!reenrollment && <button type="button" className="kiosk-ghost" onClick={() => setStep("academic")}>Quay lại</button>}
        <button disabled={!consented}>Đồng ý và tiếp tục</button><button type="button" className="kiosk-ghost" onClick={onCancel}>{reenrollment ? "Quay lại hồ sơ" : "Không đồng ý"}</button></div>
    </form> : null}
    {step === "capture" ? <div className="registration-capture-step">
      <div className="registration-camera"><CameraPreview videoRef={videoRef} status={cameraStatus} error={cameraError}
        showFrameOverlay faceCount={faceCount} faceGuideRects={faceGuideRects} qualityReady={Boolean(qualityReady)}
        multipleFacesDetected={multipleFacesDetected} kioskState="REGISTER"/></div>
      <div><span className="kiosk-kicker">{reenrollment ? "ĐĂNG KÝ LẠI FACE ID" : "BƯỚC 2 · NHẬN DIỆN KHUÔN MẶT"}</span><h1>Nhìn thẳng vào camera</h1><p>{reenrollment ? `Đang thay Face ID cho ${existingUser?.full_name}. Thông tin hồ sơ hiện tại sẽ được giữ nguyên.` : "Đứng một mình trong khung hình, bỏ khẩu trang nếu có và giữ yên khuôn mặt."}</p>
        {multipleFacesDetected && <div className="registration-error registration-multiple-faces" role="alert">Phát hiện nhiều khuôn mặt. Vui lòng chỉ để một người xuất hiện trong khung hình.</div>}
        {error && <div className="registration-error" role="alert">{error}</div>}
        {!multipleFacesDetected && faceCount === 1 && qualityReady && !capturePrepared && <CountdownAnimation value={captureCountdown}/>}
        <div className="registration-actions"><span role="status">{multipleFacesDetected ? "Đăng ký đang bị khóa" : faceCount === 0 ? "Đưa khuôn mặt vào khung" : !qualityReady ? "Tiến lại gần và nhìn thẳng" : !capturePrepared ? "Giữ yên khuôn mặt" : "Đang tạo Face ID…"}</span>{!reenrollment && <button className="kiosk-ghost" onClick={() => setStep("academic")}>Sửa thông tin</button>}<button className="kiosk-ghost" onClick={onCancel}>{reenrollment ? "Quay lại hồ sơ" : "Hủy đăng ký"}</button></div>
      </div>
    </div> : null}
  </div>;
}
