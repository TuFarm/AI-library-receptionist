export type RuntimeEvent = { event: string; payload: Record<string, unknown>; sequence?: number; request_id?: string };
export class EventBus {
  private listeners = new Set<(event: RuntimeEvent) => void>();
  subscribe(listener: (event: RuntimeEvent) => void) {
    this.listeners.add(listener);
    return () => { this.listeners.delete(listener); };
  }
  publish(event: string, payload: Record<string, unknown> = {}) {
    this.receive({ event, payload });
  }
  receive(event: RuntimeEvent) { [...this.listeners].forEach(listener => listener(event)); }
}
export const kioskEvents = new EventBus();
