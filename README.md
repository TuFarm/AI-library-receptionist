# AI Library Receptionist Assistant — Technical Brief

> This is the only project-maintained Markdown document. It is an orientation brief for developers and AI agents; source code, tests, and migrations are the operational source of truth.

## Purpose and scope

This is an AI receptionist for a university library: a fullscreen visitor kiosk plus a separate staff admin UI. The kiosk identifies a visitor by face, accepts library questions through speech/text, offers simple book suggestions, and can collect a survey. Admin has dashboard, knowledge, conversation, user, survey, report, and feature-status views.

It is **not** a library-management system. Do not add catalog, author, publisher, shelf, copy, lending/return, or circulation management unless scope is explicitly expanded. `suggested_books.external_book_id` is the link to the existing library system.

## Repository map

| Location | Responsibility |
| --- | --- |
| `backend/app/main.py` | FastAPI app, CORS, error handling, `/api/v1` router. |
| `backend/app/api/v1/routes/` | HTTP and WebSocket endpoints. |
| `backend/app/services/` | Persistence and provider operations: sessions, face, voice, AI, knowledge, reports, surveys. |
| `backend/app/vision/` | Connection-scoped realtime detection, tracking, quality, voting, stream events. |
| `backend/app/models/schema.py` | SQLAlchemy data model; migration: `backend/alembic/versions/`. |
| `backend/tests/` | Backend unit/runtime/API tests. |
| `frontend/src/pages/kiosk/` | Fullscreen kiosk screens. |
| `frontend/src/hooks/` | Kiosk flow, camera, speech recognition, TTS. |
| `frontend/src/runtime/` | Event bus, WebSocket, state guard, camera manager, realtime sensor. |
| `frontend/src/pages/admin/` | Admin pages; separate from kiosk UI. |
| `frontend/electron/` | Electron main/preload; packaged kiosk uses MemoryRouter. |
| `docker-compose.yml` | Local PostgreSQL 16 and Redis 7. |

## Architecture

```text
React/Vite kiosk or admin UI
  ├─ REST client ──────────────────────────┐
  └─ kiosk WebSocket + camera frames ──┐   │
                                      FastAPI (`/api/v1`)
                                        ├─ services → PostgreSQL
                                        ├─ AI / voice / face providers
                                        └─ vision engine → stream events
```

The browser owns rendering, hardware permission, browser STT/TTS, and local UI state. FastAPI owns validation, transactions, providers, persistent data, and vision streaming. The stream is live-only, not durable; REST owns one-shot session, enrollment, survey, and end-session transactions.

## Kiosk flow

The state machine is `frontend/src/runtime/stateMachine.ts`. Use `useKioskFlow` and the event bus; do not make ad-hoc screen transitions.

```text
IDLE → PRESENCE_DETECTED → WAKE_UP → GREETING → CAMERA_PREPARING
  → FACE_TRACKING / FACE_RECOGNIZING
  → FACE_RECOGNIZED → STOP_CAMERA → WELCOME → AI_GREETING
  → LISTENING ↔ USER_SPEAKING → PROCESSING → AI_SPEAKING → LISTENING
  → SURVEY → THANK_YOU → RETURN_IDLE → IDLE

Unknown: FACE_* → UNKNOWN_FACE → REGISTER → REGISTER_PROCESSING
       → REGISTER_SUCCESS → WELCOME
```

While scanning, JPEG frames go to `WS /api/v1/kiosk/stream`; only one frame may be in flight. The backend detects/tracks faces, gates quality, attempts recognition on stable tracks, and emits events to the client bus. Three consecutive matches for one identity are required before candidacy. Multiple faces, low quality, movement, disappearance, or reconnect reset voting. The client stops camera tracks before confirming an identity.

Realtime frames remain in memory. Camera requests 1920×1080 preferably (1280×720 minimum); backend limits frames to 2.5 MB and 1920×1080. Production wake-up should come from an Electron presence-sensor bridge so camera remains off when idle; developer mode can simulate presence.

Voice is turn-based, not Gemini Live/full-duplex: greeting → browser STT (`vi-VN`) → final transcript → AI request → browser TTS → listening. Keyboard input is always a fallback. Raw microphone audio is not sent through the WebSocket.

## API

Responses normally use `{ success, message, data }`; errors use `{ success: false, message, error }`. Prefix: `/api/v1`.

| Area | Main endpoints | Notes |
| --- | --- | --- |
| Health | `GET /health`, `/health`, `/health/db` | DB check executes `SELECT 1`. |
| Live kiosk | `WS /kiosk/stream`, `POST /kiosk/sessions/start`, `.../{id}/end`, `.../{id}/events` | WebSocket transports vision/runtime events. |
| Face | `POST /face/enroll`, `/face/verify`, `/face/verify/mock` | Records profiles, auth logs, identity/session events. |
| Voice/AI | `POST /voice/transcribe`, `/voice/browser-transcript`, `/ai/answer`, `/ai/answer/mock` | Voice save prevents duplicate user messages. |
| Conversations | `POST /conversations/start`, `POST/GET /conversations/{id}/messages` | Session-linked history. |
| Knowledge | source/upload/document/search routes | Presently mock/text-match bridge; ingestion/RAG unfinished. |
| Books/surveys | categories, suggestions, active survey, responses | Mock and DB-backed paths coexist. |
| Admin/reporting | admin, reports, users, prompts, interactions | Several functions remain mock/static. |

