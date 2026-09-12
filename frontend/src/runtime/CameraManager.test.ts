import { afterEach, describe, expect, it, vi } from "vitest";
import { CameraManager } from "./CameraManager";
import { isFaceFrameState } from "./useRealtimeSensor";

afterEach(() => vi.unstubAllGlobals());

describe("persistent kiosk camera lifecycle", () => {
  it("reuses one MediaStream and stops tracks only on explicit lifecycle cleanup", async () => {
    const stop = vi.fn();
    const stream = { getVideoTracks: () => [{ readyState: "live" }], getTracks: () => [{ stop }] } as unknown as MediaStream;
    const getUserMedia = vi.fn(async () => stream);
    const videos: Array<Record<string, unknown>> = [];
    vi.stubGlobal("navigator", { mediaDevices: { getUserMedia } });
    vi.stubGlobal("document", { createElement: () => {
      const video = { srcObject: null, muted: false, playsInline: false, autoplay: false, play: vi.fn(async () => undefined) };
      videos.push(video); return video;
    } });
    const manager = new CameraManager();
    expect(manager.sensingVideo).toBe(manager.sensingVideo);
    expect(await manager.start()).toBe(true); expect(await manager.start()).toBe(true);
    expect(getUserMedia).toHaveBeenCalledTimes(1); expect(stop).not.toHaveBeenCalled();
    manager.stop(); expect(stop).toHaveBeenCalledTimes(1);
    expect(videos[0].srcObject).toBe(null);
  });

  it("never classifies IDLE as a WebSocket face-frame state", () => {
    expect(isFaceFrameState("IDLE")).toBe(false);
    expect(isFaceFrameState("PRESENCE_DETECTED")).toBe(false);
    expect(isFaceFrameState("CAMERA_PREPARING")).toBe(true);
    expect(isFaceFrameState("FACE_TRACKING")).toBe(true);
  });
});
