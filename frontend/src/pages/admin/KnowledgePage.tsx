import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "../../components/ui";
import { formatCitation } from "../../components/kiosk/ChatBubble";
import { knowledgeApi, type KnowledgeChunkPreview, type KnowledgeDocument, type KnowledgeSearchHit } from "../../services/apiClient";

export const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".xlsx", ".txt", ".md", ".csv"];
const DEFAULT_MAX_MB = 20;

/** Mirrors the backend checks so staff get instant feedback before uploading. */
export function validateUpload(file: { name: string; size: number } | null, maxMb = DEFAULT_MAX_MB): string {
  if (!file) return "Vui lòng chọn tệp cần tải lên.";
  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  if (!file.name.includes(".") || !ACCEPTED_EXTENSIONS.includes(extension)) return "Chỉ hỗ trợ PDF, Word (.docx), Excel (.xlsx), TXT, Markdown hoặc CSV.";
  if (file.size === 0) return "Tệp rỗng.";
  if (file.size > maxMb * 1024 * 1024) return `Tệp vượt quá ${maxMb} MB.`;
  return "";
}

export function formatSize(bytes: number | null): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const STATUS: Record<KnowledgeDocument["status"], [string, string]> = {
  processed: ["Đã xử lý", "success"], processing: ["Đang xử lý", "warning"], failed: ["Lỗi xử lý", "danger"],
};

