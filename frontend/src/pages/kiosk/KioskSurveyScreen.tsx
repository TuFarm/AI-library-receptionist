import { useEffect, useState, type FormEvent } from "react";
import { surveyApi } from "../../services/apiClient";
import type { ActiveSurvey, SurveyQuestion } from "../../types/kiosk";

/** Blank free-text answers are skipped rather than submitted (the server rejects empty text). */
export function answersToSubmit(answers: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(answers).filter(([, value]) => typeof value !== "string" || value.trim() !== ""));
}

function Question({ question, value, onChange }: { question: SurveyQuestion; value: unknown; onChange: (value: unknown) => void }) {
  if (question.type === "rating") return <fieldset><legend>{question.text}</legend><div className="kiosk-rating">
    {[1, 2, 3, 4, 5].map((number) => <button type="button" className={Number(value) >= number ? "selected" : ""} onClick={() => onChange(number)} key={number}>★<small>{number}</small></button>)}
  </div></fieldset>;
  if (question.type === "yes_no") return <fieldset><legend>{question.text}</legend><div className="kiosk-choices">
    {["Có", "Không"].map((choice) => <button type="button" className={value === choice ? "selected" : ""} onClick={() => onChange(choice)} key={choice}>{choice}</button>)}
  </div></fieldset>;
  if (question.type === "multiple_choice") return <fieldset><legend>{question.text}</legend><div className="kiosk-choices">
    {(question.options ?? ["Rất tốt", "Tốt", "Cần cải thiện"]).map((choice) => <button type="button" className={value === choice ? "selected" : ""} onClick={() => onChange(choice)} key={choice}>{choice}</button>)}
  </div></fieldset>;
  return <fieldset><legend>{question.text}</legend><textarea value={String(value ?? "")} onChange={(event) => onChange(event.target.value)} placeholder="Nhập phản hồi của bạn…"/></fieldset>;
}

export default function KioskSurveyScreen({ sessionId, userId, onComplete }: { sessionId?: string; userId?: string; onComplete: () => void }) {
  const [survey, setSurvey] = useState<ActiveSurvey | null>();
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  useEffect(() => {
    surveyApi.getActiveSurvey().then(setSurvey).catch(() => { setSurvey(null); setError("Không thể tải khảo sát từ máy chủ."); });
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const filled = answersToSubmit(answers);
    if (!survey || !Object.keys(filled).length) { onComplete(); return; }
    setSubmitting(true); setError("");
    try { await surveyApi.submitSurvey(survey.id, { answers: filled, session_id: sessionId, user_id: userId }); onComplete(); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Không thể gửi phản hồi. Vui lòng thử lại."); }
    finally { setSubmitting(false); }
  }

  if (survey === undefined) return <div className="kiosk-center"><h1>Đang tải khảo sát…</h1></div>;
  if (survey === null) return <div className="kiosk-center"><div className="state-symbol success">✓</div><h1>Hiện chưa có khảo sát</h1><p>{error || "Cảm ơn bạn đã sử dụng trợ lý thư viện."}</p><button onClick={onComplete}>Hoàn tất phiên</button></div>;
  return <form className="kiosk-survey survey-scroll" onSubmit={submit}>
    <span className="kiosk-kicker">CHỈ MẤT KHOẢNG 1 PHÚT</span><h1>{survey.name}</h1>
    <p>{survey.description ?? "Phản hồi của bạn giúp trợ lý thư viện tốt hơn mỗi ngày."}</p>
    {survey.questions.map((question) => <Question key={question.id} question={question} value={answers[question.id]}
      onChange={(value) => setAnswers((current) => ({ ...current, [question.id]: value }))}/>)}
    {error && <p className="form-notice">{error}</p>}
    <button className="kiosk-primary" disabled={submitting || !Object.keys(answersToSubmit(answers)).length}>{submitting ? "Đang gửi…" : "Gửi phản hồi"}</button>
  </form>;
}
