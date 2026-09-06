import { useEffect, useRef, useState, type FormEvent, type Ref } from "react";
import { ScanningAnimation } from "../../components/kiosk/KioskAnimations";
import { CameraPreview } from "../../components/kiosk/CameraPreview";
import type { CameraStatus, FaceRegistrationFields } from "../../types/kiosk";

type WizardStep = "identity" | "academic" | "capture" | "processing";
const progressSteps = ["Thông tin", "Nhận diện khuôn mặt", "Xử lý", "Hoàn tất"];

export default function FaceRegistrationScreen({ videoRef, cameraStatus, cameraError, busy, qualityReady, captureFrame, onEnroll, onCancel }: {
  videoRef: Ref<HTMLVideoElement>; cameraStatus: CameraStatus; cameraError?: string | null; busy: boolean; qualityReady?: boolean;
  captureFrame: () => Promise<Blob>; onEnroll: (fields: FaceRegistrationFields, image: Blob) => Promise<unknown>;
  onCancel: () => void;
}) {
  const [step, setStep] = useState<WizardStep>("identity");
  const [fields, setFields] = useState<FaceRegistrationFields>({ full_name: "" });
  const enrolling = useRef(false);
  const [error, setError] = useState("");
  const activeStep = step === "capture" ? 2 : step === "processing" ? 3 : 1;
  const update = (name: keyof FaceRegistrationFields, value: string) => setFields((current) => ({
    ...current, [name]: name === "admission_year" ? (value ? Number(value) : undefined) : value,
  }));

  function next(event: FormEvent) {
    event.preventDefault(); setError("");
    if (!fields.full_name.trim()) { setError("Vui lòng nhập họ và tên."); return; }
    setStep(step === "identity" ? "academic" : "capture");
  }

  async function capture() {
    if (enrolling.current || busy || cameraStatus !== "READY" || !qualityReady) return;
    enrolling.current = true;
    setError(""); setStep("processing");
    try { await onEnroll(fields, await captureFrame()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể đăng ký khuôn mặt."); setStep("capture"); }
    finally { enrolling.current = false; }
  }

  useEffect(() => { if (step === "capture" && qualityReady && !error) void capture(); }, [step, qualityReady, error]);

  return <div className="registration-wizard">
    <ol className="wizard-progress" aria-label="Tiến trình đăng ký">{progressSteps.map((label, index) => <li key={label} className={index + 1 <= activeStep ? "active" : ""}><span>{index + 1}</span>{label}</li>)}</ol>
    {step === "processing" ? <div className="kiosk-center registration-processing"><ScanningAnimation/><span className="kiosk-kicker">BƯỚC 3 · ĐANG XỬ LÝ</span><h1>Đang tạo hồ sơ nhận diện...</h1><p>Vui lòng chờ trong giây lát và không rời khỏi kiosk.</p></div> : null}
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
          <label>Số điện thoại<input value={fields.phone ?? ""} onChange={(event) => update("phone", event.target.value)} placeholder="Số điện thoại"/></label>
        </>}
      </div>
      {error && <div className="registration-error" role="alert">{error}</div>}
      <div className="registration-actions">{step === "academic" && <button type="button" className="kiosk-ghost" onClick={() => setStep("identity")}>Quay lại</button>}<button>Tiếp tục</button><button type="button" className="kiosk-ghost" onClick={onCancel}>Hủy đăng ký</button></div>
    </form> : null}
    {step === "capture" ? <div className="registration-capture-step">
      <div className="registration-camera"><CameraPreview videoRef={videoRef} status={cameraStatus} error={cameraError} showFrameOverlay/></div>
      <div><span className="kiosk-kicker">BƯỚC 2 · NHẬN DIỆN KHUÔN MẶT</span><h1>Nhìn thẳng vào camera</h1><p>Đứng một mình trong khung hình, bỏ khẩu trang nếu có và giữ yên khuôn mặt.</p>
        {error && <div className="registration-error" role="alert">{error}</div>}
        <div className="registration-actions"><span role="status">{qualityReady ? "Đang đăng ký tự động…" : "Nhìn thẳng và giữ yên để đăng ký"}</span><button className="kiosk-ghost" onClick={() => setStep("academic")}>Sửa thông tin</button><button className="kiosk-ghost" onClick={onCancel}>Hủy đăng ký</button></div>
      </div>
    </div> : null}
  </div>;
}
