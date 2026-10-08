import { FormEvent, useCallback, useEffect, useState } from "react";
import { PageHeader } from "../../components/ui";
import { surveyAdminApi, type AdminSurvey, type SurveyInput, type SurveyQuestionType, type SurveyResults } from "../../services/apiClient";

export const QUESTION_TYPES: Record<SurveyQuestionType, string> = { rating: "Chấm điểm 1–5 sao", yes_no: "Có / Không", text: "Trả lời tự do" };
type Form = { survey_name: string; description: string; questions: Array<{ question_text: string; question_type: SurveyQuestionType }> };
const emptyForm = (): Form => ({ survey_name: "", description: "", questions: [{ question_text: "", question_type: "rating" }] });

/** Mirrors the backend schema: name 3–255, description ≤1000, 1–20 questions of 3–500 characters. */
export function validateSurvey(form: Form, editQuestions = true): Record<string, string> {
  const errors: Record<string, string> = {};
  const name = form.survey_name.trim();
  if (name.length < 3 || name.length > 255) errors.survey_name = "Tên khảo sát từ 3 đến 255 ký tự.";
  if (form.description.trim().length > 1000) errors.description = "Mô tả tối đa 1000 ký tự.";
  if (editQuestions) {
    if (form.questions.length === 0 || form.questions.length > 20) errors.questions = "Khảo sát cần từ 1 đến 20 câu hỏi.";
    form.questions.forEach((question, index) => {
      const text = question.question_text.trim();
      if (text.length < 3 || text.length > 500) errors[`question_${index}`] = "Câu hỏi từ 3 đến 500 ký tự.";
    });
  }
  return errors;
}

function Distribution({ values }: { values: Record<string, number> }) {
  const max = Math.max(...Object.values(values), 1);
  return <div className="distribution">{Object.entries(values).map(([label, count]) => <div key={label}>
    <span>{label}</span><i style={{ width: `${(count / max) * 100}%` }}/><b>{count}</b></div>)}</div>;
}

