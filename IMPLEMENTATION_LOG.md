# Implementation log

## 2026-09-03 — Phase 2 foundation

- Preserved the optimized 24-table kiosk schema and existing migration.
- Added standard API success/validation-error envelopes and safe database health reporting.
- Added domain Pydantic schemas, session/book service boundaries, and expanded service TODOs.
- Added mock endpoints for user, session, FaceID, knowledge, conversation, AI, suggestions, surveys and reports.
- Added endpoint/helper tests.
- Rebuilt the React UI around a responsive app shell with complete kiosk and admin route coverage.
- Added interactive FaceID simulation, mock chat, book filtering and survey completion flow.
- Added admin metrics, upload placeholder, logs, users, surveys, reports and polished incomplete states.
- Added an environment-aware API client and documented frontend fallback mock usage.

Intentionally not implemented: authentication/RBAC, camera access, biometric processing, Gemini, RAG, parsers, embeddings, real upload/persistence, production charts, catalog or circulation.

Next: introduce service transactions and repositories, consent/auth policy, storage/parser design, selected retrieval stack, Gemini execution and integration tests against disposable PostgreSQL.

## 2026-09-03 — Admin/Kiosk architecture correction

- Split the frontend into `AdminLayout` and fullscreen `KioskLayout`; root now presents both modes.
- Added a reducer-free `useKioskFlow` state controller with inactivity reset and session/conversation context.
- Added dedicated kiosk screens for presence, scan, recognized/unknown identity, welcome, chat, books, survey, thank-you and error.
- Prepared Electron to enter the fullscreen kiosk route through `MemoryRouter` while browsers retain normal URLs.
- Added kiosk session and admin mock routes; aligned conversation route names and added FaceID `next_state` for all mock outcomes.
- Updated psycopg binary requirement for newer Python installers and documented Python 3.12 as the recommended runtime.

Verification: `npm run build` passed (TypeScript and Vite); `git diff --check` passed. Backend tests could not run because this execution environment exposes no `python`, `py`, or `python3` executable.

## 2026-09-03 — Phase 3 kiosk backend runtime

- Added transaction-scoped DB dependency and structured database errors.
- Implemented database-backed kiosk sessions/events, conversations/messages, AI request/response history, face profiles/logs and survey submissions.
- Added multipart face enrollment/verification and voice transcription endpoints with provider isolation.
- Added safe local media validation, randomized filenames, size limits and delete-after-processing default.
- Added browser Web Speech transcript persistence and simple database chunk search.
- Added real database category/book and active-survey reads.
- Added idempotent `scripts/seed_dev.py` for device, user/profile, books, knowledge chunks and survey.
- No migration was required; all writes fit the existing 24-table schema.
- Real local recognition, STT, Gemini and RAG remain isolated placeholders.
- Verification completed with a clean Python 3.12 environment: requirements installed with `psycopg-binary 3.3.5`, 21 tests passed, FastAPI imported 40 routes, Alembic offline SQL compiled, frontend production build passed, and live DB health correctly returned structured 503 because PostgreSQL was not running.

## 2026-09-03 — Phase 4 kiosk frontend runtime

- Replaced the mock-button kiosk controller with a typed `useReducer` state machine covering idle, camera permission/ready, face scan/result, welcome, chat, books, survey, thank-you and error.
- Added `useCamera`, a reusable live preview, safe stream cleanup and in-memory JPEG frame capture posted as multipart form data to the Phase 3 FaceID endpoint.
- Added Vietnamese Web Speech recognition with interim/final transcripts, permission/unsupported fallbacks and keyboard input that remains available at all times.
- Centralized typed session, FaceID, voice, conversation, AI, book, survey and admin API functions; offline fallback now requires `VITE_ENABLE_MOCK_FALLBACK=true`.
- Loaded categories, suggested books and active surveys from database endpoints with friendly empty/loading/error states.
- Added five-second thank-you reset and configurable inactivity reset, paused while listening or processing.
- Kept developer FaceID/bypass/reset controls behind `import.meta.env.DEV` and kept the Admin Web layout/routes unchanged.
- Added conversation message reading and an AI request flag so browser voice persistence does not duplicate the user message.
- Documented runtime architecture, device setup, state transitions, contracts, environment variables, remaining mocks and Electron readiness.

Verification: `npm run build` passed (strict TypeScript project build and Vite production bundle); 21 backend tests passed; OpenAPI exposed the conversation message GET route and voice de-duplication field; live Vite HTTP smoke checks returned 200 with the React root for `/`, `/admin`, `/kiosk` and `/kiosk/fullscreen`. Hardware permission prompts remain a manual laptop check.

## 2026-09-04 — Phase 5 real FaceID and live voice AI kiosk

- Added optional local `face_recognition` provider with lazy imports, exactly-one-face enrollment, 128-dimensional serialized templates, multi-profile distance matching and configurable confidence.
- Expanded `/face/enroll` to create or update users from kiosk registration fields, update the session identity, persist face profiles and record enrollment events.
- Preserved dependency-free mock FaceID and clear `FACE_PROVIDER_UNAVAILABLE` behavior so native Windows dependencies cannot prevent backend startup.
- Implemented Gemini REST text generation with Vietnamese kiosk system instructions, recent conversation context, configurable model/timeout and safe missing-key/network fallback.
- Persisted Gemini fallback status in `ai_requests` and kept conversation messages, AI responses and interaction events consistent.
- Added `useTextToSpeech` with Vietnamese voice preference, spoken welcome/answers and visible default-voice fallback.
- Added `FaceRegistrationScreen` and `KioskVoiceChatScreen` with explicit listening, speaking, transcribing, AI processing, AI speaking and voice error states.
- Implemented the automatic turn loop while preventing recognition during synthesized speech; retained keyboard and quick-question fallback.
- Updated timeout, development controls, provider environment examples, privacy warnings and manual camera/microphone test procedures.
- Kept local FaceID in a separate optional requirements file; no migration was needed because the existing face template binary column supports development embeddings.

