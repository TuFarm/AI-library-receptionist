import type { AssistantMood } from "../components/kiosk/AssistantAvatar";
import type { KioskState } from "../types/kiosk";

const moodByState: Record<KioskState, AssistantMood> = {
  IDLE: "idle", CAMERA_PERMISSION: "error", PRESENCE_DETECTED: "greeting", WAKE_UP: "greeting", GREETING: "greeting",
  CAMERA_PREPARING: "focused", FACE_TRACKING: "focused", FACE_RECOGNIZING: "focused", IDENTITY_CONFIRMING: "focused",
  FACE_RECOGNIZED: "happy", STOP_CAMERA: "happy", FACE_SUCCESS: "happy", WELCOME: "happy",
  AI_GREETING: "speaking", VOICE_GREETING: "speaking", VOICE_LISTENING: "listening", LISTENING: "listening",
  USER_SPEAKING: "listening", PROCESSING: "thinking", AI_SPEAKING: "speaking", UNKNOWN_FACE: "unknown",
  REGISTER: "thinking", REGISTER_PROCESSING: "thinking", REGISTER_SUCCESS: "happy", BOOK_SUGGESTION: "listening",
  SURVEY: "listening", THANK_YOU: "goodbye", RETURN_IDLE: "idle", ERROR: "error",
};

export function avatarMoodForState(state: KioskState): AssistantMood { return moodByState[state]; }
