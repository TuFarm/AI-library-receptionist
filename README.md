# AI Library Receptionist Assistant — Technical Brief

> This is the only project-maintained Markdown document. It is an orientation brief for developers and AI agents; source code, tests, and migrations are the operational source of truth.

## Purpose and scope

This is an AI receptionist for a university library: a fullscreen visitor kiosk plus a separate staff admin UI, both served as one web app (the kiosk is the `/kiosk/fullscreen` route opened in a browser; there is no desktop/Electron build). The kiosk identifies a visitor by face, accepts library questions through speech/text, offers simple book suggestions, and can collect a survey. Admin has dashboard, knowledge, conversation, user, survey, report, and feature-status views.

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
| `docker-compose.yml` | Production-like full stack: Nginx frontend, FastAPI, migrations, PostgreSQL 16, and Redis 7. |

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

The kiosk supports direct touch wake-up and camera-based local motion sensing; it has no physical presence-sensor bridge. One `MediaStream` is opened for the mounted kiosk and reused across states. In IDLE there is no camera preview, scanner, face guide, recognition, AI processing, or frame upload. A local 96×54 grayscale canvas samples at 5 FPS, evaluates a configurable standing-zone ROI, warms an adaptive background, compensates whole-frame brightness shifts, and requires sustained 6/8 evidence for at least 1.2 seconds. Motion and pointer/touch/Enter/Space all enter the same idempotent state-machine wake path.

Only active Face ID states send JPEG frames to `WS /api/v1/kiosk/stream`; only one frame may be in flight. The backend detects/tracks faces, gates quality, attempts recognition on stable tracks, and emits events to the client bus. Three consecutive matches for one identity are required before candidacy. Multiple faces, low quality, movement, disappearance, or reconnect reset voting. `STOP_CAMERA` remains a logical flow state; it does not tear down the shared camera stream.

Realtime frames remain in memory. Camera requests 1920×1080 preferably (1280×720 minimum); backend limits frames to 2.5 MB and 1920×1080. Idle motion pixels are processed locally and are never logged, stored, or sent. Face ID quality, enrollment evidence, unknown-recognition, tracking, and confirmation guards remain authoritative. The IDLE rotating tips are a typed static list in `frontend/src/content/kioskIdleFacts.ts` and require no database/admin data.

Voice is turn-based, not Gemini Live/full-duplex: greeting → STT (`vi-VN`) → final transcript → AI request → browser TTS → listening. Keyboard input is always a fallback, and every answer is also shown as text. Raw microphone audio is not sent through the WebSocket.

`VITE_VOICE_INPUT` picks the STT source: `auto` (default) uses browser Web Speech (Chrome/Edge); in browsers without it (e.g. Firefox) the kiosk records one utterance with `MediaRecorder` (it ends after 1.2 s of silence, 15 s at most, and is discarded if nobody spoke) and posts it to `POST /voice/transcribe`. `browser` or `server` force one source. Server STT needs `VOICE_PROVIDER=gemini` and `GEMINI_API_KEY`: the utterance is sent inline to the configured `GEMINI_MODEL`, the temporary file is deleted afterwards (unless `MEDIA_RETAIN_DEVELOPMENT_FILES`), and a failure or silence returns an empty transcript rather than a guess. Enabling it sends visitors' voice to Google. Browser Web Speech is not local either: Chrome sends the audio to Google and Edge to Microsoft. The voice screen therefore shows a one-line notice naming the service for the active mode (`voicePrivacyNotice`), and the admin status page repeats it; the deployment's written privacy notice must say the same. The mock provider returns a fixed sentence for tests; the kiosk refuses to submit it as a question unless `VITE_ENABLE_MOCK_FALLBACK=true`. Speech output still uses the OS voices behind `speechSynthesis`; install a Vietnamese voice on the kiosk machine.

## API

Responses normally use `{ success, message, data }`; errors use `{ success: false, message, error }`. Prefix: `/api/v1`.

| Area | Main endpoints | Notes |
| --- | --- | --- |
| Health | `GET /health`, `/health`, `/health/db` | DB check executes `SELECT 1`. |
| Live kiosk | `WS /kiosk/stream`, `POST /kiosk/sessions/start`, `.../{id}/end`, `.../{id}/events` | WebSocket transports vision/runtime events. |
| Face | `POST /face/enroll`, `/face/verify` | Records profiles, auth logs, identity/session events. |
| Voice/AI | `POST /voice/transcribe`, `/voice/browser-transcript`, `/ai/answer` | Voice save prevents duplicate user messages. |
| Conversations | `POST /conversations/start`, `POST/GET /conversations/{id}/messages` | Session-linked history. |
| Knowledge | `GET/POST /knowledge/documents`, `POST /knowledge/documents/text`, `GET/PATCH/DELETE /knowledge/documents/{id}`, `POST .../{id}/reprocess`, `POST /knowledge/search` | Staff only. Upload → extract → chunk → BM25 retrieval; see *Knowledge and RAG*. |
| Books/surveys | categories, suggestions, `GET /surveys/active`, `POST /surveys/{id}/responses` | Answers are validated per question type before anything is stored. |
| Admin/reporting | `/admin/dashboard`, `/admin/status`, `/admin/conversations`, `/admin/surveys`, `/reports/overview`, `/reports/sessions`, `/reports/daily`, `POST /reports/daily/rebuild`, `/users` | Staff only; see *Surveys, conversation logs and daily reports*. |

