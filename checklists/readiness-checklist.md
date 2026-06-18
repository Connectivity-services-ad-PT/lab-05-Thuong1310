# Readiness Checklist – Lab 05

Đây là danh sách kiểm tra (checklist) để đảm bảo stack Docker Compose của bạn đã sẵn sàng trước khi gửi bài. Hãy tick vào mỗi mục sau khi hoàn thành.

- [x] **Database ready:** container DB đã chạy và phản hồi `pg_isready`. Kiểm tra bằng `docker exec -it fit4110-db-lab05 pg_isready -U $POSTGRES_USER`.
- [x] **AI service ready:** container AI service trả về `200` cho endpoint `/health`, `/predict` hoạt động và `/detect` hỗ trợ khói/nhận diện.
- [x] **API ready:** container API trả `200` cho `/health` và có thể thực hiện thẩm định quyền ra vào (`POST /access/check`) khi token hợp lệ.
- [x] **Environment variables:** `.env` đã được thiết lập đúng (`APP_PORT`, `POSTGRES_USER`, `AUTH_TOKEN`,...). Không sử dụng secret thật; lưu secret vào `.env` cục bộ, commit `.env.example`.
- [x] **Network & Ports:** mạng `team-internal` hoạt động; API gọi được AI bằng hostname `ai-service`; ports 8000 (API), 9000 (AI) và 5432 (DB) được map đúng.
- [x] **Image tags:** bạn đã build image với tag `v0.1.0-team-core` và push lên registry (ghcr.io hoặc Docker Hub). Xác nhận rằng tag xuất hiện trong registry.

Ghi chú thêm những vấn đề gặp phải hoặc điều chỉnh tại đây:

```text
- Đã thay thế API IoT Ingestion mẫu bằng dịch vụ thật của Core Business (A6).
- Đồng bộ và tích hợp thành công container DB (Postgres) và container AI Service chạy Uvicorn phục vụ mock nhận diện cho Newman.
- Đã khắc phục lỗi thiếu thư viện requests trong container AI bằng cách sử dụng urllib.request trong script Healthcheck.
```