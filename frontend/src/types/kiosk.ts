export type KioskState =
  | "IDLE" | "CAMERA_PERMISSION" | "PRESENCE_DETECTED" | "CAMERA_PREPARING"
  | "WAKE_UP" | "FACE_TRACKING" | "FACE_RECOGNIZING" | "IDENTITY_CONFIRMING" | "FACE_RECOGNIZED" | "STOP_CAMERA" | "WELCOME" | "AI_GREETING"
  | "FACE_SUCCESS" | "GREETING" | "VOICE_GREETING" | "VOICE_LISTENING"
  | "USER_SPEAKING" | "PROCESSING" | "AI_SPEAKING" | "LISTENING"
  | "UNKNOWN_FACE" | "REGISTER" | "REGISTER_PROCESSING" | "REGISTER_SUCCESS"
  | "BOOK_SUGGESTION" | "SURVEY" | "THANK_YOU" | "RETURN_IDLE" | "ERROR";

export type CameraStatus = "IDLE" | "REQUESTING" | "READY" | "DENIED" | "ERROR" | "STOPPED";
export type MicStatus = "IDLE" | "LISTENING" | "PROCESSING" | "DENIED" | "UNSUPPORTED" | "ERROR";
export type MessageInputMethod = "TEXT" | "VOICE";
export type VoiceState = "VOICE_IDLE" | "LISTENING" | "USER_SPEAKING" | "TRANSCRIBING" | "PROCESSING_AI" | "AI_SPEAKING" | "VOICE_ERROR";

export type KioskUser = {
  id: string; student_code: string | null; full_name: string; email?: string | null; phone?: string | null;
  faculty?: string | null; major?: string | null;
  admission_year?: number | null; student_year?: number | null;
};
export type KioskSession = { session_id: string; device_id?: string; status: string; next_state?: KioskState };
export type KioskConversation = { conversation_id: string; status: string };
export type KioskMessage = { id: string; role: "user" | "assistant"; text: string; inputMethod?: MessageInputMethod };
export type FaceVerifyResult = {
  result: "SUCCESS" | "UNKNOWN_FACE" | "LOW_CONFIDENCE" | "FAILED" | string;
  user: KioskUser | null; confidence_score: number | null; next_state: "WELCOME" | "FACE_UNKNOWN"; processing_time_ms?: number;
};
export type FaceRegistrationFields = {
  full_name: string; student_code?: string; email?: string; phone?: string; faculty?: string; major?: string; admission_year?: number;
};
export type FaceEnrollmentResult = {
  face_profile_id: string; user_id: string; user: KioskUser; provider: string; quality_score: number; next_state: "WELCOME";
};
export type BookCategory = { id: string; category_name: string; description?: string | null };
export type SuggestedBook = {
  id: string; category_id?: string | null; external_book_id?: string | null; title: string;
  author_name: string; short_description?: string | null;
};
export type SurveyQuestionType = "rating" | "yes_no" | "text" | "multiple_choice" | string;
export type SurveyQuestion = { id: string; text: string; type: SurveyQuestionType; order?: number; options?: string[] };
export type ActiveSurvey = { id: string; name: string; description?: string | null; version?: number; questions: SurveyQuestion[] };

export type KioskFlowState = {
  currentState: KioskState; session: KioskSession | null; device: { id?: string; code: string };
  user: KioskUser | null; conversation: KioskConversation | null; cameraStatus: CameraStatus; micStatus: MicStatus;
  lastFaceResult: FaceVerifyResult | null; messages: KioskMessage[]; currentTranscript: string;
  lastAiResponse: string | null; selectedBookCategory: string | null; suggestedBooks: SuggestedBook[];
  survey: ActiveSurvey | null; error: string | null; lastActivityAt: number; isProcessing: boolean; mockFallbackActive: boolean;
};

export type KioskAction =
  | { type: "START_SESSION"; session: KioskSession }
  | { type: "CAMERA_PERMISSION_GRANTED" } | { type: "CAMERA_PERMISSION_DENIED"; error?: string }
  | { type: "START_FACE_SCAN" } | { type: "FACE_VERIFY_SUCCESS"; result: FaceVerifyResult }
  | { type: "FACE_VERIFY_UNKNOWN"; result: FaceVerifyResult } | { type: "FACE_VERIFY_FAILED"; error: string }
  | { type: "FACE_ENROLL_SUCCESS"; result: FaceVerifyResult }
  | { type: "START_CONVERSATION"; conversation: KioskConversation }
  | { type: "USER_MESSAGE_SUBMITTED"; message: KioskMessage }
  | { type: "AI_RESPONSE_RECEIVED"; message: KioskMessage; mockFallback?: boolean }
  | { type: "OPEN_BOOK_SUGGESTIONS" } | { type: "OPEN_SURVEY" } | { type: "SURVEY_SUBMITTED" }
  | { type: "END_SESSION" } | { type: "RESET_TO_IDLE" } | { type: "SET_ERROR"; error: string }
  | { type: "SET_CAMERA_STATUS"; status: CameraStatus } | { type: "SET_MIC_STATUS"; status: MicStatus }
  | { type: "SET_TRANSCRIPT"; transcript: string }
  | { type: "SET_BOOK_DATA"; categoryId: string | null; books: SuggestedBook[] }
  | { type: "SET_SURVEY"; survey: ActiveSurvey | null } | { type: "SET_PROCESSING"; value: boolean }
  | { type: "TOUCH" } | { type: "TRANSITION"; state: KioskState };