export default function KnowledgePage() {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [maxMb, setMaxMb] = useState(DEFAULT_MAX_MB);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileTitle, setFileTitle] = useState("");
  const [fileError, setFileError] = useState("");
  const [textTitle, setTextTitle] = useState("");
  const [textContent, setTextContent] = useState("");
  const [textError, setTextError] = useState("");
  const [preview, setPreview] = useState<{ id: string; chunks: KnowledgeChunkPreview[] } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<KnowledgeDocument | null>(null);
  const [question, setQuestion] = useState("");
  const [hits, setHits] = useState<KnowledgeSearchHit[] | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const requestVersion = useRef(0);

  const load = useCallback((term: string) => {
    const version = ++requestVersion.current;
    setLoading(true); setError("");
    void knowledgeApi.list(term)
      .then(result => { if (version === requestVersion.current) { setDocuments(result.items); setMaxMb(result.max_upload_mb); } })
      .catch((reason: Error) => { if (version === requestVersion.current) { setDocuments([]); setError(reason.message); } })
      .finally(() => { if (version === requestVersion.current) setLoading(false); });
  }, []);
  useEffect(() => { load(search); return () => { requestVersion.current++; }; }, [load, search]);

  async function run<T>(action: () => Promise<T>, success: (result: T) => string): Promise<boolean> {
    if (busy) return false;
    setBusy(true); setError(""); setMessage("");
    try { const result = await action(); setMessage(success(result)); load(search); return true; }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể thực hiện thao tác."); return false; }
    finally { setBusy(false); }
  }
  const outcome = (document: KnowledgeDocument, done: string) => document.status === "failed"
    ? `“${document.title}” đã được lưu nhưng không xử lý được: ${document.processing_error ?? "lỗi không xác định"}`
    : `${done} “${document.title}” (${document.chunk_count} đoạn).`;

  async function upload(event: FormEvent) {
    event.preventDefault();
    const problem = validateUpload(file, maxMb);
    setFileError(problem);
    if (problem || !file) return;
    if (await run(() => knowledgeApi.upload(file, fileTitle), document => outcome(document, "Đã tải lên"))) {
      setFile(null); setFileTitle("");
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  async function addText(event: FormEvent) {
    event.preventDefault();
    const problem = !textTitle.trim() ? "Vui lòng nhập tiêu đề." : !textContent.trim() ? "Vui lòng nhập nội dung." : "";
    setTextError(problem);
    if (problem) return;
    if (await run(() => knowledgeApi.createText(textTitle, textContent), document => outcome(document, "Đã thêm"))) {
      setTextTitle(""); setTextContent("");
    }
  }

  async function togglePreview(document: KnowledgeDocument) {
    if (preview?.id === document.id) { setPreview(null); return; }
    setError("");
    try { const detail = await knowledgeApi.get(document.id); setPreview({ id: document.id, chunks: detail.chunks }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể tải nội dung tài liệu."); }
  }

  async function testRetrieval(event: FormEvent) {
    event.preventDefault();
    if (!question.trim() || busy) return;
    setBusy(true); setError("");
    try { setHits(await knowledgeApi.search(question)); }
    catch (reason) { setHits(null); setError(reason instanceof Error ? reason.message : "Không thể tìm kiếm."); }
    finally { setBusy(false); }
  }

  const active = documents.filter(document => document.is_active && document.status === "processed").length;
  return <><PageHeader eyebrow="QUẢN TRỊ TRI THỨC" title="Tài liệu tri thức"
    description={`Trợ lý AI chỉ trả lời thông tin chính thức dựa trên các tài liệu đang hoạt động (${active} tài liệu) và luôn kèm nguồn.`}/>
    <div className="knowledge-grid">
      <section className="panel form-panel"><div className="panel-head"><h2>Tải tệp lên</h2><small>Tối đa {maxMb} MB</small></div>
        <form className="admin-form single" onSubmit={upload}>
          <label className={fileError ? "field-error" : ""}>Tệp tài liệu *
            <input ref={fileInput} type="file" accept={ACCEPTED_EXTENSIONS.join(",")} disabled={busy}
              onChange={event => { setFile(event.target.files?.[0] ?? null); setFileError(""); }} aria-invalid={!!fileError}/>
            <small>PDF có lớp chữ, Word (.docx), Excel (.xlsx), TXT, Markdown, CSV. PDF scan chưa được hỗ trợ.</small>
            {fileError && <small className="validation-error">{fileError}</small>}
          </label>
          <label>Tiêu đề (không bắt buộc)<input maxLength={500} value={fileTitle} disabled={busy} onChange={event => setFileTitle(event.target.value)} placeholder="Mặc định lấy theo tên tệp"/></label>
          <button disabled={busy}>{busy ? "Đang xử lý…" : "Tải lên và xử lý"}</button>
        </form>
      </section>
      <section className="panel form-panel"><div className="panel-head"><h2>Nhập nội dung trực tiếp</h2></div>
        <form className="admin-form single" onSubmit={addText}>
          <label>Tiêu đề *<input maxLength={500} value={textTitle} disabled={busy} onChange={event => { setTextTitle(event.target.value); setTextError(""); }} placeholder="Ví dụ: Giờ mở cửa thư viện"/></label>
          <label className={textError ? "field-error" : ""}>Nội dung *
            <textarea rows={5} maxLength={200000} value={textContent} disabled={busy} onChange={event => { setTextContent(event.target.value); setTextError(""); }}
              placeholder="Thư viện mở cửa từ 7:00 đến 21:00, thứ Hai đến thứ Bảy…" aria-invalid={!!textError}/>
            {textError && <small className="validation-error">{textError}</small>}
          </label>
          <button disabled={busy}>Thêm tài liệu</button>
        </form>
      </section>
    </div>
    {message && <div className="tip" role="status"><span>✓</span><p>{message}</p></div>}
    {error && <div className="tip error" role="alert"><span>!</span><p>{error}</p><button disabled={busy || loading} onClick={() => load(search)}>Tải lại</button></div>}
    <section className="panel"><div className="panel-head"><h2>Thử truy xuất</h2><small>Xem trợ lý sẽ dùng đoạn nào để trả lời</small></div>
      <form className="table-search wide" onSubmit={testRetrieval}>
        <input maxLength={500} value={question} onChange={event => setQuestion(event.target.value)} placeholder="Nhập câu hỏi của bạn đọc, ví dụ: Thư viện mở cửa lúc mấy giờ?" aria-label="Câu hỏi thử"/>
        <button disabled={busy || !question.trim()}>Tìm</button>
      </form>
      {hits && (hits.length === 0
        ? <div className="empty-state"><strong>Không có đoạn phù hợp</strong><p>Trợ lý sẽ trả lời rằng chưa có tài liệu chính thức cho câu hỏi này.</p></div>
        : <ol className="hit-list">{hits.map(hit => <li key={hit.chunk_id}><strong>[{hit.index}] {formatCitation(hit)}</strong><small>điểm {hit.score.toFixed(2)}</small><p>{hit.text}</p></li>)}</ol>)}
    </section>
    <section className="panel table-panel"><div className="panel-head"><h2>Tài liệu ({documents.length})</h2>
      <form className="table-search" onSubmit={event => { event.preventDefault(); if (query.trim() === search) load(search); else setSearch(query.trim()); }}>
        <input maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder="Tìm theo tiêu đề" aria-label="Tìm tài liệu"/><button disabled={busy}>Tìm</button>
      </form></div>
      {loading ? <div className="loading-state">Đang tải tài liệu…</div> : documents.length === 0
        ? <div className="empty-state"><strong>Chưa có tài liệu</strong><p>Tải lên nội quy, giờ mở cửa, hướng dẫn dịch vụ… để trợ lý trả lời chính xác.</p></div>
        : <div className="data-table">{documents.map(document => <div key={document.id}>
          <div className="user-row knowledge-row">
            <div><strong>{document.title}</strong><small>{document.source_type} · {document.original_file_name ?? "—"} · {formatSize(document.file_size)}</small>
              {document.processing_error && <small className="validation-error">{document.processing_error}</small>}</div>
            <span>{document.chunk_count} đoạn</span>
            <span className={`badge ${STATUS[document.status][1]}`}>{STATUS[document.status][0]}</span>
            <span className={`badge ${document.is_active ? "success" : "danger"}`}>{document.is_active ? "Đang dùng" : "Tạm tắt"}</span>
            <div className="row-actions">
              <button type="button" className="secondary" disabled={busy || document.chunk_count === 0} onClick={() => void togglePreview(document)}>{preview?.id === document.id ? "Ẩn" : "Xem"}</button>
              <button type="button" className="secondary" disabled={busy} onClick={() => void run(() => knowledgeApi.update(document.id, { is_active: !document.is_active }),
                updated => updated.is_active ? `Đã bật “${updated.title}”.` : `Đã tạm tắt “${updated.title}”; trợ lý sẽ không dùng tài liệu này.`)}>{document.is_active ? "Tắt" : "Bật"}</button>
              <button type="button" className="secondary" disabled={busy} onClick={() => void run(() => knowledgeApi.reprocess(document.id), updated => outcome(updated, "Đã xử lý lại"))}>Xử lý lại</button>
              <button type="button" className="secondary danger-text" disabled={busy} onClick={() => setConfirmDelete(document)}>Xóa</button>
            </div>
          </div>
          {preview?.id === document.id && <ol className="chunk-preview">{preview.chunks.map(chunk => <li key={chunk.id}>
            <small>Đoạn {chunk.index + 1}{chunk.page_number ? ` · trang ${chunk.page_number}` : ""}{chunk.sheet_name ? ` · ${chunk.sheet_name}` : ""}</small><p>{chunk.text}</p></li>)}</ol>}
        </div>)}</div>}
    </section>
    {confirmDelete && <div className="modal-overlay" onClick={() => { if (!busy) setConfirmDelete(null); }}><div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-knowledge-title" onClick={event => event.stopPropagation()}>
      <h3 id="delete-knowledge-title">Xóa tài liệu?</h3>
      <p>“{confirmDelete.title}” sẽ bị gỡ khỏi kho tri thức và trợ lý không dùng nó nữa. Lịch sử trích dẫn cũ vẫn được giữ.</p>
      <div className="modal-actions">
        <button className="secondary" disabled={busy} onClick={() => setConfirmDelete(null)}>Hủy</button>
        <button className="danger" disabled={busy} onClick={() => void run(() => knowledgeApi.remove(confirmDelete.id), () => `Đã xóa “${confirmDelete.title}”.`).then(() => setConfirmDelete(null))}>{busy ? "Đang xóa…" : "Xóa"}</button>
      </div>
    </div></div>}
  </>;
}