Read route files for request/response schemas. Endpoint presence does not mean production readiness.

## Data model and boundaries

There are 24 tables:

- Identity/session: `users`, `user_preferences`, `face_profiles`, `face_authentication_logs`, `devices`, `user_sessions`, `interaction_events`.
- Knowledge: `knowledge_sources`, `knowledge_documents`, `knowledge_chunks`.
- Conversation/AI: `conversations`, `conversation_messages`, `prompt_versions`, `ai_requests`, `ai_responses`, `ai_feedback`.
- Suggestions: `book_categories`, `suggested_books`, `book_suggestion_logs`.
- Survey/reporting: `surveys`, `survey_questions`, `survey_responses`, `survey_answers`, `daily_report_metrics`.

Keys are UUIDs. Mutable business/configuration rows use timestamp/soft-delete mixins when appropriate; factual logs are append-only. Unknown visitors are valid (`user_sessions.user_id` and `face_authentication_logs.user_id` are nullable). `student_year` is derived from `admission_year`, never stored.

Never store raw face photos in user data. `face_profiles` holds a template/reference only. The local development adapter stores a serialized embedding and is **not** production encryption. A real deployment needs consent, managed encryption keys, liveness/anti-spoofing, RBAC, audit, retention/deletion, and demographic performance validation.

Knowledge chunks, selected conversation context, feedback, prompt versions, and preferences can support RAG and controlled improvement. The system must not silently train itself from DB data. Any training use needs explicit consent, anonymization, governance, and separate approval. `daily_report_metrics` is derived and never replaces raw facts.

## Providers and limits

- `FACE_PROVIDER=mock` runs without native packages. `local` lazily uses `face_recognition`/dlib (CPU HOG, 128-d encodings) and can require CMake/Visual C++ Build Tools on Windows.
- `VOICE_PROVIDER=mock` is available server-side; kiosk normally uses browser Web Speech/SpeechSynthesis, whose Electron support is not assured.
- `AI_PROVIDER=mock` is default. `gemini` calls Gemini `generateContent` through `httpx`, with recent context and a Vietnamese receptionist prompt. Provider errors fall back safely to a concise mock answer and are recorded as fallback/failed—not grounded.
- No vector stack/pgvector, robust document parser, citation-grade RAG, liveness, device authentication, production authorization, or unattended-installation certification exists yet.

Vision quality thresholds are engineering defaults, not calibrated biometric guarantees: HOG detection, IoU tracking, single-face/size/light/blur/eye/pose/stability checks, 500 ms recognition cadence, then three-vote confirmation. Tune only with consented representative testing.

Enrollment requires exactly one face to pass every quality gate for both
`REGISTRATION_STABLE_FRAMES` frames (default `5`) and
`REGISTRATION_STABLE_MS` milliseconds (default `700`). Zero, multiple, low-quality,
track-change, reconnect, or session-change observations reset all enrollment evidence.
`FACE_PROVIDER=mock` is test-only: it has no real detector/identity capability, cannot
prove that two people were identified correctly, and is rejected by the safe REST
enrollment path. Biometric end-to-end identity tests must use `local` or a real provider.

## Local development

Prerequisites: Docker Desktop, Python 3.12 recommended for optional local face support, Node.js/npm, browser camera/microphone access.

```powershell
# root
docker compose up -d

# backend
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
alembic upgrade head
python -m pytest -q
uvicorn app.main:app --reload

# another terminal: frontend
cd frontend
npm install
npm run dev
```

Visit `http://localhost:5173/kiosk/fullscreen` or `/admin/dashboard`. Inside `frontend`, `npm run electron:dev` starts Electron and `npm run electron:build` packages it.

```dotenv
# backend/.env
DATABASE_URL=postgresql+psycopg://ai_library:ai_library_dev@localhost:5432/ai_library
REDIS_URL=redis://localhost:6379/0
FACE_PROVIDER=mock
REGISTRATION_STABLE_FRAMES=5
REGISTRATION_STABLE_MS=700
VOICE_PROVIDER=mock
AI_PROVIDER=mock
# AI_PROVIDER=gemini
# GEMINI_API_KEY=...  # never commit secrets
GEMINI_MODEL=gemini-3.8-flash

# frontend/.env
VITE_API_BASE_URL=http://localhost:8000
VITE_KIOSK_DEVICE_CODE=KIOSK_DEV_01
VITE_ENABLE_MOCK_FALLBACK=false
VITE_KIOSK_IDLE_TIMEOUT_SECONDS=90
VITE_ENABLE_DEV_CONTROLS=true
```

Optional local face support is in `backend/requirements-face-local.txt`; install it separately so missing native dependencies cannot prevent FastAPI startup.

## Change discipline

1. Current source, tests, migrations, and schemas are authoritative; update this brief only for meaningful architecture/scope changes.
2. Preserve kiosk/admin separation and centralized state machine/event bus.
3. Keep biometric templates, raw media, API secrets, and sensitive data out of logs, Git, and events.
4. Do not expand the 24-table schema or mirror the library system of record without an approved requirement.
5. Backend changes: run relevant `pytest` and `alembic upgrade head --sql`. Frontend changes: run relevant `npm run test` and `npm run build`.
6. Before deployment, test migrations against disposable PostgreSQL, test actual kiosk hardware, and close the provider/security gaps above.
