# Realtime testing and final implementation report

## Automated checks

From backend: .venv-codex/Scripts/python.exe -m pytest -q -p no:cacheprovider (or your configured Python environment).

From frontend: npm test and npm run build.

Tests cover track continuity across multi-second processing gaps, missed-frame expiry, independent tracks, identity streak resets, distance-threshold matching, embedding diagnostics, three-frame confirmation with explicit acceptance, frozen recognition after success, origin rejection, malformed-frame recovery, guarded transitions, subscription cleanup, one-frame backpressure, obsolete sockets and interrupted turns. Existing schema/API/service tests remain in the suite.

## Local setup

1. Start the existing PostgreSQL/backend stack as described in README.
2. Install backend requirements.txt and requirements-face-local.txt in the same backend environment. Realtime detection and matching require the local face-recognition dependencies and `FACE_PROVIDER=local`.
3. Start uvicorn app.main:app --host 127.0.0.1 --port 8000 --ws-max-size 2500000 --ws-max-queue 2.
4. Start frontend on port 5173 and open /kiosk/fullscreen. If using another origin, add its exact origin to KIOSK_STREAM_ORIGINS.
5. Provision camera/microphone permissions. VITE_ENABLE_DEV_CONTROLS=true enables diagnostics only in development. The simulated-presence control creates a development session; it never fabricates an identity.

## Hardware acceptance scenarios

| Scenario | Expected result |
| --- | --- |
| Empty kiosk, physical presence sensor installed | IDLE, camera LED off |
| Idle without a physical presence sensor | Camera remains off; developer control can simulate presence |
| Visitor enters for less than 1.2 seconds | No session wake |
| Visitor remains | Greeting followed by tracking |
| Small face, dim/overexposed light, blur, head turn, closed/occluded eyes | Guidance; matching pauses |
| Two visitors | Independent Track IDs; matching pauses |
| Same known visitor on three eligible observations | One identity confirmation, camera tracks stopped before welcome |
| One still visitor during slow processing | Track ID remains stable; recreation rate approaches zero |
| Developer diagnostics | Server detection FPS and stage latency differ clearly from frontend capture FPS; missing score is `--` |
| Alternating identities / missed face / bad quality | Streak resets; no single-frame acceptance |
| Unknown visitor for 20 seconds | Only Register Face is offered; no retry or guest button; recognition continues |
| Register after fields | Fresh quality-approved frame submits automatically |
| Candidate confirms while unknown screen is visible | Camera stops immediately and welcome begins |
| Voice conversation | TTS, 500 ms silence, automatic listening, interim transcript, thinking, answer |
| No speech | Automatic recognition restart; eventual session inactivity timeout |
| Microphone unavailable | Keyboard input available |
| Connection drops during recognition | Bounded reconnect; votes restart |
| Connection drops during AI operation | Error; request is not automatically replayed |
| Leave during scan | Return idle after eight seconds of absence |
| End and complete survey | Thank-you, end transaction, reset, next visitor gets a fresh session |

## Components and services

Created frontend: AssistantAvatar, CameraManager, TrackingDiagnostics, runtime event catalog/eventBus/stream/stateMachine/useRealtimeSensor, and runtime tests. Modified: KioskApp, KioskChrome, KioskAnimations, FaceRegistrationScreen, WelcomeScreen, KioskVoiceChatScreen, useKioskFlow, useCamera, useSpeechRecognition, API client, runtime state types, Electron main/preload and styles. Removed the obsolete FaceScanningScreen, FaceUnknownScreen and ESM preload.

Created backend: `vision/` with VisionEngine, PresenceDetector, FaceDetector, FaceTracker, QualityEstimator, RecognitionService, IdentityVoting, SessionController and EventPublisher; the runtime WebSocket route remains the existing envelope and service boundary. No database model/migration, Gemini provider or backend business transaction redesign.

Runtime diagram: RUNTIME_ARCHITECTURE.md. Event flow and complete event list: EVENT_SYSTEM.md. Streaming architecture: STREAMING_ARCHITECTURE.md. State machine: STATE_MACHINE.md. Electron checklist: ELECTRON_READY.md.

## Remaining work before RAG integration

First validate the kiosk hardware and speech adapters, calibrate/liveness-test recognition, finish biometric security and provision authenticated backend deployment. Then choose the retrieval/index stack, implement document parsing/chunking, establish source citations, authorization and freshness rules, add grounded-answer evaluation and test retrieval latency within the voice turn budget. The present Gemini behavior and database remain unchanged; this work does not implement or claim RAG.

## Verification recorded on 2026-09-05

39 backend tests and 13 frontend tests passed; the TypeScript/Vite production build and Electron main/preload syntax checks passed. The investigation used aggregate database/profile metadata only; no biometric vectors or identity details were written to the report. Live-camera FPS, detector jitter, microphone conversation, Windows installer and physical sensor acceptance still require kiosk hardware. One existing Starlette test-client deprecation warning remains.
