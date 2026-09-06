import type { ActiveSurvey, BookCategory, FaceEnrollmentResult, FaceRegistrationFields, KioskConversation, KioskMessage, KioskSession, SuggestedBook } from "../types/kiosk";

type ApiEnvelope<T> = { success: boolean; message: string; data: T; error?: { code: string; details?: unknown } };
const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8000";
export const API_ROOT = configuredBase.endsWith("/api/v1") ? configuredBase : `${configuredBase}/api/v1`;
export const MOCK_FALLBACK_ENABLED = String(import.meta.env.VITE_ENABLE_MOCK_FALLBACK ?? "false").toLowerCase() === "true";

export class ApiClientError extends Error {
  constructor(message: string, public status?: number, public code?: string) { super(message); this.name = "ApiClientError"; }
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, { signal: AbortSignal.timeout(30000), ...options, headers: options.body instanceof FormData ? options.headers : { "Content-Type": "application/json", ...options.headers } });
  } catch { throw new ApiClientError("Không thể kết nối máy chủ. Vui lòng kiểm tra backend hoặc thử lại."); }
  let body: ApiEnvelope<T> | undefined;
  try { body = await response.json() as ApiEnvelope<T>; } catch { /* invalid server response */ }
  if (!response.ok || !body?.success) throw new ApiClientError(body?.message ?? "Máy chủ không thể xử lý yêu cầu.", response.status, body?.error?.code);
  return body.data;
}
export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(data) }),
  postForm: <T>(path: string, data: FormData) => request<T>(path, { method: "POST", body: data }),
};
export const kioskApi = {
  startSession: (deviceCode: string) => apiClient.post<KioskSession>("/kiosk/sessions/start", { device_code: deviceCode, mode: "kiosk" }),
  endSession: (sessionId: string, exitReason = "COMPLETED") => apiClient.post<{ session_id: string; duration_seconds: number | null; next_state: "IDLE" }>(`/kiosk/sessions/${sessionId}/end`, { exit_reason: exitReason }),
  logEvent: (sessionId: string, event: { event_type: string; input_method?: string; content_summary?: string; success?: boolean }) => apiClient.post<{ event_id: string }>(`/kiosk/sessions/${sessionId}/events`, event),
};
export const faceApi = {
  enrollFace: ({ sessionId, deviceCode, imageBlob, fields }: {
    sessionId?: string; deviceCode: string; imageBlob: Blob; fields: FaceRegistrationFields;
  }) => {
    const form = new FormData();
    if (sessionId) form.append("session_id", sessionId);
    form.append("device_code", deviceCode);
    form.append("image_file", imageBlob, "kiosk-enrollment.jpg");
    Object.entries(fields).forEach(([key, value]) => {
      if (value !== undefined && value !== "") form.append(key, String(value));
    });
    return apiClient.postForm<FaceEnrollmentResult>("/face/enroll", form);
  },
};
export const voiceApi = {
  sendBrowserTranscript: (payload: { session_id?: string; conversation_id: string; transcript: string; confidence_score?: number }) => apiClient.post<{ message_id: string; transcript: string; provider: string }>("/voice/browser-transcript", payload),
};
export const conversationApi = {
  startConversation: (payload: { session_id?: string; user_id?: string }) => apiClient.post<KioskConversation>("/conversations/start", payload),
  sendMessage: (conversationId: string, payload: { sender_type: "USER" | "ASSISTANT"; message_text: string; input_method: "TEXT" | "VOICE" | "SYSTEM" }) => apiClient.post(`/conversations/${conversationId}/messages`, payload),
  getMessages: (conversationId: string) => apiClient.get<KioskMessage[]>(`/conversations/${conversationId}/messages`),
};
export const aiApi = {
  answer: (payload: { conversation_id: string; session_id?: string; message_text: string; save_user_message?: boolean }) => apiClient.post<{ answer: string; provider: string; model_name: string; grounded: boolean; warning?: string | null; next_state: "AI_VOICE_CHAT" }>("/ai/answer", payload),
};
export const bookSuggestionApi = {
  getCategories: () => apiClient.get<BookCategory[]>("/book-categories"),
  getSuggestedBooks: (categoryId?: string) => apiClient.get<SuggestedBook[]>(`/suggested-books${categoryId ? `?category_id=${encodeURIComponent(categoryId)}` : ""}`),
};
export const surveyApi = {
  getActiveSurvey: () => apiClient.get<ActiveSurvey | null>("/surveys/active"),
  submitSurvey: (surveyId: string, payload: { answers: Record<string, unknown>; session_id?: string; user_id?: string }) => apiClient.post<{ response_id: string; answer_count: number }>(`/surveys/${surveyId}/responses`, payload),
};
export const adminApi = {
  getDashboard: () => apiClient.get<Record<string, unknown>>("/admin/dashboard/mock"),
  getStatus: () => apiClient.get<Record<string, unknown>>("/admin/status"),
};
