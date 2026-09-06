# Session state machine

The transition graph is implemented in frontend/src/runtime/stateMachine.ts. The existing reducer holds business data; async adapters deliver domain actions and epoch guards discard stale AI/enrollment results after reset. Direct TRANSITION actions are validated by the graph. Recognition success is accepted only from sensor states, and enrollment success only from REGISTER_PROCESSING.

```mermaid
stateDiagram-v2
  [*] --> IDLE
  IDLE --> PRESENCE_DETECTED: 1.2s confirmed presence
  PRESENCE_DETECTED --> WAKE_UP
  WAKE_UP --> GREETING
  GREETING --> CAMERA_PREPARING
  CAMERA_PREPARING --> FACE_TRACKING
  FACE_TRACKING --> FACE_RECOGNIZING: quality + stability
  FACE_RECOGNIZING --> FACE_TRACKING: next observation
  FACE_RECOGNIZING --> IDENTITY_CONFIRMING: 3 matches + acceptance
  IDENTITY_CONFIRMING --> FACE_RECOGNIZED: committed identity
  FACE_RECOGNIZED --> STOP_CAMERA
  STOP_CAMERA --> WELCOME
  FACE_TRACKING --> UNKNOWN_FACE: 20s deadline
  FACE_RECOGNIZING --> UNKNOWN_FACE: 20s deadline
  UNKNOWN_FACE --> FACE_RECOGNIZED: recognition continues
  UNKNOWN_FACE --> REGISTER
  REGISTER --> REGISTER_PROCESSING: automatic eligible frame
  REGISTER_PROCESSING --> REGISTER_SUCCESS
  REGISTER_PROCESSING --> REGISTER: enrollment error
  REGISTER_SUCCESS --> WELCOME
  WELCOME --> AI_GREETING
  AI_GREETING --> VOICE_LISTENING
  VOICE_LISTENING --> USER_SPEAKING
  USER_SPEAKING --> PROCESSING
  PROCESSING --> AI_SPEAKING
  AI_SPEAKING --> VOICE_LISTENING: TTS end + 500ms
  VOICE_LISTENING --> SURVEY
  SURVEY --> THANK_YOU
  THANK_YOU --> RETURN_IDLE
  RETURN_IDLE --> IDLE
```

UNKNOWN_FACE is the implementation name for the requested FACE_UNKNOWN branch. LISTENING is retained as a compatibility alias for VOICE_LISTENING. Recognition continues while UNKNOWN_FACE is visible. The only visitor action is Register Face; there is no retry or guest action.

Presence lost for eight seconds during an active scan returns to idle. Session inactivity defaults to 60 seconds and is configurable with VITE_KIOSK_IDLE_TIMEOUT_SECONDS. Speech content and touch refresh activity; mere microphone restart does not. Processing pauses inactivity expiry but transport/API deadlines bound requests. Conversation errors expose a recoverable error screen. Exit opens the existing survey; completion shows thank-you and ends the session.

The camera effect depends on sensor ownership, not per-frame recognition state. It never remounts on a tracking/recognizing transition. Media permission generations prevent late getUserMedia resolution from reopening the camera after shutdown. The voice screen stays mounted across conversational state transitions; speech generation guards prevent the StrictMode cleanup cycle from opening duplicate microphone sessions.

Track lifecycle is independent of UI state transitions. A `track_created` event begins evidence, `track_updated` preserves the identity across slow processed frames, and a missed observation clears votes. `track_lost` follows six consecutive missed processed frames. Three matching attempts at a 500 ms cadence create the candidate proposal; the camera stops before the client accepts that proposal, and `identity_confirmed` is published only after the existing database transaction commits.
