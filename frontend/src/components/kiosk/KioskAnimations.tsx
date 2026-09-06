import type { ReactNode } from "react";

export function AnimatedTransition({ state, children }: { state: string; children: ReactNode }) {
  return <div className="kiosk-transition" data-kiosk-state={state}>{children}</div>;
}

export { AssistantAvatar } from "./AssistantAvatar";

export function ListeningIndicator({ active = true }: { active?: boolean }) {
  return <div className={`listening-indicator ${active ? "active" : ""}`} aria-label="Micro đang lắng nghe">
    <span>●</span><div>{[1, 2, 3, 4, 5].map((bar) => <i key={bar}/>)}</div>
  </div>;
}

export function ScanningAnimation() {
  return <div className="verification-visual" role="status" aria-label="Đang xác minh danh tính">
    <div className="verification-portrait"><span>☺</span><i/></div>
    <div className="verification-progress"><i/></div>
  </div>;
}

export function CountdownAnimation({ value }: { value: number }) {
  return <div className="countdown-animation" key={value} aria-live="assertive">{value}</div>;
}

export function SuccessAnimation() {
  return <div className="success-animation" role="img" aria-label="Nhận diện thành công">
    <span>✓</span><i/><i/><i/>
  </div>;
}
