import { KIOSK_TIMING } from "../config/kioskRuntime";

export type WakeSource = "motion" | "pointer" | "keyboard" | "assistive";

export class WakeUpGate {
  private inFlight = false;
  private lastAcceptedAt = -Infinity;
  tryAcquire(isIdle: boolean, now: number) {
    if (!isIdle || this.inFlight || now - this.lastAcceptedAt < KIOSK_TIMING.presenceWakeCooldownMs) return false;
    this.inFlight = true; this.lastAcceptedAt = now; return true;
  }
  release() { this.inFlight = false; }
}

export function shouldWakeFromTarget(target: Element) {
  if (target.closest("[data-kiosk-wake-ignore]")) return false;
  const interactive = target.closest("a,button,input,select,textarea,[role='button'],[contenteditable='true']");
  return !interactive || Boolean(target.closest("[data-kiosk-wake-cta]"));
}

export function isWakeKey(key: string) { return key === "Enter" || key === " "; }
