import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CameraPreview } from "../../components/kiosk/CameraPreview";
import { initialState, reducer } from "../../hooks/useKioskFlow";
import type { KioskUser } from "../../types/kiosk";
import EnrollmentSuccessScreen from "./EnrollmentSuccessScreen";
import FaceRegistrationScreen from "./FaceRegistrationScreen";
import { isRecognitionState, RecognitionScreen } from "./RecognitionScreen";
import { welcomeMessage } from "./WelcomeScreen";

const noRef = () => undefined;
const user: KioskUser = { id: "u1", student_code: "001", full_name: "Nguyễn Văn An" };
const recognition = (state: "CAMERA_PREPARING" | "IDENTITY_CONFIRMING" | "UNKNOWN_FACE") => renderToStaticMarkup(
  <RecognitionScreen state={state} videoRef={noRef} cameraStatus="READY" guidance="Giữ yên"
    qualityReady={state !== "CAMERA_PREPARING"} faceCount={1} multipleFacesDetected={false} onRegister={noRef}/>,
);

describe("kiosk recognition and welcome UI", () => {
  it("unmounts recognition copy when registration is rendered", () => {
    expect(isRecognitionState("REGISTER")).toBe(false);
    const html = renderToStaticMarkup(<FaceRegistrationScreen videoRef={noRef} cameraStatus="READY" busy={false}
      captureFrame={async () => new Blob()} onCaptureStart={noRef} onCaptureEnd={noRef}
      onEnroll={async () => undefined} onCancel={noRef}/>);
    expect(html).not.toContain("Vui lòng nhìn vào camera");
    expect(html).not.toContain("Đang xác nhận danh tính");
  });

  it("renders exactly one recognition heading without overlapping old copy", () => {
    const html = recognition("IDENTITY_CONFIRMING");
    expect((html.match(/<h1/g) ?? [])).toHaveLength(1);
    expect(html).toContain("Đang xác nhận danh tính…");
    expect(html).not.toContain("Vui lòng nhìn vào camera");
  });

  it("renders the unknown heading only after the flow enters UNKNOWN_FACE", () => {
    const html = recognition("UNKNOWN_FACE");
    expect((html.match(/<h1/g) ?? [])).toHaveLength(1);
    expect(html).toContain("Chưa nhận ra khuôn mặt");
  });

  it("shows a production-safe orange guide without biometric diagnostics", () => {
    const html = renderToStaticMarkup(<CameraPreview videoRef={noRef} status="READY" faceCount={1}
      qualityReady={false} multipleFacesDetected={false} kioskState="FACE_TRACKING"/>);
    expect(html).toContain("face-guide-analyzing");
    expect(html).not.toMatch(/Track #|track_id|landmark|confidence|diagnostics/i);
  });

  it("distinguishes new enrollment, returning recognition, and re-enrollment", () => {
    expect(welcomeMessage(user, "new_enrollment")).toBe("Chào mừng Nguyễn Văn An lần đầu tiên đến với Trợ lý Thư viện AI");
    expect(welcomeMessage(user, "returning")).toContain("Chào mừng bạn quay trở lại");
    expect(welcomeMessage(user, "reenrollment")).not.toContain("lần đầu tiên");
    const success = renderToStaticMarkup(<EnrollmentSuccessScreen user={user} welcomeContext="new_enrollment" onComplete={noRef}/>);
    expect(success).toContain("lần đầu tiên đến với Trợ lý Thư viện AI");
  });

  it("keeps welcome context in the existing reducer state machine", () => {
    const result = { result: "SUCCESS", user, confidence_score: .9, next_state: "WELCOME" as const };
    const returning = reducer({ ...initialState(), currentState: "IDENTITY_CONFIRMING" }, { type: "FACE_VERIFY_SUCCESS", result });
    expect(returning.welcomeContext).toBe("returning");
    const reenrolled = reducer({ ...returning, currentState: "REGISTER_PROCESSING" },
      { type: "FACE_ENROLL_SUCCESS", result, welcomeContext: "reenrollment" });
    expect(reenrolled.welcomeContext).toBe("reenrollment");
  });
});
