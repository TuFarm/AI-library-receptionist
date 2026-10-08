import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { PageHeader } from "../../components/ui";
import { formatCitation } from "../../components/kiosk/ChatBubble";
import { conversationAdminApi, type ConversationDetail, type ConversationSummary } from "../../services/apiClient";

const PERIOD_OPTIONS = [7, 14, 30, 90] as const;
const PAGE_SIZE = 20;

export function formatTime(value: string): string {
  return new Date(value).toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

/** "2/3 có nguồn" style label; conversations without AI answers have none. */
export function groundedLabel(item: Pick<ConversationSummary, "answer_count" | "grounded_count">): [string, string] {
  if (item.answer_count === 0) return ["Chưa có trả lời", "warning"];
  if (item.grounded_count === item.answer_count) return ["Có nguồn", "success"];
  return [`${item.answer_count - item.grounded_count}/${item.answer_count} không có nguồn`, "danger"];
}

export default function ConversationLogsPage() {
  const [items, setItems] = useState<ConversationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [days, setDays] = useState<number>(7);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [ungrounded, setUngrounded] = useState(false);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<ConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const version = useRef(0);

  const load = useCallback(() => {
    const current = ++version.current;
    setLoading(true); setError("");
    void conversationAdminApi.list({ days, search, ungrounded, offset: page * PAGE_SIZE, limit: PAGE_SIZE })
      .then(result => { if (current === version.current) { setItems(result.items); setTotal(result.total); } })
      .catch((reason: Error) => { if (current === version.current) { setItems([]); setError(reason.message); } })
      .finally(() => { if (current === version.current) setLoading(false); });
  }, [days, search, ungrounded, page]);
  useEffect(() => { load(); return () => { version.current++; }; }, [load]);

  function submitSearch(event: FormEvent) { event.preventDefault(); setSearch(query.trim()); setPage(0); }

  async function open(id: string) {
    if (detail?.id === id) { setDetail(null); return; }
    setDetailLoading(true); setError("");
    try { setDetail(await conversationAdminApi.get(id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể tải hội thoại."); }
    finally { setDetailLoading(false); }
  }

  return <><PageHeader eyebrow="NHẬT KÝ" title="Hội thoại" description="Xem bạn đọc đã hỏi gì và trợ lý trả lời dựa trên tài liệu nào. Lọc câu trả lời không có nguồn để biết cần bổ sung tài liệu gì."
    action={<div className="admin-report-actions">{PERIOD_OPTIONS.map(value => <button key={value} className={value === days ? "" : "secondary"} onClick={() => { setDays(value); setPage(0); }}>{value} ngày</button>)}</div>}/>
    {error && <div className="tip error" role="alert"><span>!</span><p>{error}</p><button disabled={loading} onClick={load}>Thử lại</button></div>}
    <div className="conversation-layout">
      <section className="panel table-panel"><div className="panel-head"><h2>Phiên hội thoại ({total})</h2>
        <form className="table-search" onSubmit={submitSearch}><input maxLength={200} value={query} onChange={event => setQuery(event.target.value)} placeholder="Tìm trong nội dung" aria-label="Tìm hội thoại"/><button>Tìm</button></form></div>
        <label className="filter-toggle"><input type="checkbox" checked={ungrounded} onChange={event => { setUngrounded(event.target.checked); setPage(0); }}/> Chỉ hiện hội thoại có câu trả lời không có nguồn</label>
        {loading ? <div className="loading-state">Đang tải hội thoại…</div> : items.length === 0
          ? <div className="empty-state"><strong>Không có hội thoại</strong><p>{ungrounded ? "Mọi câu trả lời trong khoảng này đều có nguồn." : "Chưa có bạn đọc nào hỏi trợ lý trong khoảng thời gian này."}</p></div>
          : <div className="data-table">{items.map(item => {
            const [label, tone] = groundedLabel(item);
            return <button type="button" key={item.id} className={`log-row conversation-row${detail?.id === item.id ? " selected" : ""}`} onClick={() => void open(item.id)}>
              <div className="avatar small">{item.visitor?.full_name[0] ?? "?"}</div>
              <div><strong>{item.visitor ? `${item.visitor.full_name}${item.visitor.student_code ? ` · ${item.visitor.student_code}` : ""}` : "Khách chưa nhận diện"}</strong>
                <small>{item.first_question ?? "Chưa có câu hỏi"}</small></div>
              <time>{formatTime(item.started_at)}<small>{item.device_code ?? "—"} · {item.message_count} tin</small></time>
              <span className={`badge ${tone}`}>{label}</span>
            </button>;
          })}</div>}
        {total > PAGE_SIZE && <nav className="panel-head" aria-label="Phân trang hội thoại">
          <button disabled={loading || page === 0} onClick={() => setPage(value => value - 1)}>Trang trước</button>
          <span>Trang {page + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
          <button disabled={loading || (page + 1) * PAGE_SIZE >= total} onClick={() => setPage(value => value + 1)}>Trang sau</button>
        </nav>}
      </section>
      <section className="panel conversation-detail" aria-live="polite">
        {detailLoading ? <div className="loading-state">Đang tải nội dung…</div> : !detail
          ? <div className="empty-state"><strong>Chọn một hội thoại</strong><p>Nội dung, nguồn trích dẫn và thời gian phản hồi sẽ hiện ở đây.</p></div>
          : <><div className="panel-head"><h2>{detail.visitor?.full_name ?? "Khách chưa nhận diện"}</h2><small>{formatTime(detail.started_at)}</small></div>
            <ol className="transcript">{detail.messages.map(message => <li key={message.id} className={message.sender_type === "USER" ? "user" : "assistant"}>
              <small>{message.sender_type === "USER" ? `Bạn đọc · ${message.input_method === "VOICE" ? "giọng nói" : "bàn phím"}` : "Trợ lý"} · {formatTime(message.time)}</small>
              <p>{message.text}</p>
              {message.ai && <div className="transcript-meta">
                <span className={`badge ${message.ai.grounded ? "success" : "danger"}`}>{message.ai.grounded ? "Có nguồn" : "Không có nguồn"}</span>
                {message.ai.citations.length > 0 && <span>Nguồn: {[...new Set(message.ai.citations.map(formatCitation))].join(" · ")}</span>}
                <span>{message.ai.model_name ?? "—"}{message.ai.latency_ms != null ? ` · ${message.ai.latency_ms} ms` : ""}{message.ai.status !== "completed" ? ` · ${message.ai.status}` : ""}</span>
              </div>}
            </li>)}</ol></>}
      </section>
    </div>
  </>;
}
