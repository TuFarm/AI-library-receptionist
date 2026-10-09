import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "../../components/ui";
import { getAdminSession } from "../../services/adminAccess";
import { adminUserApi, ApiClientError, type AdminUser, type FaceIdErasure } from "../../services/apiClient";

const emptyForm = { student_code: "", full_name: "", email: "", faculty: "", major: "", admission_year: "" };
type UserForm = typeof emptyForm;
type FieldErrors = Partial<Record<keyof UserForm, string>>;

function userToForm(user: AdminUser): UserForm {
  return {
    student_code: user.student_code ?? "",
    full_name: user.full_name,
    email: user.email ?? "",
    faculty: user.faculty ?? "",
    major: user.major ?? "",
    admission_year: user.admission_year?.toString() ?? "",
  };
}

/** Client-side validation — mirrors backend Pydantic rules. */
export function validateForm(form: UserForm, isEdit: boolean): FieldErrors {
  const errors: FieldErrors = {};
  if (!isEdit && !form.student_code.trim()) errors.student_code = "Mã sinh viên là bắt buộc";
  else if (form.student_code && !/^[A-Za-z0-9_-]{3,50}$/.test(form.student_code.trim())) errors.student_code = "Mã sinh viên chỉ chứa chữ cái, số, gạch ngang (3–50 ký tự)";
  if (form.full_name.trim().length < 2) errors.full_name = "Họ và tên tối thiểu 2 ký tự";
  if (form.full_name.trim().length > 255) errors.full_name = "Họ và tên tối đa 255 ký tự";
  if (form.email.trim().length > 320) errors.email = "Email tối đa 320 ký tự";
  if (form.faculty.trim().length > 150) errors.faculty = "Khoa tối đa 150 ký tự";
  if (form.major.trim().length > 150) errors.major = "Ngành tối đa 150 ký tự";
  if (!isEdit && !form.email.trim()) errors.email = "Email là bắt buộc";
  else if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email.trim())) errors.email = "Email không hợp lệ";
  if (form.admission_year) {
    const year = Number(form.admission_year);
    if (!Number.isInteger(year) || year < 1990 || year > new Date().getFullYear() + 1) errors.admission_year = "Năm nhập học từ 1990 đến năm sau";
  }
  return errors;
}

const FIELD_LABELS: Record<string, string> = {
  student_code: "Mã sinh viên", full_name: "Họ và tên", email: "Email",
  faculty: "Khoa", major: "Ngành", admission_year: "Năm nhập học",
};

/** The admin must give a reason and confirm the student is at the desk (mirrors the backend rule). */
export function canEraseFaceId(reason: string, studentPresent: boolean): boolean {
  return studentPresent && reason.trim().length >= 5 && reason.trim().length <= 500;
}