Read route files for request/response schemas. Endpoint presence does not mean production readiness.

### Access control

There are two kinds of caller, and every non-public endpoint requires one of them.

**Staff (admin UI).** Accounts live in PostgreSQL (`staff_accounts`) with one of two roles:

| Role | Can do |
| --- | --- |
| `librarian` | Dashboard, reports, knowledge documents, conversation logs, surveys, non-biometric user profile CRUD, departments/majors. |
| `admin` | Everything a librarian can, plus staff accounts, kiosk devices, and Face ID erasure at the desk (`POST /users/{id}/face-id-erasures`). |

No staff role can read or export a Face ID template; the admin user list only shows whether one exists (`has_face_id`). See *Consent* for erasure.

Create the first admin from `backend` after migrating (the password is prompted, or read
from `STAFF_PASSWORD` for non-interactive runs); in the Docker stack use
`docker compose exec backend python scripts/create_staff.py ...`:

```powershell
python scripts/create_staff.py --username admin --full-name "Quản trị viên" --role admin
```

`POST /admin/login` returns an opaque bearer token; only its SHA-256 is stored
(`staff_sessions`). Sessions last `STAFF_SESSION_MINUTES` (default 15), are bound to the
browser's random `X-Admin-Device` ID, user agent and client IP, and are revoked on logout,
password change, password reset, role change or deactivation. Passwords use PBKDF2-SHA256
(`STAFF_PASSWORD_ITERATIONS`, default 600,000). `STAFF_LOGIN_MAX_FAILURES` wrong passwords
(default 5) lock the account for `STAFF_LOGIN_LOCKOUT_MINUTES` (default 15). The last active
admin cannot be demoted or deactivated, and nobody can demote or deactivate themselves.
Missing/invalid credentials return 401, a wrong role 403.

