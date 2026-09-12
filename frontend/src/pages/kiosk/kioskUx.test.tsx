import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CameraPreview } from "../../components/kiosk/CameraPreview";
import { initialState, reducer } from "../../hooks/useKioskFlow";
import type { KioskUser } from "../../types/kiosk";
import EnrollmentSuccessScreen from "./EnrollmentSuccessScreen";
import FaceRegistrationScreen, { registrationFieldsForUser } from "./FaceRegistrationScreen";
import { isRecognitionState, RecognitionScreen } from "./RecognitionScreen";
import { welcomeMessage } from "./WelcomeScreen";
import KioskIdleScreen, { FACT_ROTATION_MS } from "./KioskIdleScreen";
import { KIOSK_IDLE_FACTS } from "../../content/kioskIdleFacts";
import { avatarMoodForState } from "../../runtime/avatarMood";

const noRef = () => undefined;
const user: KioskUser = { id: "u1", student_code: "001", full_name: "Nguyễn Văn An" };
const recognition = (state: "CAMERA_PREPARING" | "IDENTITY_CONFIRMING" | "UNKNOWN_FACE") => renderToStaticMarkup(
  <RecognitionScreen state={state} videoRef={noRef} cameraStatus="READY" guidance="Giữ yên"
    qualityReady={state !== "CAMERA_PREPARING"} faceCount={1}
    faceGuideRects={[{ x_pct: 25, y_pct: 18, width_pct: 30, height_pct: 42, quality_ok: true }]}
    multipleFacesDetected={false} onRegister={noRef}/>,
);

describe("kiosk recognition and welcome UI", () => {
  it("renders a camera-invisible, touchable idle invitation with static facts and privacy copy", () => {
    const html = renderToStaticMarkup(<KioskIdleScreen onWake={() => true}/>);
    expect(html).toContain("Chạm hoặc đến gần để bắt đầu");
    expect(html).toContain("<button"); expect(html).toContain("data-kiosk-wake-cta");
    expect(html).toContain(KIOSK_IDLE_FACTS[0].text); expect(FACT_ROTATION_MS).toBeGreaterThanOrEqual(8000);
    expect(FACT_ROTATION_MS).toBeLessThanOrEqual(12000);
    expect(html).not.toContain("Camera chỉ dùng để phát hiện");
    expect(html).not.toMatch(/<video|camera-preview|face-frame|scanner|verification-visual/);
  });

  it("maps kiosk states to avatar mood from one typed source", () => {
    expect(avatarMoodForState("IDLE")).toBe("idle");
    expect(avatarMoodForState("PRESENCE_DETECTED")).toBe("greeting");
    expect(avatarMoodForState("FACE_TRACKING")).toBe("focused");
    expect(avatarMoodForState("LISTENING")).toBe("listening");
    expect(avatarMoodForState("PROCESSING")).toBe("thinking");
    expect(avatarMoodForState("AI_SPEAKING")).toBe("speaking");
    expect(avatarMoodForState("ERROR")).toBe("error");
    expect(avatarMoodForState("RETURN_IDLE")).toBe("idle");
  });
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
      faceGuideRects={[{ x_pct: 22.5, y_pct: 14, width_pct: 31, height_pct: 48, quality_ok: false }]}
      qualityReady={false} multipleFacesDetected={false} kioskState="FACE_TRACKING"/>);
    expect(html).toContain("face-guide-analyzing");
    expect(html).toContain("left:22.5%");
    expect(html).not.toContain("scan-line");
    expect(html).not.toMatch(/Track #|track_id|landmark|confidence|diagnostics/i);
  });

  it("distinguishes new enrollment, returning recognition, and re-enrollment", () => {
    expect(welcomeMessage(user, "new_enrollment")).toBe("Chào mừng Nguyễn Văn An lần đầu tiên đến với Trợ lý Thư viện AI");
    expect(welcomeMessage(user, "returning")).toContain("Chào mừng bạn quay trở lại");
    expect(welcomeMessage(user, "reenrollment")).not.toContain("lần đầu tiên");
    const success = renderToStaticMarkup(<EnrollmentSuccessScreen user={user} welcomeContext="new_enrollment" onComplete={noRef}/>);
    expect(success).toContain("lần đầu tiên đến với Trợ lý Thư viện AI");
  });

  it("re-enrollment keeps the current profile and opens directly on face capture", () => {
    const profile = { ...user, email: "an@example.test", faculty: "CNTT", admission_year: 2024 };
    expect(registrationFieldsForUser(profile)).toEqual({
      full_name: "Nguyễn Văn An", student_code: "001", email: "an@example.test",
      phone: undefined, faculty: "CNTT", major: undefined, admission_year: 2024,
    });
    const html = renderToStaticMarkup(<FaceRegistrationScreen existingUser={profile} videoRef={noRef}
      cameraStatus="READY" busy={false} captureFrame={async () => new Blob()}
      onCaptureStart={noRef} onCaptureEnd={noRef} onEnroll={async () => undefined} onCancel={noRef}/>);
    expect(html).toContain("ĐĂNG KÝ LẠI FACE ID");
    expect(html).toContain("Thông tin hồ sơ hiện tại sẽ được giữ nguyên");
    expect(html).not.toContain("Cho chúng tôi biết về bạn");
    expect(html).not.toContain("Sửa thông tin");
  });

  it("keeps welcome context in the existing reducer state machine", () => {
    const result = { result: "SUCCESS", user, confidence_score: .9, next_state: "WELCOME" as const };
    const returning = reducer({ ...initialState(), currentState: "IDENTITY_CONFIRMING" }, { type: "FACE_VERIFY_SUCCESS", result });
    expect(returning.welcomeContext).toBe("returning");
    const reenrolled = reducer({ ...returning, currentState: "REGISTER_PROCESSING" },
      { type: "FACE_ENROLL_SUCCESS", result, welcomeContext: "reenrollment" });
    expect(reenrolled.welcomeContext).toBe("reenrollment");
    const conversation = reducer(reenrolled, { type: "START_CONVERSATION", conversation: { conversation_id: "c1", status: "active" } });
    expect(conversation.currentState).toBe("AI_GREETING");
  });
});
