import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { adminApi, ApiClientError } from "../../services/apiClient";
import { ADMIN_SESSION_KEY, clearAdminSession, getAdminSession, saveAdminSession, type AdminSession } from "../../services/adminAccess";

export default function AdminAccess({ children }: { children: ReactNode | ((signOut: () => Promise<void>) => ReactNode) }) {
  const [session, setSession] = useState<AdminSession | null>(null);
  const [checking, setChecking] = useState(() => !!getAdminSession());
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    let current = true;
    async function restore() {
      const saved = getAdminSession();
      if (!saved) { setSession(null); setChecking(false); return; }
      setChecking(true);
      try {
        const info = await adminApi.getSession();
        if (current) setSession({ ...saved, ...info });
      } catch (reason) {
        if (current) { setSession(null); setError(reason instanceof Error ? reason.message : "Không thể kiểm tra phiên đăng nhập."); }
      } finally { if (current) setChecking(false); }
    }
    function expire(event: Event) { clearAdminSession(); setSession(null); setError(event instanceof CustomEvent && event.detail?.message ? event.detail.message : "Phiên đăng nhập đã hết hạn hoặc bị thu hồi. Vui lòng đăng nhập lại."); }
    function storage(event: StorageEvent) { if (event.key === ADMIN_SESSION_KEY) void restore(); }
    void restore();
    window.addEventListener("admin-session-expired", expire);
    window.addEventListener("storage", storage);
    return () => { current = false; window.removeEventListener("admin-session-expired", expire); window.removeEventListener("storage", storage); };
  }, []);

  useEffect(() => {
    if (!session) return;
    const timer = setTimeout(() => {
      clearAdminSession(); setSession(null); setError("Phiên đăng nhập đã hết 15 phút. Vui lòng đăng nhập lại.");
    }, Math.max(session.expires_at * 1000 - Date.now(), 0));
    return () => clearTimeout(timer);
  }, [session]);

  async function signOut() {
    try { await adminApi.logout(); }
    catch (reason) { if (!(reason instanceof ApiClientError) || reason.status !== 401) throw reason; }
    clearAdminSession(); setSession(null); setError("");
  }

  async function signIn(event: FormEvent) {
    event.preventDefault();
    if (loading) return;
    const errors: Record<string, string> = {};
    if (!username.trim()) errors.username = "Vui lòng nhập tên đăng nhập.";
    if (!password) errors.password = "Vui lòng nhập mật khẩu.";
    setFieldErrors(errors); setError("");
    if (Object.keys(errors).length) return;
    setLoading(true);
    try {
      const result = await adminApi.verifyAccess(username, password);
      saveAdminSession(result); setSession(result); setUsername(""); setPassword("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể đăng nhập.");
      if (reason instanceof ApiClientError) setFieldErrors(reason.fieldErrors);
    } finally { setLoading(false); }
  }

  if (checking) return <main className="page"><section className="panel loading-state" role="status">Đang kiểm tra phiên đăng nhập…</section></main>;
  if (!session) return <main className="page"><section className="panel form-panel">
    <h1>Xác thực quản trị</h1>
    <p>Đăng nhập bằng tài khoản nhân viên. Phiên được lưu 15 phút trên thiết bị và IP hiện tại.</p>
    <form className="admin-form" onSubmit={signIn} noValidate>
      <label>Tên đăng nhập<input autoComplete="username" maxLength={100} value={username} disabled={loading}
        aria-label="Tên đăng nhập" aria-describedby={fieldErrors.username ? "admin-username-error" : undefined}
        aria-invalid={!!fieldErrors.username} onChange={event => { setUsername(event.target.value); setFieldErrors(value => ({ ...value, username: "" })); }}/>
        {fieldErrors.username && <small id="admin-username-error" className="validation-error">{fieldErrors.username}</small>}</label>
      <label>Mật khẩu<input type="password" autoComplete="current-password" maxLength={1024} value={password} disabled={loading}
        aria-label="Mật khẩu" aria-describedby={fieldErrors.password ? "admin-password-error" : undefined}
        aria-invalid={!!fieldErrors.password} onChange={event => { setPassword(event.target.value); setFieldErrors(value => ({ ...value, password: "" })); }}/>
        {fieldErrors.password && <small id="admin-password-error" className="validation-error">{fieldErrors.password}</small>}</label>
      <button disabled={loading}>{loading ? "Đang xác thực…" : "Đăng nhập"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
  </section></main>;
  return <>{typeof children === "function" ? children(signOut) : children}</>;
}
