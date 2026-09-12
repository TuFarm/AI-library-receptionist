import { useEffect, useState, type KeyboardEvent, type PointerEvent } from "react";
import { AssistantAvatar } from "../../components/kiosk/AssistantAvatar";
import { KIOSK_IDLE_FACTS } from "../../content/kioskIdleFacts";
import { isWakeKey, shouldWakeFromTarget, type WakeSource } from "../../runtime/kioskWakeUp";

export const FACT_ROTATION_MS = 10_000;

export default function KioskIdleScreen({ onWake }: { onWake: (source: WakeSource) => boolean }) {
  const [factIndex, setFactIndex] = useState(0);
  useEffect(() => {
    const timer = window.setInterval(() => setFactIndex(index => (index + 1) % KIOSK_IDLE_FACTS.length), FACT_ROTATION_MS);
    return () => window.clearInterval(timer);
  }, []);
  const onPointerUp = (event: PointerEvent<HTMLElement>) => {
    if (!event.isPrimary || event.button !== 0 || !(event.target instanceof Element) || !shouldWakeFromTarget(event.target)) return;
    onWake("pointer");
  };
  const onCtaKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!isWakeKey(event.key)) return;
    event.preventDefault(); onWake("keyboard");
  };
  return <section className="kiosk-center idle-screen production-idle" onPointerUp={onPointerUp}>
    <div className="idle-ambient" aria-hidden="true"><i/><i/><i/></div>
    <main className="idle-hero">
      <div className="idle-avatar-wrap">
        <AssistantAvatar mood="idle" label="Trợ lý AI đang chờ và mời bạn bắt đầu"/>
        <span><i/> Trợ lý AI đang sẵn sàng</span>
      </div>
      <span className="kiosk-kicker">KHÔNG GIAN TRI THỨC CỦA BẠN</span>
      <h1>Chào bạn! <span aria-hidden="true">👋</span></h1>
      <p className="idle-lead">Tìm tài liệu, khám phá sách hay và hỏi đáp cùng trợ lý thư viện.</p>
      <button className="idle-wake-cta" data-kiosk-wake-cta onKeyDown={onCtaKeyDown}
        onClick={event => { if (event.detail === 0) onWake("assistive"); }}>
        <span>Chạm hoặc đến gần để bắt đầu</span><b aria-hidden="true">→</b>
      </button>
      <div className="idle-capabilities" aria-label="Các hỗ trợ nổi bật">
        <span>📚 Tìm vị trí sách</span><span>✨ Gợi ý tài liệu</span><span>💬 Hỏi đáp thư viện</span>
      </div>
    </main>
    <aside className="idle-fact" aria-label="Bạn có biết">
      <div className="idle-fact-icon" aria-hidden="true">💡</div>
      <div><span>MẸO NHỎ CHO BẠN</span>
        <p key={KIOSK_IDLE_FACTS[factIndex].id}>{KIOSK_IDLE_FACTS[factIndex].text}</p>
        <div className="idle-fact-dots" aria-hidden="true">{KIOSK_IDLE_FACTS.map((fact, index) => <i className={index === factIndex ? "active" : ""} key={fact.id}/>)}</div>
      </div>
    </aside>
  </section>;
}