function FaceIdEraseDialog({ user, onClose, onErased }: { user: AdminUser; onClose: () => void; onErased: () => void }) {
  const [reason, setReason] = useState("");
  const [present, setPresent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<FaceIdErasure[] | null>(null);
  useEffect(() => { void adminUserApi.faceIdErasures(user.id).then(setHistory).catch(() => setHistory([])); }, [user.id]);
  async function erase() {
    if (busy || !canEraseFaceId(reason, present)) return;
    setBusy(true); setError("");
    try { await adminUserApi.eraseFaceId(user.id, reason.trim()); onErased(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể xóa Face ID."); setBusy(false); }
  }
  return <div className="modal-overlay" onClick={() => { if (!busy) onClose(); }}><div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="face-erase-title" onClick={e => e.stopPropagation()}>
    <h3 id="face-erase-title">Xóa Face ID của {user.full_name}</h3>
    <p>Chỉ dùng khi sinh viên đến quầy yêu cầu (ví dụ kiosk không còn nhận ra họ). Thao tác này xóa vĩnh viễn mẫu khuôn mặt và được ghi lại kèm tên tài khoản của bạn.</p>
    <label className="field">Lý do<textarea maxLength={500} value={reason} disabled={busy} onChange={e => setReason(e.target.value)} placeholder="VD: Kiosk không còn nhận ra, SV mang thẻ đến quầy"/></label>
    <label className="checkbox-row"><input type="checkbox" checked={present} disabled={busy} onChange={e => setPresent(e.target.checked)}/> Sinh viên có mặt tại quầy và tôi đã kiểm tra thẻ sinh viên</label>
    {history && history.length > 0 && <div className="face-erase-history"><strong>Lịch sử xóa</strong><ul>{history.map(row => <li key={row.id}>
      {new Date(row.created_at).toLocaleString("vi-VN")} · {row.source === "ADMIN" ? `quản trị viên ${row.staff_username ?? "?"}` : "sinh viên tự xóa tại kiosk"}{row.reason ? ` · ${row.reason}` : ""}</li>)}</ul></div>}
    {error && <p role="alert">{error}</p>}
    <div className="modal-actions">
      <button disabled={busy} className="secondary" onClick={onClose}>Hủy</button>
      <button disabled={busy || !canEraseFaceId(reason, present)} className="danger" onClick={() => void erase()}>{busy ? "Đang xóa…" : "Xóa Face ID"}</button>
    </div>
  </div></div>;
}

export default function UserManagementPage() {
  const isAdmin = getAdminSession()?.role !== "librarian";
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const pageSize = 20;
  const requestVersion = useRef(0);
  const [form, setForm] = useState(emptyForm);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [erasingFaceId, setErasingFaceId] = useState<AdminUser | null>(null);
  const busy = saving || deleting;
  const messageTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(messageTimer.current), []);

  function showMessage(msg: string) {
    setMessage(msg);
    clearTimeout(messageTimer.current);
    messageTimer.current = setTimeout(() => setMessage(""), 4000);
  }

  const load = useCallback((term: string, currentPage: number) => {
    const version = ++requestVersion.current;
    setLoading(true);
    setError("");
    void adminUserApi.list(term, currentPage * pageSize, pageSize)
      .then(result => { if (version === requestVersion.current) { setUsers(result.items); setTotal(result.total); } })
      .catch((reason: Error) => { if (version === requestVersion.current) { setUsers([]); setError(reason.message); } })
      .finally(() => { if (version === requestVersion.current) setLoading(false); });
  }, []);
  useEffect(() => {
    load(search, page);
    return () => { requestVersion.current++; };
  }, [load, search, page]);

  function submitSearch(event: FormEvent) {
    event.preventDefault();
    const term = query.trim();
    if (term === search && page === 0) load(term, 0);
    else { setSearch(term); setPage(0); }
  }

  async function saveUser(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const errors = validateForm(form, !!editingId);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setSaving(true); setError("");
    const payload = {
      ...form,
      faculty: form.faculty || null,
      major: form.major || null,
      admission_year: form.admission_year ? Number(form.admission_year) : null,
    };
    try {
      if (editingId) {
        await adminUserApi.update(editingId, payload);
        showMessage("Đã cập nhật hồ sơ người dùng.");
      } else {
        await adminUserApi.create(payload);
        showMessage("Đã tạo hồ sơ người dùng.");
      }
      setForm(emptyForm); setEditingId(null); setFieldErrors({});
      if (page === 0) load(search, 0); else setPage(0);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể lưu hồ sơ.");
      if (reason instanceof ApiClientError) setFieldErrors(reason.fieldErrors);
    } finally { setSaving(false); }
  }

  async function handleDelete(userId: string) {
    if (busy) return;
    setDeleting(true); setError(""); setMessage("");
    try {
      await adminUserApi.delete(userId);
      showMessage("Đã xóa hồ sơ người dùng.");
      if (editingId === userId) { setEditingId(null); setForm(emptyForm); }
      setConfirmDelete(null);
      if (users.length === 1 && page > 0) setPage(page - 1);
      else load(search, page);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể xóa hồ sơ.");
    } finally { setDeleting(false); }
  }

  function startEdit(user: AdminUser) { setEditingId(user.id); setForm(userToForm(user)); setError(""); setFieldErrors({}); }
  function cancelEdit() { setEditingId(null); setForm(emptyForm); setFieldErrors({}); }

  return <><PageHeader title="Quản lý người dùng" description="Quản lý hồ sơ người dùng không sinh trắc học."/>
    <section className="panel form-panel"><div className="panel-head"><h2>{editingId ? "Chỉnh sửa hồ sơ" : "Thêm hồ sơ"}</h2>{editingId && <button type="button" disabled={busy} className="secondary" onClick={cancelEdit}>Hủy chỉnh sửa</button>}</div>
      <form className="admin-form" onSubmit={saveUser}>
        {(Object.keys(emptyForm) as (keyof UserForm)[]).map(key => <label key={key} className={fieldErrors[key] ? "field-error" : ""}>
          {FIELD_LABELS[key]}{["student_code", "full_name", "email"].includes(key) && !editingId ? " *" : ""}
          <input
            required={!editingId && ["student_code", "full_name", "email"].includes(key)}
            type={key === "admission_year" ? "number" : key === "email" ? "email" : "text"}
            value={form[key]}
            onChange={event => { setForm(current => ({ ...current, [key]: event.target.value })); setFieldErrors(prev => { const next = { ...prev }; delete next[key]; return next; }); }}
            disabled={busy}
            aria-invalid={!!fieldErrors[key]}
          />
          {fieldErrors[key] && <small className="validation-error">{fieldErrors[key]}</small>}
        </label>)}
        <button disabled={busy}>{saving ? "Đang lưu…" : editingId ? "Lưu thay đổi" : "Tạo hồ sơ"}</button>
      </form>
    </section>
    {message && <div className="tip" role="status"><span>✓</span><p>{message}</p></div>}
    {error && <div className="tip error" role="alert"><span>!</span><p>{error}</p><button disabled={busy || loading} onClick={() => load(search, page)}>Tải lại danh sách</button></div>}
    <section className="panel table-panel"><div className="panel-head"><h2>Danh sách hồ sơ ({total})</h2><form onSubmit={submitSearch} className="table-search"><input disabled={busy} maxLength={100} value={query} onChange={event => setQuery(event.target.value)} placeholder="Tìm tên, mã SV, email" aria-label="Tìm người dùng"/><button disabled={busy}>Tìm</button></form></div>
      {loading ? <div className="loading-state">Đang tải danh sách…</div> : users.length === 0 ? <div className="empty-state"><strong>Chưa có hồ sơ phù hợp</strong><p>Thử từ khóa khác hoặc tạo hồ sơ mới.</p></div> : <div className="data-table">{users.map(user => <div className="user-row" key={user.id}>
        <div><strong>{user.full_name}</strong><small>{user.student_code} · {user.email}</small></div>
        <span>{user.faculty ?? "—"} · {user.major ?? "—"}</span>
        <span>{user.admission_year ?? "—"}{user.student_year ? ` · Năm ${user.student_year}` : ""}</span>
        <span className={`badge ${user.account_status === "active" ? "success" : "danger"}`}>{user.account_status === "active" ? "Hoạt động" : user.account_status}</span>
        <div className="row-actions">
          <button type="button" disabled={busy} className="secondary user-edit-button" onClick={() => startEdit(user)}>Sửa</button>
          {isAdmin && user.has_face_id && <button type="button" disabled={busy} className="secondary danger-text" onClick={() => setErasingFaceId(user)}>Xóa Face ID</button>}
          <button type="button" disabled={busy} className="secondary danger-text" onClick={() => setConfirmDelete(user.id)}>Xóa</button>
        </div>
      </div>)}</div>}
      {total > pageSize && <nav className="panel-head" aria-label="Phân trang người dùng">
        <button disabled={loading || busy || page === 0} onClick={() => setPage(value => value - 1)}>Trang trước</button>
        <span>Trang {page + 1} / {Math.ceil(total / pageSize)}</span>
        <button disabled={loading || busy || (page + 1) * pageSize >= total} onClick={() => setPage(value => value + 1)}>Trang sau</button>
      </nav>}
    </section>
    {erasingFaceId && <FaceIdEraseDialog user={erasingFaceId} onClose={() => setErasingFaceId(null)}
      onErased={() => { setErasingFaceId(null); showMessage("Đã xóa Face ID. Sinh viên có thể đăng ký lại tại kiosk."); load(search, page); }}/>}
    {/* Confirm delete dialog */}
    {confirmDelete && <div className="modal-overlay" onClick={() => { if (!deleting) setConfirmDelete(null); }}><div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-title" onClick={e => e.stopPropagation()}>
      <h3 id="delete-title">Xác nhận xóa</h3>
      <p>Bạn có chắc muốn xóa hồ sơ người dùng này? Thao tác này sẽ vô hiệu hóa tài khoản.</p>
      <div className="modal-actions">
        <button disabled={deleting} className="secondary" onClick={() => setConfirmDelete(null)}>Hủy</button>
        <button disabled={deleting} className="danger" onClick={() => handleDelete(confirmDelete)}>{deleting ? "Đang xóa…" : "Xóa"}</button>
      </div>
      {error && <p role="alert">{error}</p>}
    </div></div>}
  </>;
}
