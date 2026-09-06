import { useEffect, useState, type ComponentType } from "react";
import { kioskEvents } from "../../runtime/eventBus";
import { RuntimeEvent as Events } from "../../runtime/events";
export type AssistantMood = "idle" | "greeting" | "listening" | "thinking" | "speaking" | "happy" | "unknown" | "goodbye" | "error";
export type AvatarProps = { mood?: AssistantMood; label?: string };
// Renderers receive presentation state only: Live2D/ThreeJS can replace this skin.
export function AssistantAvatar({ mood: controlledMood, label = "Trợ lý AI", renderer: Renderer }: AvatarProps & { renderer?: ComponentType<AvatarProps> }) {
  const [eventMood, setEventMood] = useState<AssistantMood>("idle");
  useEffect(() => kioskEvents.subscribe(({ event }) => {
    const moods: Record<string, AssistantMood> = { [Events.presenceDetected]: "greeting", [Events.identityConfirmed]: "happy", [Events.identityUnknown]: "unknown", [Events.aiListeningStarted]: "listening", [Events.aiProcessingStarted]: "thinking", [Events.aiSpeakingStarted]: "speaking", [Events.sessionReset]: "idle", [Events.streamError]: "error" };
    if (moods[event]) setEventMood(moods[event]);
  }), []);
  const mood = controlledMood ?? eventMood;
  if (Renderer) return <Renderer mood={mood} label={label}/>;
  return <div className={`assistant-avatar-runtime ${mood}`} role="img" aria-label={`${label}: ${mood}`}>
    <div className="assistant-face"><i/><i/><span/></div>
    <div className="assistant-rings"><i/><i/><i/></div>
    {(mood === "greeting" || mood === "goodbye") && <b className="assistant-wave">👋</b>}
  </div>;
}
