> **2026-09-05 runtime update:** The active kiosk now uses continuous WebSocket face tracking and three-observation recognition, an assistant-centered UI and automatic voice turns. The older capture/countdown instructions below are historical. See [runtime architecture](docs/kiosk/RUNTIME_ARCHITECTURE.md), [event system](docs/kiosk/EVENT_SYSTEM.md), [stream protocol](docs/kiosk/STREAMING_ARCHITECTURE.md), [state machine](docs/kiosk/STATE_MACHINE.md), [Electron readiness](docs/kiosk/ELECTRON_READY.md), and [testing/report](docs/kiosk/TESTING_REALTIME.md).
>
> Realtime detection requires the optional local FaceID dependencies. Use `FACE_PROVIDER=local` for actual matching. Idle wake-up requires an external presence sensor; developer mode provides explicit presence simulation while keeping the camera off at idle. Browser speech support, hardware quality thresholds and unattended Windows deployment still require validation. The database and Gemini business integration were not redesigned.

# Trợ lý Lễ tân Thư viện AI

Monorepo cho trợ lý lễ tân/kiosk thư viện đại học, gồm backend FastAPI, PostgreSQL, Redis và giao diện React/TypeScript. Đây không phải hệ thống quản lý thư viện hay mượn/trả.

> Trạng thái hiện tại: Phase 5 đã bổ sung đăng ký khuôn mặt, provider FaceID local tùy chọn, Gemini thật có fallback, lời chào/TTS và vòng hội thoại giọng nói theo lượt. RAG, streaming voice và bảo mật sinh trắc học production chưa được triển khai.

Frontend có hai chế độ độc lập: Admin Web tại `/admin` dành cho nhân viên và Kiosk fullscreen tại `/kiosk/fullscreen` dành cho sinh viên. Kiosk vận hành theo luồng trạng thái tự động, không dùng sidebar như một website thông thường.

Backend ghi session, event, hội thoại, AI history, FaceID log và khảo sát vào PostgreSQL. FaceID mặc định vẫn là `mock`; có thể bật provider `local`. Gemini được dùng khi `AI_PROVIDER=gemini` và có API key. Trình duyệt/Electron thu camera, Web Speech và phát TTS.

## Kiến trúc tổng quan

```text
nlu-library-ai/
├── backend/
│   ├── app/
│   │   ├── api/v1/routes/       # API runtime kiosk và các module quản trị
│   │   ├── core/                # Cấu hình, engine và SQLAlchemy Base
│   │   ├── models/              # Đúng 24 bảng cho AI kiosk assistant
│   │   └── services/            # Biên tích hợp nghiệp vụ/Gemini
│   ├── alembic/                 # Hai migration database
│   └── tests/                   # Kiểm tra metadata, FK, constraint và model
├── frontend/
│   ├── src/                     # React + TypeScript + React Router
│   └── electron/                # Vỏ ứng dụng kiosk Electron
├── docs/database/               # Design, ERD, data dictionary và redesign log
└── docker-compose.yml           # PostgreSQL 16 và Redis 7
```

### Công nghệ

- Backend: Python, FastAPI, SQLAlchemy 2.x
- Database: PostgreSQL 16, Alembic, UUID, JSONB, INET
- Cache/session infrastructure: Redis 7
- Frontend: React, TypeScript, Vite
- Kiosk desktop: Electron
- AI integration boundary: Gemini API
- AI/RAG: nguồn tri thức → tài liệu → chunk, hội thoại, prompt và feedback

## Yêu cầu trước khi cài đặt

- Git
- Docker Desktop hoặc Docker Engine có Docker Compose v2
- Python 3.12 được khuyến nghị. Python 3.14 có thể gặp vấn đề tương thích với một số binary dependency chưa phát hành wheel phù hợp.
- Node.js 20 trở lên và npm

Kiểm tra các công cụ:

```bash
git --version
docker --version
docker compose version
python --version
node --version
npm --version
```

