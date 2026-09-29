// Kiosk device key issued by staff from the admin UI (Admin → Thiết bị kiosk).
// Stored on the kiosk itself; never compiled into the web bundle for production.
export const DEVICE_KEY_STORAGE = "nlu.kiosk.deviceKey";
export const DEVICE_UNAUTHORIZED_EVENT = "kiosk-device-unauthorized";
const DEVICE_ERROR_CODES = new Set(["DEVICE_KEY_REQUIRED", "DEVICE_KEY_INVALID", "DEVICE_DISABLED"]);
let memoryKey = "";

export function isDeviceKey(value: string) {
  return /^kd_[A-Za-z0-9_-]{20,125}$/.test(value.trim());
}

export function getDeviceKey(): string {
  let stored = memoryKey;
  try { stored = localStorage.getItem(DEVICE_KEY_STORAGE) ?? memoryKey; } catch { /* Storage may be disabled. */ }
  if (stored) return stored;
  // Development convenience only: a key in VITE_* is visible to anyone who loads the bundle.
  const devKey = import.meta.env.DEV ? String(import.meta.env.VITE_KIOSK_DEVICE_KEY ?? "").trim() : "";
  return isDeviceKey(devKey) ? devKey : "";
}

export function saveDeviceKey(key: string) {
  memoryKey = key.trim();
  try { localStorage.setItem(DEVICE_KEY_STORAGE, memoryKey); } catch { /* In-memory fallback. */ }
}

export function clearDeviceKey() {
  memoryKey = "";
  try { localStorage.removeItem(DEVICE_KEY_STORAGE); } catch { /* Storage may be disabled. */ }
}

export function deviceHeaders(): Record<string, string> {
  const key = getDeviceKey();
  return key ? { "X-Device-Key": key } : {};
}

export function isDeviceAuthError(code: string | undefined) {
  return !!code && DEVICE_ERROR_CODES.has(code);
}

export function reportDeviceUnauthorized(code?: string) {
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(DEVICE_UNAUTHORIZED_EVENT, { detail: { code } }));
}
