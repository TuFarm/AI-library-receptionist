import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { ApiClientError, kioskApi } from "../../services/apiClient";
import {
  clearDeviceKey, DEVICE_UNAUTHORIZED_EVENT, getDeviceKey, isDeviceKey, saveDeviceKey,
} from "../../services/deviceAccess";

const REJECTED: Record<string, string> = {
  DEVICE_DISABLED: "Thiết bị này đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên.",
  DEVICE_KEY_INVALID: "Khóa thiết bị không còn hiệu lực (có thể đã được cấp lại). Vui lòng nhập khóa mới.",
  DEVICE_KEY_REQUIRED: "Kiosk chưa được đăng ký với hệ thống.",
};

/** Renders the kiosk only once this device holds a key issued from Admin → Thiết bị kiosk. */
export default function KioskDeviceGate({ children }: { children: ReactNode }) {
  const [hasKey, setHasKey] = useState(() => !!getDeviceKey());
  const [notice, setNotice] = useState("");
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    function rejected(event: Event) {
      const code = event instanceof CustomEvent ? event.detail?.code as string | undefined : undefined;
      // A disabled device keeps its key so it works again once re-enabled; other errors need a new key.
      if (code !== "DEVICE_DISABLED") clearDeviceKey();
      setNotice(REJECTED[code ?? ""] ?? REJECTED.DEVICE_KEY_REQUIRED);
      setHasKey(false);
    }
    window.addEventListener(DEVICE_UNAUTHORIZED_EVENT, rejected);
    return () => window.removeEventListener(DEVICE_UNAUTHORIZED_EVENT, rejected);
  }, []);

  async function register(event: FormEvent) {
    event.preventDefault();
    const candidate = key.trim();
    if (!isDeviceKey(candidate)) { setError("Khóa thiết bị bắt đầu bằng “kd_”. Vui lòng kiểm tra lại."); return; }
    setBusy(true); setError("");
    try {
      await kioskApi.verifyDevice(candidate);
      saveDeviceKey(candidate);
      setKey(""); setNotice(""); setHasKey(true);
    } catch (reason) {
      setError(reason instanceof ApiClientError && reason.code ? REJECTED[reason.code] ?? reason.message
        : reason instanceof Error ? reason.message : "Không thể xác minh khóa thiết bị.");
    } finally { setBusy(false); }
  }

  if (hasKey) return <>{children}</>;
  return <div className="kiosk-content device-setup-screen">
    <section className="kiosk-center device-setup" aria-labelledby="device-setup-title">
      <span className="kiosk-kicker">CÀI ĐẶT THIẾT BỊ</span>
      <h1 id="device-setup-title">Kết nối kiosk với hệ thống</h1>
      <p>{notice || "Nhân viên thư viện vui lòng nhập khóa thiết bị được cấp tại trang quản trị (mục Thiết bị kiosk)."}</p>
      <form className="kiosk-input device-key-form" onSubmit={register} noValidate>
        <input type="password" autoComplete="off" spellCheck={false} aria-label="Khóa thiết bị" placeholder="kd_…"
          value={key} disabled={busy} onChange={change => { setKey(change.target.value); setError(""); }}/>
        <button disabled={busy || !key.trim()}>{busy ? "Đang xác minh…" : "Kết nối"}</button>
      </form>
      {error && <p className="registration-error" role="alert">{error}</p>}
    </section>
  </div>;
}