Trên Windows, nếu lệnh `python` không tồn tại, thử `py -3.12` và thay `python` trong các lệnh bên dưới bằng lệnh đó.

## Hướng dẫn cài đặt và chạy từng bước

### Bước 1: Lấy mã nguồn

```bash
git clone <repository-url>
cd nlu-library-ai
```

Nếu đã có mã nguồn, mở terminal tại thư mục gốc chứa `docker-compose.yml`.

### Bước 2: Tạo cấu hình backend

Windows PowerShell:

```powershell
Copy-Item backend/.env.example backend/.env
```

macOS/Linux:

```bash
cp backend/.env.example backend/.env
```

Nội dung mặc định:

```dotenv
APP_NAME=NLU AI Library Receptionist Assistant
API_V1_PREFIX=/api/v1
DATABASE_URL=postgresql+psycopg://ai_library:ai_library_dev@localhost:5432/ai_library
REDIS_URL=redis://localhost:6379/0
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.8-flash
FACE_PROVIDER=mock
VOICE_PROVIDER=browser
AI_PROVIDER=mock
```

Không commit `backend/.env` hoặc API key thật. Nếu `AI_PROVIDER=gemini` nhưng key trống hoặc Gemini lỗi, backend lưu trạng thái fallback và trả lời an toàn bằng mock thay vì làm hỏng phiên kiosk.

Docker Compose đọc file `.env` ở thư mục gốc nếu có. Khi dùng thông số mặc định, không cần tạo file này. Nếu muốn tùy chỉnh container, tạo `.env` tại thư mục gốc:

```dotenv
POSTGRES_DB=ai_library
POSTGRES_USER=ai_library
POSTGRES_PASSWORD=ai_library_dev
POSTGRES_PORT=5432
REDIS_PORT=6379
```

Khi đổi thông tin PostgreSQL ở file gốc, phải cập nhật `DATABASE_URL` trong `backend/.env` tương ứng.

### Bước 3: Khởi động PostgreSQL và Redis

Tại thư mục gốc:

```bash
docker compose up -d
docker compose ps
```

Hai service cần chuyển sang trạng thái `healthy`. Xem log khi có lỗi:

```bash
docker compose logs -f postgres
docker compose logs -f redis
```

### Bước 4: Tạo môi trường Python và cài backend

Windows PowerShell:

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

macOS/Linux:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Các lệnh backend sau đây phải chạy trong thư mục `backend` và khi virtual environment đang được kích hoạt.

FaceID local là tùy chọn vì `dlib` có thể khó cài trên Windows:

```powershell
python -m pip install -r requirements-face-local.txt
```

Sau đó đặt `FACE_PROVIDER=local`. Nếu không cài được, giữ `FACE_PROVIDER=mock`; backend vẫn khởi động bình thường.

### Bước 5: Tạo database schema bằng Alembic

Đảm bảo PostgreSQL đang chạy, sau đó:

```bash
alembic upgrade head
alembic current
python scripts/seed_dev.py
```

Migration hiện có: `20260902_0001_ai_kiosk_schema.py`, tạo đúng 24 bảng của AI kiosk assistant.

Kiểm tra SQL mà không thực thi:

```bash
alembic upgrade head --sql
```

Chỉ dùng downgrade trên database phát triển và sau khi đã sao lưu:

```bash
alembic downgrade -1
```

### Bước 6: Chạy kiểm thử backend

```bash
python -m pytest -q
```

Test hiện kiểm tra mapper/metadata SQLAlchemy, PostgreSQL DDL, bảng quan trọng, khóa ngoại, constraint, grain của fact table và an toàn cascade.

### Bước 7: Chạy FastAPI backend

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Mở các địa chỉ:

- Health check: [http://localhost:8000/health](http://localhost:8000/health)
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- OpenAPI JSON: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

Kết quả health check mong đợi:

```json
{"success":true,"message":"OK","data":{"status":"ok","app":"AI Library Receptionist Assistant"}}
```

FastAPI không tự tạo PostgreSQL database hoặc tables khi khởi động. SQLAlchemy chỉ kết nối khi có query. Sau `alembic upgrade head`, kiểm tra kết nối thực tế tại `GET /api/v1/health/db`.

### Bước 8: Cài và chạy frontend web

Mở terminal thứ hai tại thư mục gốc:

```bash
cd frontend
npm install
npm run dev
```

Mở [http://localhost:5173](http://localhost:5173). Vite lắng nghe trên `0.0.0.0:5173`, phù hợp cho thử nghiệm trong mạng nội bộ hoặc kiosk.

- Landing chọn chế độ: `http://localhost:5173/`
- Admin Web: `http://localhost:5173/admin`
- Kiosk fullscreen: `http://localhost:5173/kiosk/fullscreen`

Tạo `frontend/.env` từ `frontend/.env.example` nếu cần đổi backend, mã thiết bị, mock fallback, timeout hoặc dev controls. Tại kiosk fullscreen, camera chạy nền và tự xác nhận hiện diện; người dùng không cần bấm nút bắt đầu. Kiosk hướng dẫn ổn định khuôn mặt, đếm ngược, chụp đúng một ảnh, xác minh, chào bằng TTS rồi tự mở micro sau 500 ms im lặng. Nếu Web Speech không được hỗ trợ, ô nhập bàn phím mới xuất hiện.

Phase 5.5 centralizes production timing and the continuous Electron-ready state machine. See [Kiosk UX runtime](docs/kiosk/KIOSK_UX_RUNTIME.md), [state timeline](docs/kiosk/STATE_TIMELINE.md), and [Electron readiness](docs/kiosk/ELECTRON_READY.md).

### Bước 9: Chạy chế độ kiosk Electron

Sau khi đã chạy `npm install`:

```bash
npm run electron:dev
```

Lệnh này khởi động Vite, chờ cổng 5173 sẵn sàng rồi mở Electron.

Build frontend web:

```bash
npm run build
npm run preview
```

Build bộ cài Electron:

```bash
npm run electron:build
```

Artifact được tạo trong `frontend/release/`. Quá trình build Electron có thể cần tải binary từ Internet.

## Quy trình chạy hằng ngày

Từ thư mục gốc:

```bash
docker compose up -d
```

Terminal backend:

```bash
cd backend
# Kích hoạt .venv
alembic upgrade head
uvicorn app.main:app --reload
```

Terminal frontend:

```bash
cd frontend
npm run dev
```

Dừng ứng dụng bằng `Ctrl+C`. Dừng hạ tầng:

```bash
docker compose down
```

Lệnh trên giữ dữ liệu trong Docker volumes. Chỉ dùng `docker compose down -v` khi chắc chắn muốn xóa toàn bộ dữ liệu PostgreSQL và Redis cục bộ.

## Database AI kiosk

Schema có đúng 24 bảng, tập trung vào:

- User/student cơ bản và preference
- Face profile, FaceID attempt, device và anonymous/identified session
- Interaction events
- Knowledge source → document → chunk cho RAG
- Conversation → message → AI request → response → feedback
- Prompt versioning
- Category và suggested book đơn giản, có optional external library ID
- Survey và daily report metrics

Đây không phải hệ thống quản lý thư viện. Catalog đầy đủ, tác giả, nhà xuất bản, bản sao, kệ, mượn/trả, recommendation engine, experiment framework và data warehouse không nằm trong schema này.

Tài liệu quan trọng:

- [Thiết kế database](docs/database/DATABASE_DESIGN.md)
- [ERD](docs/database/ERD.md)
- [Data dictionary](docs/database/DATA_DICTIONARY.md)
- [AI learning và reporting data](docs/database/AI_LEARNING_VS_REPORTING_DATA.md)
- [Database redesign changelog](docs/database/CHANGELOG_DATABASE_REDESIGN.md)

## Xử lý lỗi thường gặp

### Backend không kết nối được PostgreSQL

- Chạy `docker compose ps` và kiểm tra `postgres` healthy.
- Đối chiếu `DATABASE_URL` với tài khoản và cổng Docker Compose.
- Kiểm tra cổng 5432 có bị PostgreSQL khác chiếm dụng không.
- Xem `docker compose logs postgres`.
- Nếu database chưa tồn tại, tạo trong DBeaver, dùng `createdb ai_library`, hoặc kiểm tra tên `POSTGRES_DB` trong Docker Compose.

### Alembic không tìm thấy module `app`

Bạn đang chạy lệnh sai thư mục. Hãy `cd backend` trước khi chạy Alembic.

### PowerShell không cho kích hoạt virtual environment

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### Frontend không mở được

- Kiểm tra `npm install` đã hoàn tất.
- Kiểm tra cổng 5173 chưa bị ứng dụng khác sử dụng.
- Chạy lại `npm run dev` và xem URL Vite in trong terminal.

### Tạo migration mới

Sau khi sửa model:

```bash
cd backend
alembic revision --autogenerate -m "mo ta thay doi"
alembic upgrade head
python -m pytest -q
```

Luôn đọc và review migration được sinh ra trước khi chạy trên database dùng chung.

## Trạng thái triển khai sau Phase 5

Đã sẵn sàng để thử trên laptop:

- session kiosk, timeout và tự trở về idle;
- camera permission, fullscreen aspect-preserving preview, native-resolution JPEG streaming and automatic recognition;
- recognized/unknown welcome with continuous scanning and no guest/retry controls;
- form tạo/cập nhật user và đăng ký mẫu khuôn mặt;
- FaceID local tùy chọn với embedding 128 chiều và so khớp nhiều profile;
- Gemini REST với lịch sử hội thoại, system instruction tiếng Việt và fallback có ghi nhận;
- vòng Web Speech → AI → SpeechSynthesis → Web Speech, cùng text fallback;
- dữ liệu thể loại/sách/khảo sát từ backend;
- fallback có kiểm soát bằng `VITE_ENABLE_MOCK_FALLBACK`;
- fullscreen web và Electron development shell.

Xem [FaceID runtime](docs/kiosk/FACEID_RUNTIME.md), [Voice runtime](docs/kiosk/VOICE_RUNTIME.md), [kiểm thử camera/mic](docs/kiosk/TESTING_CAMERA_MIC.md), [Gemini](docs/backend/GEMINI_INTEGRATION.md), [face provider](docs/backend/FACE_PROVIDER.md) và [state machine](docs/kiosk/KIOSK_STATE_MACHINE.md).

## Những phần chưa triển khai

- CRUD/API nghiệp vụ hoàn chỉnh
- Authentication và phân quyền runtime
- FaceID production: liveness, encryption/key management, consent, retention và deletion
- RAG/tài liệu chính thức; câu trả lời Gemini hiện chưa grounded
- Redis cache/session client
- Job tổng hợp `daily_report_metrics`
- Streaming/full-duplex voice và STT onsite độc lập trình duyệt
- Basic dashboard API và UI hoàn chỉnh
- CI/CD và cấu hình production

Biometric template chỉ được thiết kế dưới dạng dữ liệu mã hóa hoặc secure external reference. Việc mã hóa, quản lý khóa, phân quyền, retention và audit phải được triển khai ở tầng security/service trước khi sử dụng FaceID thật.

## Nguyên tắc đóng góp

1. Không sửa migration đã chạy trên môi trường dùng chung; tạo revision mới.
2. Giữ event/audit tables theo hướng append-only.
3. Không lưu plaintext password, raw face image hoặc prompt nhạy cảm mặc định.
4. Thêm constraint/index có lý do và cập nhật tài liệu liên quan.
5. Chạy backend tests và frontend build trước khi gửi thay đổi.
6. Không commit `.env`, API key, database dump, virtual environment hoặc artifact build.
