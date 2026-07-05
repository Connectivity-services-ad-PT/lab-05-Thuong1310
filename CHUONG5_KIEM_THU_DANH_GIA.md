# Chương 5: Kiểm thử và đánh giá kết quả

## 5.1. Mục tiêu và phạm vi kiểm thử

Chương này trình bày cách kiểm thử hệ thống Core Business theo đúng luồng hiện có trong repo, đặc biệt là các quy trình xử lý event từ IoT, Access Gate và Camera Stream. Nội dung kiểm thử tập trung vào ba mục chính:

1. Xác nhận logic policy hoạt động đúng theo từng loại event.
2. Kiểm tra luồng dữ liệu từ MQTT đến việc tạo và phát hành alert.
3. Đánh giá tính ổn định của hệ thống khi gặp trường hợp AI Vision không phản hồi hoặc event không đầy đủ thông tin.

Các phần logic kiểm thử bám sát thực tế vào các module chính trong [src/core_app/main.py](src/core_app/main.py), [src/handlers/camera_event_handler.py](src/handlers/camera_event_handler.py) và [test_e2e.py](test_e2e.py).

---

## 5.2. Chiến lược kiểm thử

Nhóm áp dụng chiến lược kiểm thử 3 lớp như sau:

### 5.2.1. Unit Test

Kiểm tra từng rule xử lý riêng lẻ bằng pytest và mock, nhằm xác nhận:
- event sensor có trạng thái danger sẽ tạo alert critical;
- event warning sẽ tạo cảnh báo mức medium;
- event access denied lặp lại nhiều lần sẽ kích hoạt alert bruteforce;
- camera event với kết quả AI Vision phù hợp sẽ tạo alert intrusion hoặc suspicious_person.

### 5.2.2. Integration Test

Kiểm tra luồng xử lý end-to-end thông qua các thành phần:
- MQTT broker nhận event từ các topic như smart-campus/events/sensor, smart-campus/events/access và smart-campus/events/camera;
- Core Business xử lý event và gọi AI Vision nếu cần;
- Alert được publish lên topic smart-campus/events/alert và smart-campus/events/policy.

### 5.2.3. Scenario Test

Thực hiện kiểm tra thủ công theo các tình huống nghiệp vụ phổ biến trong campus:
- phát hiện nguy hiểm môi trường;
- phát hiện người lạ tại cổng;
- phát hiện quẹt thẻ thất bại lặp lại.

---

## 5.3. Unit Test cho Policy và Handler

Hiện tại, logic nghiệp vụ chính được triển khai trong [src/core_app/main.py](src/core_app/main.py). Do đó, bộ test nên tập trung vào ba nhóm hàm chính:

### 5.3.1. Test cho Sensor Event

Mục đích: xác minh rằng hệ thống phân loại trạng thái môi trường đúng.

Các case kiểm thử đề xuất:

| Test case | Input | Kết quả mong đợi |
|---|---|---|
| sensor_danger_creates_critical_alert | status = danger | Tạo alert severity = critical, alert_type = fire |
| sensor_warning_creates_medium_alert | status = warning | Tạo alert severity = medium, alert_type = environment_warning |
| sensor_normal_no_alert | status = normal | Không tạo alert |

### 5.3.2. Test cho Access Event

Mục đích: kiểm tra logic đếm số lần denied và phát hiện truy cập bất thường.

| Test case | Input | Kết quả mong đợi |
|---|---|---|
| first_denied_no_alert | denied lần đầu | Không tạo alert |
| third_denied_creates_medium_alert | denied liên tiếp 3 lần cho cùng uid | Tạo alert medium, alert_type = access_bruteforce |
| granted_resets_counter | sau denied thì nhận granted | Reset bộ đếm và không tạo alert tiếp theo |

### 5.3.3. Test cho Camera Event

Mục đích: kiểm tra logic phát hiện bất thường dựa trên kết quả AI Vision và tín hiệu access gần đó.

| Test case | Input | Kết quả mong đợi |
|---|---|---|
| intrusion_when_denied_nearby | motion=true, label=person, confidence >= 0.8, risk medium/high, có denied gần đây | Tạo alert critical, alert_type = intrusion |
| suspicious_person_when_high_risk | motion=true, label=person, confidence >= 0.8, risk medium/high | Tạo alert high, alert_type = suspicious_person |
| low_priority_when_ai_unavailable | AI Vision không phản hồi | Tạo alert low, alert_type = camera_vision_unavailable |

Một mẫu testcase có thể viết như sau:

```python
from unittest.mock import patch
from core_app.main import handle_sensor_event


def test_sensor_danger_creates_critical_alert():
    event = {
        "status": "danger",
        "location": "Lab A101",
        "reason": "smoke_too_high",
        "raw_event_id": "raw-001"
    }

    with patch("core_app.main.publish_alert") as mock_publish:
        handle_sensor_event(event)

    assert mock_publish.called
```

