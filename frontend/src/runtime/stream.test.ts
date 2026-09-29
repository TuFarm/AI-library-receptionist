import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KioskStream } from "./stream";

class FakeSocket {
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = 1;
  bufferedAmount = 0;
  sent: unknown[] = [];
  onopen?: () => void;
  onclose?: (event?: { code: number }) => void;
  onmessage?: (event: { data: string }) => void;
  onerror?: () => void;
  constructor() { FakeSocket.instances.push(this); }
  send(data: unknown) { this.sent.push(data); }
  close(code?: number) { this.readyState = 3; (this.onclose as ((event?: { code: number }) => void) | undefined)?.(code ? { code } : undefined); }
  receive(event: string, payload = {}, request_id?: string) { this.onmessage?.({ data: JSON.stringify({ event, payload, request_id }) }); }
}
describe("duplex stream lifecycle", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.stubGlobal("window", globalThis); vi.stubGlobal("WebSocket", FakeSocket); FakeSocket.instances = []; });
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); });
  it("permits one frame until an acknowledgement and never buffers a second", () => {
    const stream = new KioskStream(); stream.connect(); const socket = FakeSocket.instances[0]; socket.onopen?.(); socket.receive("stream_ready");
    expect(stream.frame(new Blob(["frame"]))).toBe(true);
    expect(stream.lastFrameSentAt).not.toBeNull();
    expect(stream.frame(new Blob(["late"]))).toBe(false);
    socket.receive("frame_ready");
    expect(stream.lastFrameSentAt).toBeNull();
    expect(stream.frame(new Blob(["next"]))).toBe(true);
    stream.close();
  });
  it("ignores events and close callbacks from an obsolete connection", () => {
    const stream = new KioskStream(); stream.connect(); const old = FakeSocket.instances[0];
    stream.close(); stream.connect(); const current = FakeSocket.instances[1];
    old.receive("stream_ready"); old.onclose?.();
    expect(stream.frameReady).toBe(false);
    current.onopen?.(); current.receive("stream_ready");
    expect(stream.frameReady).toBe(true);
    stream.close(); vi.advanceTimersByTime(30000);
    expect(FakeSocket.instances).toHaveLength(2);
  });
  it("rejects an interrupted turn instead of replaying it", async () => {
    const stream = new KioskStream(); stream.connect(); const socket = FakeSocket.instances[0]; socket.onopen?.();
    const request = stream.request({ message_text: "hello" });
    const assertion = expect(request).rejects.toThrow("gián đoạn");
    socket.close(); await assertion; stream.close();
  });
  it("authenticates with the device key as the first message, never in the URL", () => {
    const values = new Map([["nlu.kiosk.deviceKey", "kd_test-device-key-0000000000"]]);
    vi.stubGlobal("localStorage", { getItem: (key: string) => values.get(key) ?? null, setItem: vi.fn(), removeItem: vi.fn() });
    const stream = new KioskStream(); stream.connect(); const socket = FakeSocket.instances[0]; socket.onopen?.();
    expect(JSON.parse(String(socket.sent[0]))).toEqual({ event: "AUTH", payload: { device_key: "kd_test-device-key-0000000000" } });
    expect(JSON.parse(String(socket.sent[1])).event).toBe("CONFIGURE");
    stream.close();
  });
  it("stops reconnecting and reports when the server rejects the device", () => {
    const target = new EventTarget();
    const listener = vi.fn();
    target.addEventListener("kiosk-device-unauthorized", listener);
    vi.stubGlobal("window", {
      setTimeout: (...args: Parameters<typeof setTimeout>) => setTimeout(...args),
      clearTimeout: (id: number) => clearTimeout(id),
      setInterval: (...args: Parameters<typeof setInterval>) => setInterval(...args),
      clearInterval: (id: number) => clearInterval(id),
      dispatchEvent: (event: Event) => target.dispatchEvent(event),
    });
    const stream = new KioskStream(); stream.connect(); FakeSocket.instances[0].onopen?.();
    FakeSocket.instances[0].close(4401);
    vi.advanceTimersByTime(30000);
    expect(FakeSocket.instances).toHaveLength(1);
    expect(listener).toHaveBeenCalledOnce();
  });
});
