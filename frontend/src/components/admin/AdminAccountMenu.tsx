import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { adminApi, ApiClientError } from "../../services/apiClient";
import { clearAdminSession } from "../../services/adminAccess";

export default function AdminAccountMenu({ onSignOut }: { onSignOut: () => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [fields, setFields] = useState({ current_password: "", new_password: "", confirmation: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    function outside(event: PointerEvent) { if (!root.current?.contains(event.target as Node)) setOpen(false); }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, []);
  useEffect(() => { if (open) root.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus(); }, [open]);

  function menuKeys(event: KeyboardEvent) {
    const items = Array.from(root.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === "Escape") { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault(); items[(index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
    }
    if (event.key === "Tab") setOpen(false);
  }

  async function logout() {
    setBusy(true); setError("");
    try { await onSignOut(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể đăng xuất. Vui lòng thử lại."); }
    finally { setBusy(false); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const invalid: Record<string, string> = {};
    if (!fields.current_password) invalid.current_password = "Vui lòng nhập mật khẩu hiện tại.";
    if (fields.new_password.length < 8 || fields.new_password.length > 128 || !fields.new_password.trim()) invalid.new_password = "Mật khẩu mới cần từ 8 đến 128 ký tự.";
    else if (fields.new_password === fields.current_password) invalid.new_password = "Mật khẩu mới phải khác mật khẩu hiện tại.";
    if (fields.confirmation !== fields.new_password) invalid.confirmation = "Mật khẩu xác nhận không khớp.";
    setErrors(invalid); setError("");
    if (Object.keys(invalid).length) return;
    setBusy(true);
    try {
      await adminApi.changePassword(fields.current_password, fields.new_password);
      dialog.current?.close(); clearAdminSession();
      window.dispatchEvent(new CustomEvent("admin-session-expired", { detail: { message: "Đã đổi mật khẩu thành công. Vui lòng đăng nhập lại." } }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể đổi mật khẩu.");
      if (reason instanceof ApiClientError) setErrors(reason.fieldErrors);
    } finally { setBusy(false); }
  }

  return <div className="admin-account" ref={root}>
    <button type="button" className="avatar admin-account-trigger" ref={trigger} aria-label="Quản lý tài khoản"
      aria-haspopup="menu" aria-expanded={open} aria-controls="admin-account-menu"
      onClick={() => { setError(""); setOpen(value => !value); }}>QT</button>
    {open && <div id="admin-account-menu" role="menu" aria-label="Quản lý tài khoản" className="admin-account-menu" onKeyDown={menuKeys}>
      <strong>Quản lý tài khoản</strong>
      <button role="menuitem" tabIndex={-1} disabled={busy} onClick={() => {
        setOpen(false); setError(""); setErrors({}); setFields({ current_password: "", new_password: "", confirmation: "" }); dialog.current?.showModal();
      }}>Đổi mật khẩu</button>
      <button role="menuitem" tabIndex={-1} className="admin-menu-logout" disabled={busy} onClick={() => void logout()}>{busy ? "Đang đăng xuất…" : "Đăng xuất"}</button>
      {error && <p role="alert">{error}</p>}
    </div>}
    <dialog ref={dialog} className="admin-password-dialog" aria-labelledby="password-title" onCancel={event => { if (busy) event.preventDefault(); }}>
      <h2 id="password-title">Đổi mật khẩu</h2>
      <p>Sau khi đổi mật khẩu, bạn sẽ cần đăng nhập lại trên các thiết bị.</p>
      <form onSubmit={submit} noValidate>
        {([['current_password', 'Mật khẩu hiện tại'], ['new_password', 'Mật khẩu mới'], ['confirmation', 'Xác nhận mật khẩu mới']] as const).map(([name, label]) =>
          <label key={name}>{label}<input type="password" autoComplete={name === "current_password" ? "current-password" : "new-password"}
            aria-label={label} aria-describedby={errors[name] ? `change-${name}-error` : undefined}
            maxLength={name === "current_password" ? 1024 : 128} value={fields[name]} disabled={busy} aria-invalid={!!errors[name]}
            onChange={event => { setFields(value => ({ ...value, [name]: event.target.value })); setErrors(value => ({ ...value, [name]: "" })); }}/>
            {errors[name] && <small id={`change-${name}-error`} className="validation-error">{errors[name]}</small>}
          </label>)}
        {error && <p role="alert">{error}</p>}
        <div className="modal-actions"><button type="button" className="secondary" disabled={busy} onClick={() => { dialog.current?.close(); trigger.current?.focus(); }}>Hủy</button>
          <button disabled={busy}>{busy ? "Đang lưu…" : "Lưu mật khẩu"}</button></div>
      </form>
    </dialog>
  </div>;
}
