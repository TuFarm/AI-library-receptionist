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

- `FACE_PROVIDER=mock` runs without native packages. `local` lazily uses `face_recognition`/dlib (CPU HOG, 128-d encodings) and can require CMake/Visual C++ Build Tools on Windows. `local_opencv` is an opt-in YuNet + SFace ONNX provider; it is not the default and never downloads model files at runtime.
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
VITE_KIOSK_CAMERA_WIDTH=1280
VITE_KIOSK_CAMERA_HEIGHT=720
```

Optional local face support is in `backend/requirements-face-local.txt`; install it separately so missing native dependencies cannot prevent FastAPI startup.

### Optional OpenCV ONNX Face ID

Install `backend/requirements-face-opencv.txt` only on hosts that will explicitly use
`FACE_PROVIDER=local_opencv`. The pinned package is the headless OpenCV build because
camera capture and UI remain in Electron/React. OpenCV supplies its compatible NumPy
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
sent to the Electron client. The real run reports P50/P95 for frame decode, YuNet detection, quality/tracking, SFace
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

Run the following cases through the packaged kiosk unless a case explicitly says REST API.
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
| Network loss | Disconnect WebSocket during stability and after `face_quality_good`, reconnect, then test a connection loss while REST enrollment is in flight. | Reconnect cannot reuse prior evidence and requires a new stability window. For an ambiguous REST result, check the database before any manual retry; do not blindly retry enrollment. |
| Model unavailable | On a staging restart only, remove or invalidate one configured model, then restore it. | Startup/provider creation fails clearly without exposing paths and without mock fallback or database mutation. Restoring reviewed files and restarting recovers service. |

For a real run, retain only an anonymous pass/fail matrix, error-code counts, P50/P95 stage
timings, total P95, and the approved false-accept/false-reject aggregate. Run at least 30
post-warm-up latency samples as described above. The performance gate is total P95 no greater
than 3000 ms from accepted stability to the rendered result on the target CPU kiosk. Never
relax exact-one-face or quality gates to meet it.

Go only when every case above passes, the real-provider automated tests and packaged-kiosk
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

Two current boundaries require an explicit deployment decision. First, the WebSocket
evidence guard is enforced by the kiosk client, while `POST /face/enroll` does not accept a
server-issued, single-use evidence token; a client that bypasses the kiosk can submit another
single-face image. Require an authenticated kiosk boundary or add server-bound evidence
before rollout if hostile/direct clients are in scope. Second, enrollment has no idempotency
key, so a network loss after commit has an ambiguous client outcome. Operators must inspect
profile state before retrying, or idempotent enrollment must be added before unattended use.
Third, despite the historical `face_template_encrypted` column name, the current application
serializes embeddings as JSON bytes and does not encrypt them itself. Before storing real
school biometric profiles, approve key management and application-layer envelope encryption
(or an equivalent reviewed data-at-rest control), retention/deletion, backup, and access
policies. Do not infer encryption merely from the column name.

### Backend server and kiosk LAN deployment

Keep OpenCV, both ONNX models, PostgreSQL access, and all face templates on the backend
server. Kiosks need only the packaged Electron application, a camera, and network access to
the configured backend URL. Run Uvicorn behind a managed reverse proxy, binding the private
application listener deliberately (for example `--host 0.0.0.0`) and restricting its port at
the host/network firewall. Terminate TLS at the reverse proxy and expose only HTTPS/WSS to
kiosks, even on the school LAN.

Build each production kiosk with `VITE_API_BASE_URL` set to the stable HTTPS backend DNS
name, not a hard-coded machine IP or localhost. The WebSocket URL is derived from this value
and becomes WSS automatically. Also build with `VITE_ENABLE_DEV_CONTROLS=false` and
`VITE_ENABLE_MOCK_FALLBACK=false`. Because Vite embeds these values at build time, changing
them requires rebuilding the Electron renderer/package.

Set `KIOSK_STREAM_ORIGINS` to the smallest reviewed comma-separated allowlist. Packaged
Electron currently uses a `file://` renderer and therefore sends the `null` WebSocket origin;
origin allowlisting alone is not device authentication. Restrict the backend to the kiosk
VLAN/firewall and add an authenticated kiosk or mTLS boundary before treating a shared or
hostile LAN as trusted. Do not hard-code server addresses in source or copy ONNX models into
the Electron package.

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
