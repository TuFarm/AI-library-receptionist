import type { ActiveSurvey, BookCategory, Citation, FaceEnrollmentResult, FaceRegistrationFields, KioskConversation, KioskMessage, KioskSession, KioskUser, SuggestedBook } from "../types/kiosk";
import { adminHeaders, clearAdminSession, type AdminSession, type StaffRole } from "./adminAccess";
import { deviceHeaders, isDeviceAuthError, reportDeviceUnauthorized } from "./deviceAccess";

type ApiEnvelope<T> = { success: boolean; message: string; data: T; error?: { code: string; details?: unknown } };
const configuredBase = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim().replace(/\/$/, "");
const apiBase = configuredBase || (import.meta.env.DEV ? "http://localhost:8000" : window.location.origin);
export const API_ROOT = apiBase.endsWith("/api/v1") ? apiBase : `${apiBase}/api/v1`;
export const MOCK_FALLBACK_ENABLED = String(import.meta.env.VITE_ENABLE_MOCK_FALLBACK ?? "false").toLowerCase() === "true";

export class ApiClientError extends Error {
  constructor(message: string, public status?: number, public code?: string, public fieldErrors: Record<string, string> = {}) { super(message); this.name = "ApiClientError"; }
}
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_ROOT}${path}`, { signal: AbortSignal.timeout(30000), ...options, headers: options.body instanceof FormData ? options.headers : { "Content-Type": "application/json", ...options.headers } });
  } catch { throw new ApiClientError("Không thể kết nối máy chủ. Vui lòng kiểm tra backend hoặc thử lại."); }
  let body: ApiEnvelope<T> | undefined;
  try { body = await response.json() as ApiEnvelope<T>; } catch { /* invalid server response */ }
  if (!response.ok || !body?.success) {
    const fieldErrors: Record<string, string> = {};
    const labels: Record<string, string> = { username: "Tên đăng nhập", password: "Mật khẩu", current_password: "Mật khẩu hiện tại", new_password: "Mật khẩu mới", full_name: "Họ và tên", student_code: "Mã sinh viên", email: "Email", phone: "Số điện thoại", faculty: "Khoa", major: "Ngành", admission_year: "Năm nhập học", title: "Tiêu đề", content: "Nội dung", survey_name: "Tên khảo sát", description: "Mô tả", question_text: "Nội dung câu hỏi", questions: "Danh sách câu hỏi" };
    if (response.status === 422 && Array.isArray(body?.error?.details)) {
      for (const detail of body.error.details as Array<{ loc?: string[]; type?: string }>) {
        const field = detail.loc?.at(-1);
        if (field && labels[field]) fieldErrors[field] = `${labels[field]} ${detail.type === "missing" ? "là bắt buộc" : "không hợp lệ"}.`;
      }
    }
    const message = response.status === 422 ? (Object.values(fieldErrors).join(" ") || (body?.message !== "Validation error" ? body?.message : undefined) || "Dữ liệu chưa hợp lệ. Vui lòng kiểm tra lại các trường.") : body?.message ?? "Máy chủ không thể xử lý yêu cầu.";
    throw new ApiClientError(message, response.status, body?.error?.code, fieldErrors);
  }
  return body.data;
}
// Kiosk requests carry the device key; a rejected key sends the kiosk back to device setup.
async function kioskRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  try { return await request<T>(path, { ...options, headers: { ...deviceHeaders(), ...options.headers } }); }
  catch (error) {
    if (error instanceof ApiClientError && isDeviceAuthError(error.code)) reportDeviceUnauthorized(error.code);
    throw error;
  }
}
export const apiClient = {
  get: <T>(path: string) => kioskRequest<T>(path),
  post: <T>(path: string, data: unknown) => kioskRequest<T>(path, { method: "POST", body: JSON.stringify(data) }),
  patch: <T>(path: string, data: unknown) => kioskRequest<T>(path, { method: "PATCH", body: JSON.stringify(data) }),
  delete: <T>(path: string) => kioskRequest<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, data: FormData) => kioskRequest<T>(path, { method: "POST", body: data }),
};
export type KioskDeviceInfo = { id: string; device_code: string; device_name: string; location: string | null; status: string };
export const kioskApi = {
  // Checks a candidate key before it is saved on the kiosk.
  verifyDevice: (deviceKey: string) => request<KioskDeviceInfo>("/kiosk/device", { headers: { "X-Device-Key": deviceKey } }),
  startSession: (deviceCode: string) => apiClient.post<KioskSession>("/kiosk/sessions/start", { device_code: deviceCode, mode: "kiosk" }),
  endSession: (sessionId: string, exitReason = "COMPLETED") => apiClient.post<{ session_id: string; duration_seconds: number | null; next_state: "IDLE" }>(`/kiosk/sessions/${sessionId}/end`, { exit_reason: exitReason }),
  logEvent: (sessionId: string, event: { event_type: string; input_method?: string; content_summary?: string; success?: boolean }) => apiClient.post<{ event_id: string }>(`/kiosk/sessions/${sessionId}/events`, event),
};
export const faceApi = {
  enrollFace: ({ sessionId, userId, deviceCode, imageBlob, fields }: {
    sessionId?: string; userId?: string; deviceCode: string; imageBlob: Blob; fields: FaceRegistrationFields;
  }) => {
    const form = new FormData();
    if (sessionId) form.append("session_id", sessionId);
    if (userId) form.append("user_id", userId);
    form.append("device_code", deviceCode);
    form.append("image_file", imageBlob, "kiosk-enrollment.jpg");
    Object.entries(fields).forEach(([key, value]) => {
      if (value !== undefined && value !== "") form.append(key, String(value));
    });
    return apiClient.postForm<FaceEnrollmentResult>("/face/enroll", form);
  },
};
// Only the visitor identified in the kiosk's own live session can be edited from the kiosk.
export const userApi = {
  update: (sessionId: string, fields: FaceRegistrationFields) => apiClient.patch<KioskUser>(`/kiosk/sessions/${sessionId}/profile`, fields),
  deleteFaceId: (sessionId: string) => apiClient.delete<{ user_id: string; deleted_profiles: number }>(`/kiosk/sessions/${sessionId}/face-profile`),
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
  answer: (payload: { conversation_id: string; session_id?: string; message_text: string; save_user_message?: boolean }) => apiClient.post<{ answer: string; provider: string; model_name: string; grounded: boolean; citations?: Citation[]; warning?: string | null; next_state: "AI_VOICE_CHAT" }>("/ai/answer", payload),
};
export const bookSuggestionApi = {
  getCategories: () => apiClient.get<BookCategory[]>("/book-categories"),
  getSuggestedBooks: (categoryId?: string) => apiClient.get<SuggestedBook[]>(`/suggested-books${categoryId ? `?category_id=${encodeURIComponent(categoryId)}` : ""}`),
};
export const surveyApi = {
  getActiveSurvey: () => apiClient.get<ActiveSurvey | null>("/surveys/active"),
  submitSurvey: (surveyId: string, payload: { answers: Record<string, unknown>; session_id?: string; user_id?: string }) => apiClient.post<{ response_id: string; answer_count: number }>(`/surveys/${surveyId}/responses`, payload),
};
async function adminRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  try { return await request<T>(path, { ...options, headers: adminHeaders() }); }
  catch (error) {
    if (error instanceof ApiClientError && error.status === 401) {
      clearAdminSession();
      if (typeof window !== "undefined") window.dispatchEvent(new Event("admin-session-expired"));
    }
    throw error;
  }
}
const adminClient = {
  get: <T>(path: string) => adminRequest<T>(path),
  post: <T>(path: string, data: unknown) => adminRequest<T>(path, { method: "POST", body: JSON.stringify(data) }),
  patch: <T>(path: string, data: unknown) => adminRequest<T>(path, { method: "PATCH", body: JSON.stringify(data) }),
  delete: <T>(path: string) => adminRequest<T>(path, { method: "DELETE" }),
  postForm: <T>(path: string, data: FormData) => adminRequest<T>(path, { method: "POST", body: data }),
};
export const adminApi = {
  verifyAccess: (username: string, password: string) => request<AdminSession>("/admin/login", {
    method: "POST", headers: adminHeaders(), body: JSON.stringify({ username: username.trim(), password }),
  }),
  getSession: () => adminClient.get<Omit<AdminSession, "token">>("/admin/session"),
  logout: () => adminClient.post<null>("/admin/logout", {}),
  changePassword: (current_password: string, new_password: string) => adminClient.post<null>("/admin/password", { current_password, new_password }),
  getDashboard: (days?: number) => adminClient.get<AdminDashboard>(`/admin/dashboard${days ? `?days=${days}` : ""}`),
  getStatus: () => adminClient.get<Array<{ module: string; status: string; warning?: string | null }>>("/admin/status"),
};

export type StaffAccount = {
  id: string;
  username: string;
  full_name: string;
  role: StaffRole;
  is_active: boolean;
  locked: boolean;
  last_login_at: string | null;
  created_at: string | null;
};

export const staffApi = {
  list: () => adminClient.get<StaffAccount[]>("/admin/staff"),
  create: (payload: { username: string; full_name: string; role: StaffRole; password: string }) => adminClient.post<StaffAccount>("/admin/staff", payload),
  update: (id: string, payload: Partial<Pick<StaffAccount, "full_name" | "role" | "is_active">>) => adminClient.patch<StaffAccount>(`/admin/staff/${id}`, payload),
  resetPassword: (id: string, new_password: string) => adminClient.post<null>(`/admin/staff/${id}/reset-password`, { new_password }),
};

export type KioskDevice = {
  id: string;
  device_code: string;
  device_name: string;
  location: string | null;
  status: "active" | "disabled";
  has_key: boolean;
  key_prefix: string | null;
  key_rotated_at: string | null;
  last_seen_at: string | null;
};
export type IssuedDeviceKey = KioskDevice & { device_key: string };

export const deviceApi = {
  list: () => adminClient.get<KioskDevice[]>("/admin/devices"),
  create: (payload: { device_code: string; device_name: string; location?: string }) => adminClient.post<IssuedDeviceKey>("/admin/devices", payload),
  update: (id: string, payload: Partial<Pick<KioskDevice, "device_name" | "location" | "status">>) => adminClient.patch<KioskDevice>(`/admin/devices/${id}`, payload),
  rotateKey: (id: string) => adminClient.post<IssuedDeviceKey>(`/admin/devices/${id}/rotate-key`, {}),
};

export type AdminDashboard = {
  total_sessions: number;
  identified_users: number;
  questions: number;
  ai_answers: number;
  surveys: number;
  recognition_success_count: number;
  recognition_failure_count: number;
  recognition_success_rate: number;
  avg_wait_seconds: number;
  camera_network_errors: number;
  avg_satisfaction: number | null;
  grounded_answers: number;
  grounded_rate: number;
  daily: Array<{ date: string; sessions: number; identified: number }>;
};

export type AdminUser = {
  id: string;
  student_code: string | null;
  full_name: string;
  email: string | null;
  phone: string | null;
  faculty: string | null;
  major: string | null;
  admission_year: number | null;
  student_year: number | null;
  user_type: string;
  account_status: string;
};

export const adminUserApi = {
  list: (search = "", offset = 0, limit = 20) => adminClient.get<{ items: AdminUser[]; total: number }>(`/users?offset=${offset}&limit=${limit}${search ? `&search=${encodeURIComponent(search)}` : ""}`),
  create: (payload: Omit<AdminUser, "id" | "student_year" | "user_type" | "account_status"> & { student_code: string; email: string }) => adminClient.post<AdminUser>("/users", payload),
  update: (id: string, payload: Partial<Pick<AdminUser, "student_code" | "full_name" | "email" | "phone" | "faculty" | "major" | "admission_year">>) => adminClient.patch<AdminUser>(`/users/${id}`, payload),
  get: (id: string) => adminClient.get<AdminUser>(`/users/${id}`),
  delete: (id: string) => adminClient.delete<{ user_id: string; account_status: string }>(`/users/${id}`),
};

export type ReportsOverview = {
  period_days: number;
  total_sessions: number;
  identified_users: number;
  total_questions: number;
  total_ai_answers: number;
  recognition_success: number;
  recognition_failure: number;
  recognition_success_rate: number;
  avg_wait_seconds: number;
  camera_network_errors: number;
};

export type SessionReport = {
  period_days: number;
  by_exit_reason: Record<string, number>;
  by_device: Record<string, number>;
  avg_duration_seconds: number;
};

export type DailyMetric = {
  date: string;
  total_sessions: number;
  identified_users: number;
  total_questions: number;
  total_ai_answers: number;
  total_surveys: number;
  avg_satisfaction_score: number | null;
  avg_ai_response_time_ms: number | null;
};

export const reportsApi = {
  getOverview: (days = 7) => adminClient.get<ReportsOverview>(`/reports/overview?days=${days}`),
  getSessions: (days = 7) => adminClient.get<SessionReport>(`/reports/sessions?days=${days}`),
  getDaily: (days = 7) => {
    const end = new Date(); const start = new Date(end.getTime() - (days - 1) * 86_400_000);
    const iso = (value: Date) => value.toISOString().slice(0, 10);
    return adminClient.get<{ metrics: DailyMetric[] }>(`/reports/daily?start_date=${iso(start)}&end_date=${iso(end)}`);
  },
  rebuildDaily: (days = 7) => adminClient.post<{ metrics: DailyMetric[] }>(`/reports/daily/rebuild?days=${days}`, {}),
};

export type SurveyQuestionType = "rating" | "yes_no" | "text";
export type AdminSurvey = {
  id: string;
  survey_name: string;
  description: string | null;
  version: number;
  active: boolean;
  response_count: number;
  questions: Array<{ id: string; question_text: string; question_type: SurveyQuestionType; question_order: number }>;
  created_at: string | null;
};
export type SurveyInput = { survey_name: string; description: string | null; questions: Array<{ question_text: string; question_type: SurveyQuestionType }> };
export type SurveyResults = {
  survey_id: string;
  response_count: number;
  questions: Array<{ id: string; text: string; type: SurveyQuestionType; answer_count: number; average?: number | null;
    distribution?: Record<string, number>; recent_answers?: Array<{ text: string; submitted_at: string }> }>;
};

export const surveyAdminApi = {
  list: () => adminClient.get<AdminSurvey[]>("/admin/surveys"),
  create: (payload: SurveyInput) => adminClient.post<AdminSurvey>("/admin/surveys", payload),
  update: (id: string, payload: Partial<SurveyInput>) => adminClient.patch<AdminSurvey>(`/admin/surveys/${id}`, payload),
  setActive: (id: string, active: boolean) => adminClient.post<AdminSurvey>(`/admin/surveys/${id}/${active ? "activate" : "deactivate"}`, {}),
  duplicate: (id: string) => adminClient.post<AdminSurvey>(`/admin/surveys/${id}/duplicate`, {}),
  remove: (id: string) => adminClient.delete<{ id: string }>(`/admin/surveys/${id}`),
  results: (id: string) => adminClient.get<SurveyResults>(`/admin/surveys/${id}/results`),
};

export type ConversationSummary = {
  id: string;
  started_at: string;
  status: string;
  device_code: string | null;
  visitor: { full_name: string; student_code: string | null } | null;
  identified: boolean;
  message_count: number;
  first_question: string | null;
  answer_count: number;
  grounded_count: number;
};
export type ConversationDetail = {
  id: string;
  started_at: string;
  status: string;
  visitor: ConversationSummary["visitor"];
  messages: Array<{ id: string; sender_type: string; text: string; input_method: string | null; time: string;
    ai?: { grounded: boolean; citations: Citation[]; model_name: string | null; status: string; latency_ms: number | null } }>;
};

export const conversationAdminApi = {
  list: (filters: { days: number; search?: string; ungrounded?: boolean; offset?: number; limit?: number }) => {
    const params = new URLSearchParams({ days: String(filters.days), offset: String(filters.offset ?? 0), limit: String(filters.limit ?? 20) });
    if (filters.search?.trim()) params.set("search", filters.search.trim());
    if (filters.ungrounded) params.set("ungrounded", "true");
    return adminClient.get<{ items: ConversationSummary[]; total: number }>(`/admin/conversations?${params}`);
  },
  get: (id: string) => adminClient.get<ConversationDetail>(`/admin/conversations/${id}`),
};

export type KnowledgeDocument = {
  id: string;
  title: string;
  source_type: string;
  original_file_name: string | null;
  file_size: number | null;
  status: "processing" | "processed" | "failed";
  processing_error: string | null;
  is_active: boolean;
  chunk_count: number;
  created_at: string | null;
  updated_at: string | null;
};
export type KnowledgeChunkPreview = { id: string; index: number; text: string; page_number: number | null; sheet_name: string | null };
export type KnowledgeSearchHit = Citation & { text: string; score: number };

export const knowledgeApi = {
  list: (search = "") => adminClient.get<{ items: KnowledgeDocument[]; total: number; max_upload_mb: number }>(`/knowledge/documents?limit=100${search ? `&search=${encodeURIComponent(search)}` : ""}`),
  get: (id: string) => adminClient.get<KnowledgeDocument & { chunks: KnowledgeChunkPreview[] }>(`/knowledge/documents/${id}`),
  upload: (file: File, title?: string) => {
    const form = new FormData();
    form.append("file", file, file.name);
    if (title?.trim()) form.append("title", title.trim());
    return adminClient.postForm<KnowledgeDocument>("/knowledge/documents", form);
  },
  createText: (title: string, content: string) => adminClient.post<KnowledgeDocument>("/knowledge/documents/text", { title: title.trim(), content }),
  update: (id: string, payload: { title?: string; is_active?: boolean }) => adminClient.patch<KnowledgeDocument>(`/knowledge/documents/${id}`, payload),
  reprocess: (id: string) => adminClient.post<KnowledgeDocument>(`/knowledge/documents/${id}/reprocess`, {}),
  remove: (id: string) => adminClient.delete<{ id: string }>(`/knowledge/documents/${id}`),
  search: (query: string) => adminClient.post<KnowledgeSearchHit[]>("/knowledge/search", { query: query.trim(), top_k: 5 }),
};
