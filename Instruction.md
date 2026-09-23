2. Đăng — Admin, API nghiệp vụ và dashboard

Trách nhiệm

· Hoàn thiện admin page thay cho UI mock.

· Quản lý hồ sơ người dùng không sinh trắc học: họ tên, MSSV, email, số điện thoại, khoa, ngành, năm nhập học.

· Làm dashboard cơ bản: số lượt kiosk, nhận diện thành công/thất bại, thời gian chờ, lỗi camera/network.

· Viết API, validation, phân quyền cơ bản và test.

· Tích hợp API RAG nếu Thiên không thể làm phần kết nối.

Không được sửa

· backend/app/vision/

· backend/app/services/face_service.py

· Luồng enrollment/recognition.

· Electron camera bridge.

· Migration do người khác đang thực hiện, trừ khi đã thống nhất.

Phạm vi gợi ý

· backend/app/api/v1/routes/admin.py

· backend/app/api/v1/routes/users.py

· backend/app/schemas/

· frontend/src/pages/

· frontend/src/components/admin/

· Test API/admin tương ứng.

Lộ trình AI giao việc

1. Liệt kê màn admin hiện có, API thật và API mock.

2. Hoàn thiện CRUD hồ sơ người dùng không bao gồm Face ID.

3. Thêm validation và trạng thái lỗi/thành công.

4. Tạo API thống kê đọc-only.

5. Tạo dashboard hiển thị dữ liệu thật.

6. Viết test API và test UI cho các luồng quan trọng.

7. Đưa lên PR nhỏ theo từng màn hoặc endpoint.

Kiến thức cần học

· React component, form, state và gọi REST API.

· FastAPI router, Pydantic schema, HTTP status code.

· SQLAlchemy model/query cơ bản.

· Validation dữ liệu và phân quyền.

· Git branch, commit, Pull Request.

· Khác biệt giữa hồ sơ cá nhân và dữ liệu Face ID.

Prompt mẫu cho AI

Đọc README.md và các API/admin page hiện có trước khi sửa.


Task: Hoàn thiện [TÊN MÀN HÌNH HOẶC API] cho admin.


Chỉ được sửa mã admin, user profile không sinh trắc học, schema/API/test liên quan.

Không sửa Face ID, vision engine, Electron, WebSocket runtime hoặc state machine kiosk.


Yêu cầu:

1. Phân tích API và UI hiện tại.

2. Nêu kế hoạch ngắn.

3. Implement validation, loading, success và error state.

4. Viết test phù hợp.

5. Chạy test/build.

6. Không log dữ liệu nhạy cảm.

7. Không commit/push.