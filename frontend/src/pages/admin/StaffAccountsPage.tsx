import { FormEvent, useCallback, useEffect, useState } from "react";
import { PageHeader } from "../../components/ui";
import { ApiClientError, staffApi, type StaffAccount } from "../../services/apiClient";
import { getAdminSession, type StaffRole } from "../../services/adminAccess";

const ROLE_LABELS: Record<StaffRole, string> = { admin: "Quản trị viên", librarian: "Thủ thư" };
const emptyForm = { username: "", full_name: "", role: "librarian" as StaffRole, password: "" };

export function validateStaffForm(form: typeof emptyForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!/^[a-z0-9._-]{3,100}$/.test(form.username.trim().toLowerCase())) errors.username = "Tên đăng nhập 3–100 ký tự: chữ thường, số, . _ -";
  if (!form.full_name.trim()) errors.full_name = "Vui lòng nhập họ tên.";
  if (form.password.length < 8 || form.password.length > 128 || !form.password.trim()) errors.password = "Mật khẩu cần từ 8 đến 128 ký tự.";
  return errors;
}

export default function StaffAccountsPage() {
  const [accounts, setAccounts] = useState<StaffAccount[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [resetFor, setResetFor] = useState<StaffAccount | null>(null);
  const [resetPassword, setResetPassword] = useState("");
  const myId = getAdminSession()?.id;

  const load = useCallback(() => {
    setLoading(true); setError("");
    staffApi.list().then(setAccounts).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); setMessage(success); load(); return true; }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể thực hiện thao tác.");
      if (reason instanceof ApiClientError) setErrors(reason.fieldErrors);
      return false;
    } finally { setBusy(false); }
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    const invalid = validateStaffForm(form);
    setErrors(invalid);
    if (Object.keys(invalid).length) return;
    if (await run(() => staffApi.create({ ...form, username: form.username.trim().toLowerCase(), full_name: form.full_name.trim() }),
      "Đã tạo tài khoản nhân viên.")) setForm(emptyForm);
  }

  async function submitReset(event: FormEvent) {
    event.preventDefault();
    if (!resetFor) return;
    if (resetPassword.length < 8 || resetPassword.length > 128 || !resetPassword.trim()) { setError("Mật khẩu mới cần từ 8 đến 128 ký tự."); return; }
    if (await run(() => staffApi.resetPassword(resetFor.id, resetPassword), `Đã đặt lại mật khẩu cho ${resetFor.username}.`)) {
      setResetFor(null); setResetPassword("");
    }
  }

  return <><PageHeader eyebrow="PHÂN QUYỀN" title="Tài khoản nhân viên"
      description="Quản trị viên quản lý tài khoản, thiết bị và dữ liệu sinh trắc học. Thủ thư xem báo cáo và quản lý hồ sơ người dùng."/>
    <section className="panel form-panel"><div className="panel-head"><h2>Thêm tài khoản</h2></div>
      <form className="admin-form" onSubmit={create} noValidate>
        <label className={errors.username ? "field-error" : ""}>Tên đăng nhập *
          <input autoComplete="off" maxLength={100} value={form.username} disabled={busy} aria-invalid={!!errors.username}
            onChange={event => setForm(value => ({ ...value, username: event.target.value }))}/>
          {errors.username && <small className="validation-error">{errors.username}</small>}</label>
        <label className={errors.full_name ? "field-error" : ""}>Họ và tên *
          <input maxLength={255} value={form.full_name} disabled={busy} aria-invalid={!!errors.full_name}
            onChange={event => setForm(value => ({ ...value, full_name: event.target.value }))}/>
          {errors.full_name && <small className="validation-error">{errors.full_name}</small>}</label>
        <label>Vai trò
          <select value={form.role} disabled={busy} onChange={event => setForm(value => ({ ...value, role: event.target.value as StaffRole }))}>
            <option value="librarian">{ROLE_LABELS.librarian}</option><option value="admin">{ROLE_LABELS.admin}</option>
          </select></label>
        <label className={errors.password ? "field-error" : ""}>Mật khẩu ban đầu *
          <input type="password" autoComplete="new-password" maxLength={128} value={form.password} disabled={busy} aria-invalid={!!errors.password}
            onChange={event => setForm(value => ({ ...value, password: event.target.value }))}/>
          {errors.password && <small className="validation-error">{errors.password}</small>}</label>
        <button disabled={busy}>{busy ? "Đang lưu…" : "Tạo tài khoản"}</button>
      </form>
    </section>
    {message && <div className="tip" role="status"><span>✓</span><p>{message}</p></div>}
    {error && <div className="tip error" role="alert"><span>!</span><p>{error}</p></div>}
    {resetFor && <section className="panel form-panel"><div className="panel-head"><h2>Đặt lại mật khẩu: {resetFor.username}</h2>
      <button type="button" className="secondary" disabled={busy} onClick={() => setResetFor(null)}>Hủy</button></div>
      <p>Mọi phiên đăng nhập của tài khoản này sẽ bị thu hồi.</p>
      <form className="admin-form" onSubmit={submitReset} noValidate>
        <label>Mật khẩu mới<input type="password" autoComplete="new-password" maxLength={128} value={resetPassword} disabled={busy}
          onChange={event => setResetPassword(event.target.value)}/></label>
        <button disabled={busy}>Đặt lại mật khẩu</button>
      </form></section>}
    <section className="panel table-panel"><div className="panel-head"><h2>Danh sách tài khoản ({accounts.length})</h2></div>
      {loading ? <div className="loading-state">Đang tải…</div> : <div className="data-table">{accounts.map(account => <div className="user-row" key={account.id}>
        <div><strong>{account.full_name}</strong><small>{account.username}{account.id === myId ? " · bạn" : ""}</small></div>
        <span>{ROLE_LABELS[account.role]}</span>
        <span>{account.last_login_at ? `Đăng nhập ${new Date(account.last_login_at).toLocaleString("vi-VN")}` : "Chưa đăng nhập"}</span>
        <span className={`badge ${!account.is_active ? "danger" : account.locked ? "warning" : "success"}`}>
          {!account.is_active ? "Vô hiệu" : account.locked ? "Tạm khóa" : "Hoạt động"}</span>
        <div className="row-actions">
          <button type="button" className="secondary" disabled={busy || account.id === myId}
            onClick={() => void run(() => staffApi.update(account.id, { role: account.role === "admin" ? "librarian" : "admin" }), "Đã đổi vai trò.")}>
            {account.role === "admin" ? "Chuyển thành thủ thư" : "Cấp quyền quản trị"}</button>
          <button type="button" className="secondary" disabled={busy} onClick={() => { setResetFor(account); setResetPassword(""); }}>Đặt lại mật khẩu</button>
          <button type="button" className="secondary danger-text" disabled={busy || account.id === myId}
            onClick={() => void run(() => staffApi.update(account.id, { is_active: !account.is_active }),
              account.is_active ? "Đã vô hiệu hóa tài khoản." : "Đã kích hoạt lại tài khoản.")}>
            {account.is_active ? "Vô hiệu hóa" : "Kích hoạt"}</button>
        </div>
      </div>)}</div>}
    </section>
  </>;
}
