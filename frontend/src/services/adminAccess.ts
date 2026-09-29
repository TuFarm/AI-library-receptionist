export type StaffRole = "admin" | "librarian";
export type AdminSession = { token: string; username: string; expires_at: number; id?: string; full_name?: string; role?: StaffRole };
export const ADMIN_SESSION_KEY = "nlu.admin.session";
const DEVICE_KEY = "nlu.admin.device";
let memorySession: AdminSession | null = null;
let memoryDevice = "";

export function getAdminSession(): AdminSession | null {
  let session = memorySession;
  try { session = JSON.parse(localStorage.getItem(ADMIN_SESSION_KEY) ?? "null"); } catch { /* Storage may be disabled. */ }
  if (!session || typeof session.token !== "string" || typeof session.username !== "string"
    || typeof session.expires_at !== "number" || session.expires_at * 1000 <= Date.now()) {
    clearAdminSession(); return null;
  }
  return session;
}
export function saveAdminSession(session: AdminSession) {
  memorySession = session;
  try { localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(session)); } catch { /* In-memory fallback. */ }
}
export function clearAdminSession() {
  memorySession = null;
  try { localStorage.removeItem(ADMIN_SESSION_KEY); } catch { /* Storage may be disabled. */ }
}
export function adminDeviceId(): string {
  try { memoryDevice = localStorage.getItem(DEVICE_KEY) || memoryDevice; } catch { /* Storage may be disabled. */ }
  if (!memoryDevice) memoryDevice = Array.from(crypto.getRandomValues(new Uint8Array(24)), byte => byte.toString(16).padStart(2, "0")).join("");
  try { localStorage.setItem(DEVICE_KEY, memoryDevice); } catch { /* In-memory fallback. */ }
  return memoryDevice;
}
export function adminHeaders(): Record<string, string> {
  const session = getAdminSession();
  return { "X-Admin-Device": adminDeviceId(), ...(session ? { Authorization: `Bearer ${session.token}` } : {}) };
}