**Kiosk devices.** An admin registers each kiosk under *Admin → Thiết bị kiosk*; the raw
key (`kd_…`) is shown once and only its SHA-256 is stored on `devices`. On first start the
kiosk shows a *Cài đặt thiết bị* screen where staff paste that key; it is kept in the
kiosk's local storage, never in the web bundle. (`VITE_KIOSK_DEVICE_KEY` is honoured only by
the Vite dev server, for convenience.) Every kiosk REST call sends `X-Device-Key`; the
WebSocket sends `{"event": "AUTH", "payload": {"device_key": …}}` as its first message
(not in the URL, which proxies log) and is closed with 4401 (missing/invalid key) or 4403
(disabled device or another kiosk's session). Rotating a key invalidates the old one
immediately; disabling a device blocks it until it is re-enabled.

A kiosk can only act on sessions it started: sessions, conversations, AI turns,
transcripts, survey submissions and Face ID verification are checked against the
authenticated device, and a foreign ID is reported as not found. Profile edits and Face ID
deletion from the kiosk go through `PATCH /kiosk/sessions/{id}/profile` and
`DELETE /kiosk/sessions/{id}/face-profile`, which act only on the visitor already identified
in that live session. `POST /face/enroll` accepts `user_id` only for that same identified
visitor, and refuses (409 `FACE_ALREADY_REGISTERED`) to attach a new face to a student code
or email whose account already has a Face ID — the owner must be recognized first, or, if the
kiosk no longer recognizes them, bring their student card to the desk so an admin erases the
old Face ID before they re-enroll. `GET /kiosk/device` lets a kiosk check its key.

Public without credentials: health checks, active survey and book suggestion lookups,
and department/major lookups. The old `/…/mock` demo routes and static demo pages have been removed;
`VITE_ENABLE_MOCK_FALLBACK=true` remains an opt-in offline mode for kiosk UI development only.

Profile writes accept only name, student code, email, faculty, major and
admission year; phone numbers are not collected (the column was dropped in migration
`20261010_0002`, which deletes any stored numbers). Kiosk responses, REST and stream, carry
the email only masked (`ng***@st.hcmuaf.edu.vn`); the kiosk edit form leaves it empty, and a
masked value sent back is ignored, so the stored address is never overwritten with the hint. Unknown fields and invalid input return 422; duplicate student
codes/emails return 409, including values reserved by soft-deleted profiles.
Deleting a profile deactivates the account and hides it from profile CRUD without
deleting its Face ID material. Dashboard totals use the selected number of UTC
calendar days through the current time; its daily series groups the original sessions
so it works before any daily aggregate job runs. Reports use the same time window.

### Surveys, conversation logs and daily reports

The kiosk shows the one active survey at the end of a session (none active: the step is
skipped). Staff create surveys under *Admin → Khảo sát* with 1–20 questions of type
`rating` (1–5), `yes_no` (`Có`/`Không`) or `text` (≤1000 characters); a new survey starts
inactive and activating one deactivates the others. Once a survey has responses its
questions are frozen so stored answers keep their meaning; *Tạo phiên bản mới* copies it
as the next `version`. Deleting is a soft delete that keeps responses. The kiosk endpoint
validates every answer against its question type before writing any row.

*Admin → Hội thoại* lists conversations in the selected window with visitor (when
identified), kiosk, first question and how many AI answers were grounded. The
*không có nguồn* filter shows conversations with an answer that cited no document — the
list of knowledge gaps to fill. The detail view shows each answer's citations, model,
status and latency.

`report_service.aggregate_day` recomputes one UTC day of `daily_report_metrics` from the
raw logs (sessions, identified sessions, questions, answered AI requests, survey responses,
mean 1–5 rating, mean AI latency) and overwrites that day's row, so it is safe to repeat.
`REPORT_JOB_ENABLED=true` runs it in-process every `REPORT_JOB_INTERVAL_MINUTES`
(default 60) for today and yesterday; with several backend workers use
`python scripts/aggregate_daily_reports.py --days 2` from cron instead. Staff can also
press *Tổng hợp lại* on the reports page (`POST /reports/daily/rebuild?days=N`).

For the complete backend unit suite, install `backend/requirements-test.txt` instead
of only the runtime requirements. It adds NumPy and Pillow for test fixtures without
enabling a native Face ID provider. From `backend`, run
`python -m pip install -r requirements-test.txt`, then `python -m pytest -q`.
`tests/conftest.py` pins mock providers, the default stream origins and a disabled report job
before settings load, so a developer's `backend/.env` (real providers, tunnel origins) cannot
change test results; explicitly exported environment variables still win.

GitHub Actions (`.github/workflows/ci.yml`) runs on every push to `main` and every pull request:
the backend suite, `alembic upgrade head` → `downgrade base` → `upgrade head` on a PostgreSQL 16
service, a start-up check against the migrated database, and the frontend `npm ci`, `npm test`
and `npm run build`. Frontend dependencies are pinned with caret ranges and locked in `package-lock.json`.

Migrations are explicit DDL. The initial revision is frozen to the original 24 tables;
every later model change needs its own revision. `tests/test_migrations.py` renders
`alembic upgrade head --sql` offline and fails if any ORM table or column is missing.

## Data model and boundaries

There are 30 tables:

- Identity/session: `users`, `user_preferences`, `face_profiles`, `face_authentication_logs`, `devices`, `user_sessions`, `interaction_events`.
- Knowledge: `knowledge_sources`, `knowledge_documents`, `knowledge_chunks`.
- Conversation/AI: `conversations`, `conversation_messages`, `prompt_versions`, `ai_requests`, `ai_responses`, `ai_feedback`.
- Suggestions: `book_categories`, `suggested_books`, `book_suggestion_logs`.
- Survey/reporting: `surveys`, `survey_questions`, `survey_responses`, `survey_answers`, `daily_report_metrics`.
- Academic lookups and chat log (admin branch): `departments`, `majors`, `chat_sessions`, `chat_messages`.
- Staff access: `staff_accounts`, `staff_sessions` (kiosk keys live on `devices`).

Keys are UUIDs. Mutable business/configuration rows use timestamp/soft-delete mixins when appropriate; factual logs are append-only. Unknown visitors are valid (`user_sessions.user_id` and `face_authentication_logs.user_id` are nullable). `student_year` is derived from `admission_year`, never stored.

Never store raw face photos in user data. `face_profiles` holds a template/reference only.

**Template encryption.** `face_template_encrypted` is encrypted by the application with AES-256-GCM (`app/core/template_crypto.py`) under `FACE_TEMPLATE_KEY`, base64 of 32 random bytes (`python -c "import base64,os;print(base64.b64encode(os.urandom(32)).decode())"`). Each row carries a key id and a fresh nonce and is bound to its owner's user id, so a template copied to another user, a wrong key, or a tampered row is skipped (logged by profile id only) instead of matched. `ENVIRONMENT=production` refuses to start without the key and ignores unencrypted rows; development without a key still stores the legacy plaintext format. Encrypt rows written before the key existed with `python scripts/encrypt_face_templates.py --dry-run`, then without `--dry-run` (safe to repeat; in Docker prefix `docker compose exec backend`). **Losing the key makes every Face ID unusable** and everyone must re-enroll: keep a copy outside the server and outside database backups, which would otherwise hold both halves. There is no key rotation yet; changing the key means re-enrollment. Still open: liveness/anti-spoofing, audit, a retention policy, and demographic performance validation.

**Consent.** Before the camera step of any enrollment (new or re-enrollment) the kiosk shows what is stored, why, and how to erase it, and requires an explicit tick. `POST /face/enroll` rejects a request without `face_consent=true` (422 `FACE_CONSENT_REQUIRED`) before the image is saved or analysed, and on success records `users.face_consent_at` and `users.face_consent_version` (`FACE_CONSENT_VERSION`, which must match `FACE_CONSENT_VERSION` in `FaceRegistrationScreen.tsx`; bump both when the text changes). The current text (`2026-10c`) says templates are encrypted and offers two ways to erase a Face ID: the visitor from the kiosk profile after being recognized (`DELETE /kiosk/sessions/{id}/face-profile`), or an admin at the desk when the student is present, for example because the kiosk no longer recognizes them (`POST /users/{id}/face-id-erasures` with a reason and `student_present=true`; librarians get 403). Erasing removes every profile row of that user, clears the consent record, and writes an audit row to `face_id_erasures` (source `KIOSK` with the device, or `ADMIN` with the admin's username and reason); admins see that history in the erase dialog (`GET /users/{id}/face-id-erasures`). A librarian's profile deletion deactivates the account and stops recognition but leaves the encrypted template in place.

**Liveness is not implemented.** Nothing distinguishes a live face from a printed photo or a screen. This is a deliberate, documented gap: a heuristic (blink or head-turn checks) would give a false sense of security. Real anti-spoofing needs a dedicated, calibrated presentation-attack-detection model validated on consented data. Until then, treat Face ID as a convenience greeting, never as authentication for anything sensitive. Concretely, today a photo of an enrolled student yields an identified kiosk session that shows that student's profile (email masked), can edit it, can erase their Face ID, and can re-enroll, replacing their template with the presenter's face. The admin status page states this gap whenever a real Face ID provider is configured.

Knowledge chunks, selected conversation context, feedback, prompt versions, and preferences can support RAG and controlled improvement. The system must not silently train itself from DB data. Any training use needs explicit consent, anonymization, governance, and separate approval. `daily_report_metrics` is derived and never replaces raw facts.

## Knowledge and RAG

Staff upload PDF (with a text layer), Word `.docx`, Excel `.xlsx`, TXT, Markdown or CSV files
(`MAX_KNOWLEDGE_UPLOAD_MB`, default 20), or paste text, under *Admin → Tài liệu tri thức*.
`knowledge_service` checks the extension and file signature, keeps the original under
`MEDIA_STORAGE_DIR/knowledge/` for reprocessing, extracts text per PDF page / Excel sheet,
and packs paragraphs into ~900-character chunks with a 150-character overlap that never
crosses a page or sheet. Extraction runs inside the request; a failure (scanned PDF, wrong
encoding, corrupt file) leaves the document with `status=failed` and a Vietnamese
`processing_error` that staff can see and retry. Spreadsheet rows become `Header: value`
lines so every chunk stands alone. Deleting is a soft delete; deactivated, deleted or failed
documents are never retrieved.

`rag_service.retrieve` scores active chunks with BM25 over lower-cased syllables, syllable
bigrams and accent-stripped syllables (so `gio mo cua` finds `giờ mở cửa`). A chunk must
cover at least 40% of the question's content-word IDF, and chunks below 40% of the best
score are dropped; at most `RAG_TOP_K` (default 4) are used. The in-process index is rebuilt
only when the set of active chunks changes. `POST /knowledge/search` returns exactly what the
kiosk AI would retrieve, for staff to test documents.

Each AI turn retrieves first. With Gemini, chunks are sent as a numbered `<tai_lieu>` block
inside the user turn (marked as data, not instructions); the model cites `[n]`, the markers
are stripped from the spoken text and kept as `citations`. Without Gemini (mock provider, a
missing key, or a provider error), the answer quotes the best-matching sentences of the top
chunk verbatim. With no matching chunk, the assistant gives the fixed "chưa được cung cấp tài
liệu chính thức" reply. `ai_responses.grounded` and `ai_responses.citations` record which
chunks an answer used, and the kiosk shows them as *Nguồn* under the answer.

## Providers and limits

- `FACE_PROVIDER=mock` runs without native packages. `local` lazily uses `face_recognition`/dlib (CPU HOG, 128-d encodings) and can require CMake/Visual C++ Build Tools on Windows. `local_opencv` is an opt-in YuNet + SFace ONNX provider; it is not the default and never downloads model files at runtime.
- `VOICE_PROVIDER=gemini` provides server-side STT for kiosk browsers without Web Speech (see *Kiosk flow*); `mock` is for tests only, and `browser` disables server STT.
- `AI_PROVIDER=mock` is default. `gemini` calls Gemini `generateContent` through `httpx`, with recent context and a Vietnamese receptionist prompt. Provider errors fall back safely to a concise mock answer and are recorded as fallback/failed—not grounded.
- No vector stack/pgvector, OCR for scanned PDFs, liveness, mTLS/hardware-backed device identity, or unattended-installation certification exists yet. Staff RBAC and per-kiosk keys are described under *Access control*.

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

### Production-like Docker installation and smoke test

The Compose stack builds and runs the complete web application. PostgreSQL and Redis are
available only on the private Compose network; Nginx is the single public entry point and
proxies API/WebSocket traffic to FastAPI. Database migrations run before the backend starts.

```bash
cp .env.production.example .env
# Edit .env: set a strong POSTGRES_PASSWORD, allowed origin, and providers.
# Put certs/server.pem and certs/server-key.pem in place first (see LAN deployment).
docker compose up -d --build --wait
docker compose ps
curl --fail https://localhost/health
```

Nginx serves the app on HTTPS port 443; `APP_PORT` (default 80) only redirects to it, apart
from `/health`, which the container healthcheck uses. Open `/kiosk/fullscreen` or
`/admin/dashboard` through `https://<server>`. If `up` hangs on the frontend, check
`docker compose logs frontend`: Nginx refuses to start without both certificate files. Follow logs with `docker compose logs -f backend frontend`; stop the stack
with `docker compose down`. Named volumes preserve PostgreSQL, Redis, and uploaded media.
Use `docker compose down --volumes` only when intentionally deleting that data.

The target deployment is this stack on one server inside the library LAN; kiosks and staff
open it from browsers on the same network (see *Backend server and kiosk LAN deployment*).
`migrate` applies Alembic migrations on every `up`, so there is no separate migration step.
Keep database/Redis ports private and keep the server's `.env` and `certs/` out of Git.

A Cloudflare quick tunnel is for testing only, never for real visitors: it exposes the
machine to the internet and gives HTTPS for free. For the dev server run
`cloudflared tunnel --url http://localhost:5173` and put the printed host in
`DEV_ALLOWED_HOSTS` (`frontend/.env`); for the Docker stack run
`cloudflared tunnel --url https://localhost --no-tls-verify` (tunnelling the HTTP port would loop
on the redirect) and add the tunnel's `https://` origin to `KIOSK_STREAM_ORIGINS`. Stop the tunnel after testing.

To validate configuration without starting containers:

```bash
docker compose config --quiet
```

The manual development workflow remains available below.

```powershell
# root (start only development dependencies and expose their ports)
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis

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

Visit `http://localhost:5173/kiosk/fullscreen` or `/admin/dashboard`. For an unattended kiosk, open that URL in Chrome/Edge kiosk mode (e.g. `chrome --kiosk https://<host>/kiosk/fullscreen`); browsers only grant camera/microphone on HTTPS or `localhost`.

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
VITE_KIOSK_CAMERA_WIDTH=1280
VITE_KIOSK_CAMERA_HEIGHT=720
VITE_KIOSK_UNKNOWN_MIN_MS=4000
VITE_KIOSK_UNKNOWN_ATTEMPTS=3
VITE_KIOSK_CAPTURE_PREPARATION_MS=1800
VITE_KIOSK_REGISTRATION_STABLE_FRAMES=5
VITE_KIOSK_REGISTRATION_STABLE_MS=700
```

Optional local face support is in `backend/requirements-face-local.txt`; install it separately so missing native dependencies cannot prevent FastAPI startup.

### Optional OpenCV ONNX Face ID

Install `backend/requirements-face-opencv.txt` only on hosts that will explicitly use
`FACE_PROVIDER=local_opencv`. The pinned package is the headless OpenCV build because
camera capture and UI remain in the browser (React). OpenCV supplies its compatible NumPy
dependency; Pillow is pinned explicitly for the existing WebSocket frame decoder.

Provision both reviewed model files outside Git and set absolute paths in the backend
environment:

```dotenv
FACE_PROVIDER=local_opencv
FACE_YUNET_MODEL_PATH=C:/secure-models/face_detection_yunet_2023mar.onnx
FACE_SFACE_MODEL_PATH=C:/secure-models/face_recognition_sface_2021dec.onnx
FACE_YUNET_CONFIDENCE_THRESHOLD=0.9
FACE_YUNET_NMS_THRESHOLD=0.3
# Set FACE_SFACE_COSINE_THRESHOLD only after deployment-specific calibration.
```

Approved model identities for this initial adapter:

| Model | Official source | SHA-256 |
| --- | --- | --- |
| `face_detection_yunet_2023mar.onnx` | `https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet` | `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4` |
| `face_recognition_sface_2021dec.onnx` | `https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface` | `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79` |

OpenCV Zoo stores model weights with Git LFS. Confirm that provisioned files are real
ONNX binaries rather than small LFS pointer files, then verify them before deployment:

```powershell
Get-FileHash C:\secure-models\face_detection_yunet_2023mar.onnx -Algorithm SHA256
Get-FileHash C:\secure-models\face_recognition_sface_2021dec.onnx -Algorithm SHA256
```

Provider creation checks configuration, `.onnx` filenames, readability, exact hashes,
and whether OpenCV can parse both networks. A missing or invalid dependency/model fails
closed with `FaceProviderUnavailable`; there is no production fallback to mock.
YuNet receives the decoded frame's actual width and height before every detection. Its
default score threshold is `0.9`, NMS threshold is `0.3`, and pre-NMS `top_k` is `5000`.
Detector results contain only the internal box, five alignment/quality landmarks, and
the YuNet row needed by SFace alignment; the detector does not create an embedding.

SFace alignment uses the five YuNet landmarks and produces a 128-element `float32`
embedding, which the adapter L2-normalizes in memory. Embeddings are tagged internally
as `opencv-sface-128d` / `2021dec`; the existing dlib gallery remains
`face-recognition-hog-128d` / `1`. These formats must never be compared with each
other. Existing dlib profiles remain untouched. A successful SFace enrollment creates or
updates only that user's matching `opencv-sface-128d` / `2021dec` profile, so the dlib
profile stays available for an explicit provider rollback.
An explicit re-enrollment (or a separately reviewed migration from source images) is
required before an SFace gallery can be enabled. `FACE_SFACE_COSINE_THRESHOLD` has no default: identity decisions
fail closed until a threshold is deliberately calibrated and configured.

REST enrollment supports the OpenCV adapter only when `FACE_PROVIDER=local_opencv` is
explicitly selected. YuNet exact-one-face detection, the static enrollment quality gate,
SFace alignment/embedding, version checks, and serialization all finish before any User
or FaceProfile lookup or mutation. Failed enrollment therefore leaves existing profiles
untouched. Realtime detection, registration gating, and recognition can use either the
existing `local` dlib path or the opt-in OpenCV provider. SFace recognition loads only
profiles tagged `opencv-sface-128d` / `2021dec`
and remains fail-closed until `FACE_SFACE_COSINE_THRESHOLD` is calibrated. Realtime
alignment evidence stays in backend memory for the current frame only; raw frames and
embeddings are never included in WebSocket events. Multiple-face registration preserves
the existing `multiple_faces_detected` contract and invalidates all stability, voting,
and client-side capture evidence before enrollment can resume.

### Face ID latency benchmark and calibration

The kiosk target is P95 ≤ 3000 ms from the first accepted stable-face observation through
three matching votes to confirmed identity. Run mock and real-provider measurements separately; mock numbers
measure only harness overhead and are never evidence that biometric latency or accuracy
meets the target.

With a working backend virtual environment, run the privacy-safe harness from `backend`:

```powershell
# Harness validation only; does not run biometric models.
python scripts/benchmark_face_pipeline.py --provider mock --iterations 50 --warmup 5

# Backend must already be running with local_opencv, reviewed models, calibrated
# FACE_SFACE_COSINE_THRESHOLD, PostgreSQL, and version-compatible SFace profiles.
python scripts/benchmark_face_pipeline.py --provider local_opencv `
  --image C:\consented-fixtures\single-stable-face.jpg `
  --iterations 50 --warmup 5 --frame-interval-ms 100
```

Set `FACE_DIAGNOSTICS_ENABLED=true` only for the controlled benchmark run; keep it false in
production so boxes, landmarks, quality metrics, distances, and provider diagnostics are not
sent to the kiosk browser. The real run reports P50/P95 for frame decode, YuNet detection, quality/tracking, SFace
embedding, profile query, gallery matching, WebSocket/client round-trip, and total time.
It exits with code `2` when total P95 exceeds 3000 ms. Output contains aggregate timing
only—never the fixture path, image bytes, face coordinates, user ID, or embedding. The
headless round-trip is a transport/client proxy; the running React kiosk additionally
collects `diagnostics.faceLatencyBenchmark`, measured through the next Chromium paint.
Each script sample opens a fresh connection and therefore includes a cold profile query;
use the in-kiosk diagnostic window to compare later warm-gallery attempts in one session.

Recommended starting configuration for a CPU-only kiosk is:

```dotenv
FACE_ANALYSIS_WIDTH=640
FACE_FRAME_INTERVAL_MS=100
FACE_RECOGNITION_CADENCE_MS=500
FACE_YUNET_CONFIDENCE_THRESHOLD=0.9
FACE_YUNET_NMS_THRESHOLD=0.3
REGISTRATION_STABLE_FRAMES=5
REGISTRATION_STABLE_MS=700
# FACE_SFACE_COSINE_THRESHOLD must come from consented calibration; do not copy a generic value.
```

Use 1280×720 camera capture as the first CPU test point while retaining the 640-pixel
YuNet analysis width. Change only one knob per benchmark run. Resolution, sampling, or
cadence may be reduced only if exact-one-face behavior, quality rejection, false-match,
false-non-match, and demographic validation remain acceptable. Never lower YuNet or
matching thresholds merely to reach the latency target. Keep at least 30 measured runs
after warm-up and test cold-start plus warm-gallery behavior.

No GPU is required or assumed: the pinned `opencv-python-headless` package uses the CPU
OpenCV backend. A CUDA-capable OpenCV build is a separately managed deployment artifact,
not supplied by the Python wheel, and should be considered only if CPU YuNet/SFace P95
still misses the target after measurement. Rollback is setting `FACE_PROVIDER=local` and
restoring `FACE_ANALYSIS_WIDTH=640`, `FACE_FRAME_INTERVAL_MS=100`, and
`FACE_RECOGNITION_CADENCE_MS=500`; dlib profiles remain version-isolated.

### OpenCV Face ID E2E and rollout checklist

Treat mock-provider tests as contract and failure-safety tests only. They are never
identity-accuracy evidence. The identity acceptance run must use the target CPU kiosk,
`FACE_PROVIDER=local_opencv`, both reviewed ONNX files with the pinned hashes, a deliberately
calibrated `FACE_SFACE_COSINE_THRESHOLD`, and consented test images/camera subjects stored
outside this repository. Do not save images, frame dumps, embeddings, coordinates, user IDs,
or template values in test output, screenshots, CI artifacts, or logs. Use an isolated
staging database and disposable A/B test accounts; do not run this checklist against the
production database.

Before the run:

- Record the application revision, OpenCV package version, model names/hashes, threshold,
  target hardware, camera settings, and non-biometric aggregate timing configuration in the
  deployment record. Do not record model paths or biometric values.
- Verify the backend starts with `local_opencv`, fails to start with either model missing or
  invalid, and never falls back to `mock`. Confirm the SFace threshold is explicitly set.
- Take a recoverable, access-controlled database backup. Identify every active profile's
  `model_name` / `model_version` and prepare a list of accounts that will also receive an
  SFace enrollment. The version-isolated dlib profile remains intact.
- Disable unattended enrollment during the run. Have A and B give consent, use a disposable
  session, and remove external fixtures and test profiles according to the approved retention
  policy afterward.
- Run the backend and frontend automated suites first. Existing tests cover provider
  availability, 0/1/multiple-face gates, rollback before database mutation, embedding version
  isolation, WebSocket multiple-face reset, stale client evidence, event compatibility, and
  privacy-safe latency summaries. Passing mocks establishes these contracts, not biometric
  accuracy.

Run the following cases through the kiosk web page unless a case explicitly says REST API.
Inspect only status, error code, profile metadata/version, aggregate counters, and identity
label shown by the kiosk; do not enable verbose frame/model logging.

| Case | Procedure | Required result |
| --- | --- | --- |
| A enrollment and recognition | Enroll A from a fresh, stable, one-face window; start a new recognition session and scan A. | Exactly one SFace profile is written only after quality passes; A is returned as A and no embedding appears in REST/WebSocket/UI data. |
| Block B with A+B present | Snapshot B's profile metadata, begin B registration, then keep A and B in frame together. | `multiple_faces_detected` contains only `face_count` and safe guidance; enrollment locks, no `face_quality_good` is emitted, and B has no new or changed profile. |
| Interrupt stability | Let one person begin stabilizing, introduce the second person before the configured frame/time gate completes, then remove them. | All stability/votes/captured evidence reset. Enrollment remains blocked until the remaining single face completes a wholly new stability window. |
| Reject stale A evidence for B | Capture an eligible A window, then change session/registration subject to B or trigger a multiple-face invalidation before submit. | The kiosk refuses capture/submission of the old frame. Only a fresh, same-session, unexpired one-face window can be submitted for B. |
| Cross-identity check | Enroll A and B independently, place both version-compatible profiles in the gallery, and scan several fresh A samples across approved conditions. | Every accepted A result is A or safely unknown; it is never B. Repeat symmetrically for B. Any wrong identity is an immediate no-go. |
| Direct REST 0/1/multiple | Send three consented external fixtures directly to `POST /api/v1/face/enroll` using disposable users and compare profile metadata before/after each request. | 0 faces: HTTP 422 `NO_FACE_DETECTED`, no mutation. One valid face: success and one `opencv-sface-128d` / `2021dec` profile. Two or more: HTTP 422 `MULTIPLE_FACES_DETECTED` with count, no mutation. |
| Dark camera | Test the approved minimum lighting plus a clearly inadequate lighting case. | Adequate samples meet the approved recognition/rejection target. Inadequate samples receive quality guidance or unknown; never a wrong identity and never an enrollment. |
| Complex background | Repeat enrollment/recognition against the representative busiest background, with bystanders outside and then inside the camera field. | Background patterns do not become faces; a bystander in frame invokes exact-one blocking; no wrong identity is returned. |
| Network loss | Disconnect WebSocket during stability and after `face_quality_good`, reconnect, then test a connection loss while REST enrollment is in flight. | Reconnect cannot reuse prior evidence and requires a new stability window. An in-flight REST enrollment that loses its response is resent once with the same `enrollment_id` and yields exactly one profile; a fresh capture is a new enrollment. |
| Model unavailable | On a staging restart only, remove or invalidate one configured model, then restore it. | Startup/provider creation fails clearly without exposing paths and without mock fallback or database mutation. Restoring reviewed files and restarting recovers service. |

For a real run, retain only an anonymous pass/fail matrix, error-code counts, P50/P95 stage
timings, total P95, and the approved false-accept/false-reject aggregate. Run at least 30
post-warm-up latency samples as described above. The performance gate is total P95 no greater
than 3000 ms from accepted stability to the rendered result on the target CPU kiosk. Never
relax exact-one-face or quality gates to meet it.

Go only when every case above passes, the real-provider automated tests and kiosk-browser
smoke test pass, total P95 meets the target, no tested A/B sample is attributed to the other
person, failed enrollment causes no profile mutation, model failure is fail-closed, no
biometric data appears in logs/events/artifacts, and a rollback drill has succeeded. The
owner must approve the representative population, sample count, acceptable false rejection
rate, lighting/background envelope, and calibrated matching threshold; this document does
not invent biometric accuracy targets. Any wrong identity, stale evidence acceptance,
multiple-face enrollment, unexplained profile change, privacy leak, silent fallback, or
missed latency target is no-go.

Roll out in stages: isolated lab database, staffed staging on the target kiosk, one staffed
canary kiosk, then a deliberately limited fleet expansion. Compare aggregate error codes,
unknown/quality-rejection rates, and latency with the approved baseline at each stage. Stop
enrollment and roll back on a no-go signal; do not automatically change thresholds or models.

Rollback is version-aware:

1. Stop new enrollment, drain/stop kiosk sessions, and preserve the incident window's
   non-biometric aggregate metrics.
2. Verify that version-isolated dlib profiles are still active. Restore the access-controlled
   backup or schedule dlib re-enrollment only for users who do not have a valid dlib profile.
3. Set `FACE_PROVIDER=local`, restore the prior sampling settings, restart the backend, and
   run the dlib smoke/identity check before reopening kiosks.
4. Never relabel or compare an SFace vector as dlib. Users enrolled only with SFace require
   consented re-enrollment for dlib. A future SFace model/version change likewise requires
   deliberate re-enrollment or an approved regeneration from retained source images; there
   is no safe vector-to-vector conversion.

One boundary requires an explicit deployment decision: the WebSocket
evidence guard is enforced by the kiosk client, while `POST /face/enroll` does not accept a
server-issued, single-use evidence token; a client that bypasses the kiosk can submit another
single-face image. Require an authenticated kiosk boundary or add server-bound evidence
before rollout if hostile/direct clients are in scope. Enrollment is idempotent: the kiosk
sends a fresh `enrollment_id` with each captured image and, when no response arrives
(network loss, timeout, proxy 502/504), resends the same image once with the same id. The
backend stores the id with the profile in one transaction (`face_enrollment_requests`) and
answers a repeat from the same kiosk within 24 hours with the first result, without saving or
analysing the image again; the same id from another kiosk (409 `ENROLLMENT_ID_CONFLICT`) or
after the Face ID was erased (409 `ENROLLMENT_ALREADY_PROCESSED`) is refused. Templates are
encrypted at rest (see *Data model and boundaries*); retention, backup and access policies for them still
need approval before real school biometric profiles are stored.

### Backend server and kiosk LAN deployment

Keep OpenCV, both ONNX models, PostgreSQL access, and all face templates on the backend
server. Kiosks need only a current Chrome/Edge browser, a camera, a microphone, and network
access to the server's HTTPS port. The Compose stack is the deployment: Uvicorn and the
databases stay on the private Compose network, and the Nginx container terminates TLS and is
the only thing published (443, plus the redirecting `APP_PORT`). Expose only HTTPS/WSS to
kiosks, even on the school LAN; allow 80/443 through the server firewall and nothing else.

TLS uses a certificate from a local CA made with [mkcert](https://github.com/FiloSottile/mkcert),
on the server, from the repository root:

```powershell
mkcert -install                     # once: creates the local CA
mkcert -cert-file certs/server.pem -key-file certs/server-key.pem kiosk-server.library.lan 192.168.1.10
mkcert -CAROOT                      # folder holding rootCA.pem
```

Name the server's DNS name and/or LAN IP, whichever kiosks will type; the certificate only
covers the names listed. Copy **only `rootCA.pem`** to each kiosk and trust it from an
elevated prompt with `certutil -addstore -f Root rootCA.pem` (Chrome and Edge on Windows use
that store). Never copy `rootCA-key.pem` off the server: anyone holding it can impersonate any
site to those kiosks. mkcert certificates last about two years; reissue the server pair before
then and run `docker compose restart frontend`. HSTS is deliberately not sent, so a broken
certificate rollout cannot lock kiosks out.

Leave `VITE_API_BASE_URL` empty for the Compose build: the kiosk then calls the origin it was
opened from, and the WebSocket URL becomes WSS automatically. Also build with `VITE_ENABLE_DEV_CONTROLS=false` and
`VITE_ENABLE_MOCK_FALLBACK=false`. Because Vite embeds these values at build time, changing
them requires rebuilding the frontend image (`frontend/Dockerfile`).

Set `KIOSK_STREAM_ORIGINS` to the smallest reviewed comma-separated allowlist: the exact
HTTPS origin(s) the kiosk page is served from, without a port (for example
`https://kiosk-server.library.lan`, and `https://192.168.1.10` if kiosks use the IP). Never add `null`; origin allowlisting alone is not device authentication; each kiosk must also hold its own
device key (see *Access control*). A key stored on the kiosk can be copied by anyone with
physical or OS access to it, so still restrict the backend to the kiosk VLAN/firewall and
consider mTLS before treating a shared or hostile LAN as trusted; rotate a key whenever a
kiosk is serviced or lost. Do not hard-code server addresses in source or copy ONNX models into
the frontend bundle.

The cached OpenCV detector and recognizer are protected by process-local locks because their
DNN wrapper state is mutable. This is safe for concurrent requests but serializes inference
inside each backend worker. Choose worker count only after measuring server memory and a
representative concurrent-kiosk load; do not claim fleet capacity from single-kiosk latency.

## Change discipline

1. Current source, tests, migrations, and schemas are authoritative; update this brief only for meaningful architecture/scope changes.
2. Preserve kiosk/admin separation and centralized state machine/event bus.
3. Keep biometric templates, raw media, API secrets, and sensitive data out of logs, Git, and events.
4. Do not expand the 24-table schema or mirror the library system of record without an approved requirement.
5. Backend changes: run relevant `pytest` and `alembic upgrade head --sql`. Frontend changes: run relevant `npm run test` and `npm run build`.
6. Before deployment, test migrations against disposable PostgreSQL, test actual kiosk hardware, and close the provider/security gaps above.
