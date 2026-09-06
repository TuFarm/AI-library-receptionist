import { describe, expect, it } from "vitest";
import { canTransition } from "./stateMachine";
import { EventBus } from "./eventBus";
import { initialState, reducer } from "../hooks/useKioskFlow";

describe("kiosk lifecycle", () => {
  it("rejects recognition reentry from a conversation", () => {
    expect(canTransition("AI_SPEAKING", "FACE_TRACKING")).toBe(false);
    expect(canTransition("WELCOME", "CAMERA_PREPARING")).toBe(false);
    expect(canTransition("REGISTER_PROCESSING", "UNKNOWN_FACE")).toBe(false);
    expect(canTransition("AI_SPEAKING", "VOICE_LISTENING")).toBe(true);
  });
  it("does not permit a stale transition to reopen the camera", () => {
    const state = { ...initialState(), currentState: "AI_SPEAKING" as const };
    expect(reducer(state, { type: "TRANSITION", state: "CAMERA_PREPARING" })).toBe(state);
  });
  it("releases subscriptions and allows multiple independent consumers", () => {
    const bus = new EventBus(); const events: string[] = [];
    const stop = bus.subscribe(event => events.push(event.event));
    bus.publish("identity_confirmed"); stop(); bus.publish("session_reset");
    expect(events).toEqual(["identity_confirmed"]);
  });
});
