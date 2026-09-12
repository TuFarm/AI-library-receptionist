import { describe, expect, it } from "vitest";
import { isWakeKey, WakeUpGate, shouldWakeFromTarget } from "./kioskWakeUp";

const target = (ignored: boolean, interactive: boolean, cta = false) => ({
  closest: (selector: string) => selector.includes("wake-ignore") ? (ignored ? {} : null)
    : selector.includes("a,button") ? (interactive ? {} : null) : selector.includes("wake-cta") ? (cta ? {} : null) : null,
}) as unknown as Element;

describe("idle wake-up arbitration", () => {
  it("accepts one idle source and rejects races, cooldown, and non-idle input", () => {
    const gate = new WakeUpGate();
    expect(gate.tryAcquire(true, 1000)).toBe(true);
    expect(gate.tryAcquire(true, 1000)).toBe(false);
    gate.release();
    expect(gate.tryAcquire(true, 1500)).toBe(false);
    expect(gate.tryAcquire(false, 2500)).toBe(false);
    expect(gate.tryAcquire(true, 2500)).toBe(true);
  });
  it("allows the public surface/CTA but ignores admin or unrelated controls", () => {
    expect(shouldWakeFromTarget(target(false, false))).toBe(true);
    expect(shouldWakeFromTarget(target(false, true, true))).toBe(true);
    expect(shouldWakeFromTarget(target(false, true))).toBe(false);
    expect(shouldWakeFromTarget(target(true, false))).toBe(false);
  });
  it("supports Enter and Space without hijacking other navigation keys", () => {
    expect(isWakeKey("Enter")).toBe(true); expect(isWakeKey(" ")).toBe(true);
    expect(isWakeKey("Tab")).toBe(false); expect(isWakeKey("Escape")).toBe(false);
  });
});
