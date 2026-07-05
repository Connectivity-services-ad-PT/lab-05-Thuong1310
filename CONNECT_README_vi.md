TÀI LIỆU KẾT NỐI VÀ HỢP ĐỒNG DỊCH VỤ (Tiếng Việt)

Mục đích
- Tài liệu này mô tả kết nối, schema MQTT/REST và checklist kiểm thử cho hai service: IoT Ingestion (team-iot) và Core Business (team-core).

Chung (broker & secrets)
- Broker MQTT: đặt vào .env của từng service (MQTT_BROKER, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD).
- Không commit credentials. Đọc từ .env.

IoT Ingestion (team-iot)
- Subscribe (raw): smart-campus/raw/iot/environment
- Publish (processed): smart-campus/events/sensor
- File registry (đặt trong thư mục config/): device_registry.csv
- Yêu cầu bắt buộc (tóm tắt): VALIDATE, CHECK device_registry, NORMALIZE, CLASSIFY (normal/warning/danger/sensor_error/invalid_device), PRODUCE event theo schema.

Schema: payload raw (ví dụ nhận vào)
{
  "event_id": "raw-iot-abc123",
  "device_id": "esp32-lab-a101",
  "timestamp": "2026-06-07T14:30:10+07:00",
  "location": "Lab A101",
  "temperature_c": 31.2,
  "humidity_percent": 68.5,
  "motion_detected": false,
  "co2_ppm": 650,
  "smoke_ppm": 0.02,
  "battery_percent": 87,
  "scenario_hint_for_teacher": "normal"
}

Schema: event processed (publish smart-campus/events/sensor)
{
  "event_type": "sensor.reading.processed",
  "source_service": "team-iot",
  "raw_event_id": "raw-iot-abc123",
  "device_id": "esp32-lab-a101",
  "location": "Lab A101",
  "temperature_c": 42.1,
  "humidity_percent": 71.2,
  "motion_detected": true,
  "co2_ppm": 710,
  "smoke_ppm": 0.03,
  "battery_percent": 86,
  "status": "danger",
  "alert_level": "high",
  "reason": "temperature_too_high"
}

Ghi chú xử lý
- Không dùng "scenario_hint_for_teacher" để quyết định nghiệp vụ.
- Load device_registry.csv lúc khởi động và cache.
- Nếu thiếu field bắt buộc: log lỗi, KHÔNG publish event.

Core Business (team-core)
- Subscribe: smart-campus/events/sensor, smart-campus/events/access, smart-campus/events/camera
- Publish alerts: smart-campus/events/alert (ví dụ)
- Có thể gọi REST sync lên Access Gate hoặc AI Vision khi cần dữ liệu bổ sung.
- Yêu cầu bắt buộc: RECEIVE, APPLY POLICY, DECIDE severity, CREATE ALERT, DISPATCH (publish alert to Notification), audit-log.

Alert schema (publish smart-campus/events/alert)
{
  "event_type": "core.alert.created",
  "source_service": "team-core",
  "alert_id": "ALT-001",
  "alert_type": "fire",
  "severity": "critical",
  "message": "Phat hien khoi nong do cao tai Lab A101",
  "origin_event_id": "sensor-event-002",
  "target": "security_team",
  "timestamp": "2026-06-07T14:30:17+07:00"
}

Checklist kiểm thử tích hợp cơ bản
1) Kiểm tra kết nối MQTT: bật client test (mosquitto_sub) subscribe các topic events.
2) Gửi một payload raw hợp lệ đến smart-campus/raw/iot/environment, kiểm tra IoT Ingestion publish smart-campus/events/sensor với status đúng.
3) Gửi payload raw lỗi (thiếu temperature_c) → IoT phải log lỗi và KHÔNG publish.
4) Kiểm tra device không đăng ký → IoT publish status=invalid_device.
5) Core tiêu thụ event sensor danger → Core publish alert trên smart-campus/events/alert.
6) Kiểm tra audit log của Core chứa origin_event_id và quyết định.

Hướng dẫn triển khai nhanh
- Tạo file .env theo mẫu (.env.iot.sample, .env.core.sample).
- Đặt device_registry.csv vào ./config/device_registry.csv với cột device_id, location, meta...
- Chạy local MQTT broker (ví dụ mosquitto) hoặc dùng credential broker được chỉ định.

Liên hệ
- Team-iot: team-iot@example.local
- Team-core: team-core@example.local