Verification: frontend production build passed; backend suite increased to 27 tests covering missing image, unknown face, optional-provider endpoint failure and Gemini missing-key endpoint fallback. Physical camera/microphone/TTS and a real Gemini key remain manual integration checks on the target laptop.

## 2026-09-04 — Phase 5.5 production kiosk UX runtime

- Replaced the click-to-start website flow with automatic camera observation, confirmed presence, camera preparation, face stabilization, 3–2–1 countdown, one-frame capture and a paced verification state.
- Expanded the state machine for presence, capture, verification, greeting, continuous voice phases, guided registration, thank-you and return-to-idle transitions.
- Added centralized timing, cooldown and microphone activation rules plus reusable transition, assistant, listening, scanning, countdown and success animations.
- Added native FaceDetector support with a low-resolution motion/contrast fallback for development environments.
- Added an in-flight verification lock, two-second retry cooldown, 30 fps camera cap, recognition activation lock and overlap-safe speech synthesis.
- Rebuilt enrollment as a progressive information → capture → processing → success wizard.
- Removed the idle start button and manual microphone control from the normal voice path; keyboard input appears only as an unsupported-browser fallback.
- Added three-second identity welcome, TTS-complete plus 500 ms microphone handoff, three-second goodbye and smooth state transitions.
- Added Phase 5.5 runtime, timeline and Electron packaging documentation.
- Added Vitest coverage for core state transitions, success/unknown/registration branches, duplicate verification, microphone guards and production timing.

Verification: 5 frontend runtime tests passed, strict TypeScript/Vite production build passed, and the live kiosk development route returned HTTP 200. Physical presence calibration, microphone/TTS behavior and camera permissions remain manual tests on the target kiosk.

### Phase 5.5 camera lifecycle correction

- Fixed capture failures caused by the visible camera preview unmounting during countdown.
- Added a persistent internal capture video that remains attached to the live stream independently of screen transitions.
- Camera requests are now deduplicated, reuse a live stream, wait for real video dimensions and recover a stopped stream before retry or registration.
- Camera reconnection no longer resets an active scan back to idle, and stale stability results cannot skip directly to countdown.
- Camera failures now open the recoverable permission screen instead of being misclassified as an unknown face.

Verification: 7 frontend runtime tests passed, production build passed, and the live kiosk route returned HTTP 200.


## 2026-09-05 — Realtime assistant runtime

Replaced the active snapshot/countdown kiosk with a duplex WebSocket stream, per-connection face tracks, quality gates and three consecutive same-identity matches. Added client acceptance before identity persistence, camera teardown before welcome, automatic quality-approved enrollment, unknown-user timeout with continued recognition, and presence-loss reset. Existing database, Gemini service and backend business endpoints are preserved.

Added centralized event bus, guarded runtime transition graph, transport backpressure/reconnect/deadlines, stream-based AI/voice transcript commands, reusable avatar renderer, automatic STT restart after silence and microphone-error keyboard fallback. Hardened Electron renderer permissions/navigation/IPC, switched sandbox preload to CommonJS, and added diagnostics and an explicit physical-presence integration boundary.

Verification and deployment limits are recorded in docs/kiosk/TESTING_REALTIME.md and ELECTRON_READY.md. Physical hardware, liveness, recognition calibration, secure biometric templates, device authentication and a production speech provider remain acceptance gates. No production-readiness certification or RAG completion is claimed.

Final verification: 34 backend tests passed, 13 frontend tests passed, frontend production build passed, Electron main/preload syntax checks passed, and the idle browser layout was visually inspected. No database schema files changed.

## 2026-09-05 — Fullscreen native-resolution vision pass

- Enlarged the active camera view to roughly half the kiosk workspace and changed all camera rendering to `object-fit: contain`, preserving the source aspect ratio without stretching.
- Added `CameraManager`; camera capture now requests 1080p/30 fps with a 720p minimum and sends native-resolution frames. CSS preview dimensions no longer affect recognition input.
- Split vision responsibilities into `VisionEngine`, `PresenceDetector`, `FaceDetector`, `FaceTracker`, `QualityEstimator`, `RecognitionService`, `IdentityVoting`, `SessionController`, and `EventPublisher` while retaining the existing WebSocket envelope and backend business services.
- Changed active capture scheduling to a 33 ms target with one-frame acknowledgement backpressure. Detection runs for each accepted frame; recognition is limited to stable quality-approved tracks at a 500 ms cadence.
- Standardized runtime event values to lower snake case, including the required presence, camera, face quality, recognition, identity, registration, voice, and reset events.
- Added landmarks, a green tracking rectangle, confidence-ring animation, and developer-only Track ID/numeric confidence/FPS/latency details.
- Reworked unknown-user UX to keep recognition active with only the face-registration action. Removed guest and face-retry actions from the active kiosk flow.
- Added a frozen final frame and animated success presentation with the recognized student name. The MediaStream is stopped before identity confirmation is committed; welcome waits 2.5 seconds, speaks the greeting, then enters voice conversation.
- Idle no longer starts a camera fallback. Production wake-up uses the Electron presence bridge; developer mode offers explicit presence simulation.
- Added `docs/kiosk/VISION_ENGINE.md` and updated the realtime event, streaming, state, Electron, testing, and runtime documents.