export default function SurveyManagementPage() {
  const [surveys, setSurveys] = useState<AdminSurvey[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [form, setForm] = useState<Form>(emptyForm);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<AdminSurvey | null>(null);
  const [results, setResults] = useState<{ survey: AdminSurvey; data: SurveyResults } | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<AdminSurvey | null>(null);
  const questionsLocked = !!editing && editing.response_count > 0;

  const load = useCallback(() => {
    setLoading(true); setError("");
    void surveyAdminApi.list().then(setSurveys)
      .catch((reason: Error) => { setSurveys([]); setError(reason.message); })
      .finally(() => setLoading(false));
  }, []);
  useEffect(load, [load]);

  async function run<T>(action: () => Promise<T>, success: string, after?: (result: T) => void) {
    if (busy) return;
    setBusy(true); setError(""); setMessage("");
    try { const result = await action(); setMessage(success); after?.(result); load(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể thực hiện thao tác."); }
    finally { setBusy(false); }
  }

  function startEdit(survey: AdminSurvey) {
    setEditing(survey); setErrors({});
    setForm({ survey_name: survey.survey_name, description: survey.description ?? "",
      questions: survey.questions.map(({ question_text, question_type }) => ({ question_text, question_type })) });
  }
  function reset() { setEditing(null); setForm(emptyForm()); setErrors({}); }
  function setQuestion(index: number, patch: Partial<Form["questions"][number]>) {
    setForm(current => ({ ...current, questions: current.questions.map((question, i) => i === index ? { ...question, ...patch } : question) }));
  }
  function move(index: number, offset: number) {
    setForm(current => {
      const questions = [...current.questions]; const target = index + offset;
      if (target < 0 || target >= questions.length) return current;
      [questions[index], questions[target]] = [questions[target], questions[index]];
      return { ...current, questions };
    });
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    const problems = validateSurvey(form, !questionsLocked);
    setErrors(problems);
    if (Object.keys(problems).length) return;
    const payload: SurveyInput = { survey_name: form.survey_name.trim(), description: form.description.trim() || null,
      questions: form.questions.map(question => ({ ...question, question_text: question.question_text.trim() })) };
    if (editing) {
      const { questions, ...meta } = payload;
      await run(() => surveyAdminApi.update(editing.id, questionsLocked ? meta : { ...meta, questions }), "Đã cập nhật khảo sát.", reset);
    } else {
      await run(() => surveyAdminApi.create(payload), "Đã tạo khảo sát. Bấm “Kích hoạt” để hiển thị trên kiosk.", reset);
    }
  }

  async function showResults(survey: AdminSurvey) {
    if (results?.survey.id === survey.id) { setResults(null); return; }
    setError("");
    try { setResults({ survey, data: await surveyAdminApi.results(survey.id) }); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể tải kết quả."); }
  }

  return <><PageHeader eyebrow="PHẢN HỒI BẠN ĐỌC" title="Quản lý khảo sát" description="Kiosk hiển thị khảo sát đang kích hoạt ở cuối mỗi phiên. Chỉ một khảo sát được kích hoạt tại một thời điểm."/>
    <section className="panel form-panel"><div className="panel-head"><h2>{editing ? `Sửa “${editing.survey_name}” (v${editing.version})` : "Tạo khảo sát"}</h2>
      {editing && <button type="button" className="secondary" disabled={busy} onClick={reset}>Hủy chỉnh sửa</button>}</div>
      <form className="admin-form single" onSubmit={save}>
        <label className={errors.survey_name ? "field-error" : ""}>Tên khảo sát *<input maxLength={255} value={form.survey_name} disabled={busy}
          onChange={event => setForm(current => ({ ...current, survey_name: event.target.value }))} aria-invalid={!!errors.survey_name}/>
          {errors.survey_name && <small className="validation-error">{errors.survey_name}</small>}</label>
        <label className={errors.description ? "field-error" : ""}>Mô tả<input maxLength={1000} value={form.description} disabled={busy}
          onChange={event => setForm(current => ({ ...current, description: event.target.value }))} placeholder="Hiển thị dưới tiêu đề trên kiosk"/>
          {errors.description && <small className="validation-error">{errors.description}</small>}</label>
        {questionsLocked && <div className="tip" role="note"><span>i</span><p>Khảo sát đã có {editing.response_count} phản hồi nên câu hỏi bị khóa để giữ ý nghĩa dữ liệu. Dùng “Tạo phiên bản mới” để đổi câu hỏi.</p></div>}
        <fieldset className="question-list" disabled={busy || questionsLocked}><legend>Câu hỏi ({form.questions.length}/20)</legend>
          {form.questions.map((question, index) => <div className={`question-row${errors[`question_${index}`] ? " field-error" : ""}`} key={index}>
            <span>{index + 1}.</span>
            <input aria-label={`Câu hỏi ${index + 1}`} maxLength={500} value={question.question_text} onChange={event => setQuestion(index, { question_text: event.target.value })} placeholder="Nội dung câu hỏi"/>
            <select aria-label={`Loại câu hỏi ${index + 1}`} value={question.question_type} onChange={event => setQuestion(index, { question_type: event.target.value as SurveyQuestionType })}>
              {Object.entries(QUESTION_TYPES).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
            <div className="row-actions">
              <button type="button" className="secondary" onClick={() => move(index, -1)} disabled={index === 0} aria-label="Lên">↑</button>
              <button type="button" className="secondary" onClick={() => move(index, 1)} disabled={index === form.questions.length - 1} aria-label="Xuống">↓</button>
              <button type="button" className="secondary danger-text" onClick={() => setForm(current => ({ ...current, questions: current.questions.filter((_, i) => i !== index) }))} disabled={form.questions.length === 1} aria-label="Xóa câu hỏi">×</button>
            </div>
            {errors[`question_${index}`] && <small className="validation-error">{errors[`question_${index}`]}</small>}
          </div>)}
          {errors.questions && <small className="validation-error">{errors.questions}</small>}
          <button type="button" className="secondary" disabled={form.questions.length >= 20}
            onClick={() => setForm(current => ({ ...current, questions: [...current.questions, { question_text: "", question_type: "rating" }] }))}>＋ Thêm câu hỏi</button>
        </fieldset>
        <button disabled={busy}>{busy ? "Đang lưu…" : editing ? "Lưu thay đổi" : "Tạo khảo sát"}</button>
      </form>
    </section>
    {message && <div className="tip" role="status"><span>✓</span><p>{message}</p></div>}
    {error && <div className="tip error" role="alert"><span>!</span><p>{error}</p><button disabled={busy || loading} onClick={load}>Tải lại</button></div>}
    <section className="panel table-panel"><div className="panel-head"><h2>Danh sách khảo sát ({surveys.length})</h2></div>
      {loading ? <div className="loading-state">Đang tải khảo sát…</div> : surveys.length === 0
        ? <div className="empty-state"><strong>Chưa có khảo sát</strong><p>Kiosk sẽ bỏ qua bước khảo sát cho đến khi có một khảo sát được kích hoạt.</p></div>
        : <div className="data-table">{surveys.map(survey => <div key={survey.id}>
          <div className="user-row survey-row">
            <div><strong>{survey.survey_name} <small className="inline">v{survey.version}</small></strong><small>{survey.description ?? "Không có mô tả"} · {survey.questions.length} câu hỏi</small></div>
            <span>{survey.response_count.toLocaleString("vi-VN")} phản hồi</span>
            <span className={`badge ${survey.active ? "success" : "warning"}`}>{survey.active ? "Đang hiển thị" : "Chưa kích hoạt"}</span>
            <div className="row-actions">
              <button type="button" className="secondary" disabled={busy} onClick={() => void showResults(survey)}>{results?.survey.id === survey.id ? "Ẩn kết quả" : "Kết quả"}</button>
              <button type="button" className="secondary" disabled={busy} onClick={() => void run(() => surveyAdminApi.setActive(survey.id, !survey.active), survey.active ? "Đã tắt khảo sát; kiosk sẽ bỏ qua bước khảo sát." : "Kiosk sẽ hiển thị khảo sát này.")}>{survey.active ? "Tắt" : "Kích hoạt"}</button>
              <button type="button" className="secondary" disabled={busy} onClick={() => startEdit(survey)}>Sửa</button>
              <button type="button" className="secondary" disabled={busy} onClick={() => void run(() => surveyAdminApi.duplicate(survey.id), "Đã tạo phiên bản mới (chưa kích hoạt).", startEdit)}>Tạo phiên bản mới</button>
              <button type="button" className="secondary danger-text" disabled={busy} onClick={() => setConfirmDelete(survey)}>Xóa</button>
            </div>
          </div>
          {results?.survey.id === survey.id && <div className="survey-results">
            <p><strong>{results.data.response_count.toLocaleString("vi-VN")}</strong> phản hồi</p>
            {results.data.questions.map(question => <article key={question.id}>
              <strong>{question.text}</strong><small>{QUESTION_TYPES[question.type] ?? question.type} · {question.answer_count} câu trả lời{question.average != null ? ` · trung bình ${question.average.toLocaleString("vi-VN")}/5` : ""}</small>
              {question.distribution && <Distribution values={question.distribution}/>}
              {question.recent_answers && (question.recent_answers.length ? <ul>{question.recent_answers.map((answer, index) => <li key={index}>{answer.text}</li>)}</ul> : <p className="muted">Chưa có góp ý.</p>)}
            </article>)}
          </div>}
        </div>)}</div>}
    </section>
    {confirmDelete && <div className="modal-overlay" onClick={() => { if (!busy) setConfirmDelete(null); }}><div className="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="delete-survey-title" onClick={event => event.stopPropagation()}>
      <h3 id="delete-survey-title">Xóa khảo sát?</h3>
      <p>“{confirmDelete.survey_name}” sẽ bị ẩn và không hiển thị trên kiosk. {confirmDelete.response_count} phản hồi đã thu vẫn được giữ cho báo cáo.</p>
      <div className="modal-actions">
        <button className="secondary" disabled={busy} onClick={() => setConfirmDelete(null)}>Hủy</button>
        <button className="danger" disabled={busy} onClick={() => void run(() => surveyAdminApi.remove(confirmDelete.id), "Đã xóa khảo sát.", () => { if (editing?.id === confirmDelete.id) reset(); setConfirmDelete(null); })}>Xóa</button>
      </div>
    </div></div>}
  </>;
}
