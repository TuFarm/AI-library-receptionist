import { FormEvent, useCallback, useEffect, useState } from "react";
import { PageHeader } from "../../components/ui";
import { ApiClientError, deviceApi, type IssuedDeviceKey, type KioskDevice } from "../../services/apiClient";

const emptyForm = { device_code: "", device_name: "", location: "" };

export function validateDeviceForm(form: typeof emptyForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!/^[A-Za-z0-9_-]{2,80}$/.test(form.device_code.trim())) errors.device_code = "Mã thiết bị 2–80 ký tự: chữ, số, _ hoặc -";
  if (!form.device_name.trim()) errors.device_name = "Vui lòng nhập tên thiết bị.";
  return errors;
}

function formatTime(value: string | null) {
  return value ? new Date(value).toLocaleString("vi-VN") : "—";
}

export default function DevicesPage() {
  const [devices, setDevices] = useState<KioskDevice[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [issued, setIssued] = useState<IssuedDeviceKey | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [confirmRotate, setConfirmRotate] = useState<KioskDevice | null>(null);

  const load = useCallback(() => {
    setLoading(true); setError("");
    deviceApi.list().then(setDevices).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  async function run<T>(action: () => Promise<T>): Promise<T | null> {
    setBusy(true); setError("");
    try { const result = await action(); load(); return result; }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể thực hiện thao tác.");
      if (reason instanceof ApiClientError) setErrors(reason.fieldErrors);
      return null;
    } finally { setBusy(false); }
  }

  function reveal(result: IssuedDeviceKey | null) {
    if (result) { setIssued(result); setCopied(false); }
  }

  async function register(event: FormEvent) {
    event.preventDefault();
    const invalid = validateDeviceForm(form);
    setErrors(invalid);
    if (Object.keys(invalid).length) return;
    const result = await run(() => deviceApi.create({
      device_code: form.device_code.trim(), device_name: form.device_name.trim(), location: form.location.trim() || undefined,
    }));
    if (result) { setForm(emptyForm); reveal(result); }
  }

  async function copyKey() {
    if (!issued) return;
    try { await navigator.clipboard.writeText(issued.device_key); setCopied(true); }
    catch { setError("Không thể sao chép tự động. Vui lòng chọn và sao chép khóa thủ công."); }
  }

  return <><PageHeader eyebrow="BẢO MẬT KIOSK" title="Thiết bị kiosk"
      description="Mỗi kiosk cần một khóa riêng để gọi API và mở luồng camera. Khóa chỉ hiển thị một lần khi cấp."/>
    {issued && <section className="panel admin-key-reveal" role="status" aria-live="polite">
      <strong>Khóa cho {issued.device_code}</strong>
      <code>{issued.device_key}</code>
      <p>Nhập khóa này vào màn hình “Cài đặt thiết bị” trên kiosk. Sau khi đóng thông báo, khóa sẽ không hiển thị lại.</p>
      <div className="modal-actions">
        <button type="button" onClick={() => void copyKey()}>{copied ? "Đã sao chép" : "Sao chép khóa"}</button>
        <button type="button" className="secondary" onClick={() => setIssued(null)}>Tôi đã lưu khóa</button>
      </div>
    </section>}
    <section className="panel form-panel"><div className="panel-head"><h2>Đăng ký kiosk</h2></div>
      <form className="admin-form" onSubmit={register} noValidate>
        <label className={errors.device_code ? "field-error" : ""}>Mã thiết bị *
          <input maxLength={80} value={form.device_code} disabled={busy} placeholder="KIOSK_TANG1" aria-invalid={!!errors.device_code}
            onChange={event => setForm(value => ({ ...value, device_code: event.target.value }))}/>
          {errors.device_code && <small className="validation-error">{errors.device_code}</small>}</label>
        <label className={errors.device_name ? "field-error" : ""}>Tên thiết bị *
          <input maxLength={150} value={form.device_name} disabled={busy} aria-invalid={!!errors.device_name}
            onChange={event => setForm(value => ({ ...value, device_name: event.target.value }))}/>
          {errors.device_name && <small className="validation-error">{errors.device_name}</small>}</label>
        <label>Vị trí<input maxLength={255} value={form.location} disabled={busy}
          onChange={event => setForm(value => ({ ...value, location: event.target.value }))}/></label>
        <button disabled={busy}>{busy ? "Đang lưu…" : "Đăng ký và cấp khóa"}</button>
      </form>
    </section>
    {error && <div className="tip error" role="alert"><span>!</span><p>{error}</p></div>}
    {confirmRotate && <div className="modal-overlay" onClick={() => { if (!busy) setConfirmRotate(null); }}>
      <div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="rotate-title" onClick={event => event.stopPropagation()}>
        <h3 id="rotate-title">Cấp lại khóa cho {confirmRotate.device_code}?</h3>
        <p>Khóa hiện tại sẽ ngừng hoạt động ngay. Kiosk này cần được nhập khóa mới trước khi dùng tiếp.</p>
        <div className="modal-actions">
          <button className="secondary" disabled={busy} onClick={() => setConfirmRotate(null)}>Hủy</button>
          <button className="danger" disabled={busy} onClick={async () => {
            const result = await run(() => deviceApi.rotateKey(confirmRotate.id));
            setConfirmRotate(null); reveal(result);
          }}>Cấp khóa mới</button>
        </div>
      </div>
    </div>}
    <section className="panel table-panel"><div className="panel-head"><h2>Danh sách thiết bị ({devices.length})</h2></div>
      {loading ? <div className="loading-state">Đang tải…</div> : devices.length === 0
        ? <div className="empty-state"><strong>Chưa có kiosk nào</strong><p>Đăng ký kiosk đầu tiên ở biểu mẫu phía trên.</p></div>
        : <div className="data-table">{devices.map(device => <div className="user-row" key={device.id}>
          <div><strong>{device.device_name}</strong><small>{device.device_code}{device.location ? ` · ${device.location}` : ""}</small></div>
          <span>{device.has_key ? `Khóa ${device.key_prefix}…` : "Chưa cấp khóa"}</span>
          <span>Hoạt động gần nhất: {formatTime(device.last_seen_at)}</span>
          <span className={`badge ${device.status === "active" ? "success" : "danger"}`}>{device.status === "active" ? "Đang bật" : "Đã tắt"}</span>
          <div className="row-actions">
            <button type="button" className="secondary" disabled={busy} onClick={() => setConfirmRotate(device)}>
              {device.has_key ? "Cấp lại khóa" : "Cấp khóa"}</button>
            <button type="button" className="secondary danger-text" disabled={busy}
              onClick={() => void run(() => deviceApi.update(device.id, { status: device.status === "active" ? "disabled" : "active" }))}>
              {device.status === "active" ? "Vô hiệu hóa" : "Bật lại"}</button>
          </div>
        </div>)}</div>}
    </section>
  </>;
}
