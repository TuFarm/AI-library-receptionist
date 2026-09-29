import { API_ROOT } from "../services/apiClient";
import { getDeviceKey, reportDeviceUnauthorized } from "../services/deviceAccess";
import { kioskEvents, type RuntimeEvent } from "./eventBus";
import { RuntimeEvent as Events } from "./events";

// Server close codes for a missing/invalid (4401) or disabled/foreign (4403) device.
const DEVICE_REJECTED = new Set([4401, 4403]);

export class KioskStream {
  private socket: WebSocket | null = null;
  private pending = new Map<string, { resolve: (value: Record<string, unknown>) => void; reject: (error: Error) => void; timer: number }>();
  private retry?: number;
  private heartbeat?: number;
  private frameDeadline?: number;
  private closed = true;
  private attempt = 0;
  private config: Record<string, unknown> = { mode: "idle" };
  lastFrameSentAt: number | null = null;
  frameReady = false;
  connect() {
    this.closed = false;
    const socket = new WebSocket(`${API_ROOT.replace(/^http/, "ws")}/kiosk/stream`);
    this.socket = socket;
    socket.onopen = () => {
      if (this.socket !== socket || this.closed) { socket.close(); return; }
      this.attempt = 0;
      // The device key goes in the first message, never in the URL (proxies log URLs).
      socket.send(JSON.stringify({ event: "AUTH", payload: { device_key: getDeviceKey() } }));
      this.configure(this.config);
      this.heartbeat = window.setInterval(() => this.send("PING", { sent_at: performance.now() }), 15000);
    };
    socket.onmessage = ({ data }) => {
      if (this.socket !== socket || this.closed) return;
      let event: RuntimeEvent;
      try { event = JSON.parse(data); } catch { socket.close(1002); return; }
      if (event.event === Events.streamReady || event.event === Events.frameReady) {
        this.frameReady = true;
        window.clearTimeout(this.frameDeadline);
      }
      if (event.event === Events.pong) kioskEvents.publish(Events.transportLatency, { latency_ms: performance.now() - Number(event.payload.sent_at) });
      const pending = event.request_id ? this.pending.get(event.request_id) : undefined;
      if (pending && (event.event === Events.aiProcessingFinished || event.event === Events.requestError)) {
        window.clearTimeout(pending.timer);
        this.pending.delete(event.request_id!);
        if (event.event === Events.requestError) pending.reject(new Error(String(event.payload.message)));
        else pending.resolve(event.payload);
      }
      kioskEvents.receive(event);
      if (event.event === Events.frameReady) this.lastFrameSentAt = null;
    };
    socket.onclose = (event?: CloseEvent) => {
      const code = event?.code ?? 0;
      if (this.socket !== socket) return;
      this.frameReady = false;
      window.clearInterval(this.heartbeat);
      window.clearTimeout(this.frameDeadline);
      for (const request of this.pending.values()) { window.clearTimeout(request.timer); request.reject(new Error("Kết nối bị gián đoạn.")); }
      this.pending.clear();
      if (!this.closed && DEVICE_REJECTED.has(code)) {
        this.closed = true;
        reportDeviceUnauthorized(code === 4403 ? "DEVICE_DISABLED" : "DEVICE_KEY_INVALID");
      }
      if (!this.closed) {
        kioskEvents.publish(Events.streamDisconnected);
        this.retry = window.setTimeout(() => this.connect(), Math.min(10000, 500 * 2 ** this.attempt++));
      }
    };
    socket.onerror = () => socket.close();
  }
  configure(config: Record<string, unknown>) { this.config = config; this.send("CONFIGURE", config); }
  send(event: string, payload: Record<string, unknown> = {}, request_id?: string) {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify({ event, payload, request_id }));
    return true;
  }
  frame(blob: Blob) {
    if (!this.frameReady || this.socket?.readyState !== WebSocket.OPEN || this.socket.bufferedAmount > 2_500_000) return false;
    this.frameReady = false;
    this.lastFrameSentAt = performance.now();
    this.socket.send(blob);
    this.frameDeadline = window.setTimeout(() => this.socket?.close(), 15000);
    return true;
  }
  request(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return new Promise((resolve, reject) => {
      const id = crypto.randomUUID();
      const timer = window.setTimeout(() => { this.pending.delete(id); reject(new Error("AI phản hồi quá thời gian chờ.")); }, 45000);
      this.pending.set(id, { resolve, reject, timer });
      if (!this.send("AI_REQUEST", payload, id)) {
        window.clearTimeout(timer); this.pending.delete(id); reject(new Error("Chưa kết nối với trợ lý."));
      }
    });
  }
  close() { this.closed = true; window.clearTimeout(this.retry); window.clearInterval(this.heartbeat); window.clearTimeout(this.frameDeadline); this.socket?.close(); }
}
export const kioskStream = new KioskStream();