---

## 5.4. Kiểm thử tích hợp và luồng thực tế

Để kiểm tra hệ thống gần với môi trường vận hành, nhóm sử dụng script [test_e2e.py](test_e2e.py). Script này thực hiện các bước sau:

1. Kết nối tới MQTT broker.
2. Publish các event mẫu lên các topic tương ứng.
3. Quan sát các message xuất hiện trên topic alert hoặc policy.
4. Ghi nhận xem hệ thống có tạo alert đúng loại và đúng mức độ hay không.

### 5.4.1. Luồng kiểm thử tích hợp thực tế

- Sensor event: publish payload có status = danger lên topic smart-campus/events/sensor.
- Access event: publish payload access_result = denied lên topic smart-campus/events/access.
- Camera event: publish payload có motion_detected = true cùng với dữ liệu AI Vision phản hồi.
- Core Business: xử lý và tạo alert dựa trên rule hiện tại.
- Kết quả: alert xuất hiện trên topic smart-campus/events/alert.

### 5.4.2. Điểm cần lưu ý khi chạy integration test

- Nếu MQTT broker không sẵn sàng, luồng test sẽ thất bại ở bước kết nối.
- Nếu AI Vision không phản hồi, hệ thống vẫn không crash nhưng sẽ tạo alert mức low theo logic hiện có.
- Dữ liệu trạng thái như denied counter và recent_events được lưu trong bộ nhớ, nên sau khi restart service, trạng thái sẽ bị reset.

---

## 5.5. Kiểm thử theo kịch bản nghiệp vụ

### 5.5.1. Kịch bản 1 – Cảnh báo môi trường nguy hiểm

- Mô tả: Sensor phát hiện smoke_ppm cao tại Lab A101.
- Input thực tế: event có status = danger, reason = smoke_too_high.
- Kết quả mong đợi: Core Business tạo alert critical và publish sang topic alert.
- Đánh giá: phù hợp với mục tiêu cảnh báo nguy hiểm sớm.

### 5.5.2. Kịch bản 2 – Phát hiện người lạ tại cổng

- Mô tả: Camera phát hiện motion và AI Vision trả về label = person, confidence cao, risk_level = high tại cổng chính.
- Input thực tế: event camera kèm tín hiệu motion_detected = true.
- Kết quả mong đợi: tạo alert high hoặc critical nếu có event denied gần đây.
- Đánh giá: phản ánh đúng nhu cầu giám sát an ninh và phát hiện đột nhập.

### 5.5.3. Kịch bản 3 – Quẹt thẻ bị từ chối lặp lại

- Mô tả: Một UID bị denied nhiều lần liên tiếp tại cùng cổng.
- Input thực tế: các event access_result = denied liên tiếp được gửi tới Core.
- Kết quả mong đợi: sau lần denied thứ 3, hệ thống tạo alert medium.
- Đánh giá: phù hợp với logic phát hiện hành vi truy cập bất thường.

---

## 5.6. Đánh giá theo tiêu chí nghiệp vụ

| Tiêu chí đánh giá | Trạng thái | Minh chứng thực tế |
|---|---|---|
| Có bộ luật phân loại event | Đạt | Logic hiện có phân biệt sensor, access và camera |
| Có phân mức severity | Đạt | Hệ thống dùng các mức critical, medium, high, low |
| Có luồng alert đến downstream | Đạt | Alert được publish qua MQTT thông qua publish_alert |
| Có xử lý lỗi khi AI Vision không phản hồi | Đạt | Service không crash và tạo alert mức low thay thế |
| Có khả năng phát hiện hành vi bất thường | Đạt | Rule camera + denied nearby và denied counter đều có cơ chế phát hiện |
| Còn hạn chế về trạng thái lưu trữ | Cần cải thiện | Bộ đếm và recent_events đang lưu trong bộ nhớ, không bền vững sau restart |

---

## 5.7. Nhận xét chung

Hệ thống hiện tại đã có nền tảng kiểm thử và logic nghiệp vụ khá rõ ràng, đặc biệt ở các khía cạnh phân loại event, phát hiện nguy cơ và tạo alert. Tuy nhiên, để nâng cao độ tin cậy, nhóm nên tiếp tục bổ sung unit test tự động cho từng rule, đồng thời chạy integration test trên môi trường thật để đối chiếu kết quả với các kịch bản thực tế. Điều này giúp hệ thống không chỉ đúng về mặt logic mà còn ổn định hơn khi triển khai trong môi trường campus thực tế.

---

Phụ lục A — Thông tin repo

- Link repository: ____________________________________
- Nhánh chính: ________________________________________
- Hướng dẫn chạy (RUN_COMPOSE.md): có / không
- Tag image: _________________________________________

Lệnh chạy nhanh:

```bash
git clone <repo>

cp .env.example .env

docker compose up -d --build

docker compose ps

curl http://localhost:8000/health
```
