import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { KioskStream } from "./stream";

class FakeSocket {
  static OPEN = 1;
  static instances: FakeSocket[] = [];
  readyState = 1;
  bufferedAmount = 0;
  sent: unknown[] = [];
  onopen?: () => void;
  onclose?: () => void;
  onmessage?: (event: { data: string }) => void;
  onerror?: () => void;
  constructor() { FakeSocket.instances.push(this); }
  send(data: unknown) { this.sent.push(data); }
  close() { this.readyState = 3; this.onclose?.(); }
  receive(event: string, payload = {}, request_id?: string) { this.onmessage?.({ data: JSON.stringify({ event, payload, request_id }) }); }
}
describe("duplex stream lifecycle", () => {
  beforeEach(() => { vi.useFakeTimers(); vi.stubGlobal("window", globalThis); vi.stubGlobal("WebSocket", FakeSocket); FakeSocket.instances = []; });
  afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); });
  it("permits one frame until an acknowledgement and never buffers a second", () => {
    const stream = new KioskStream(); stream.connect(); const socket = FakeSocket.instances[0]; socket.onopen?.(); socket.receive("stream_ready");
    expect(stream.frame(new Blob(["frame"]))).toBe(true);
    expect(stream.frame(new Blob(["late"]))).toBe(false);
    socket.receive("frame_ready");
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
});
