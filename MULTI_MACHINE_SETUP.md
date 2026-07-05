# Multi-Machine Setup: IoT → Core Business

Hướng dẫn chạy trên 2 máy khác nhau kết nối qua MQTT broker chung.

## Kiến trúc

```
┌─────────────────────────┐
│   Machine 1 (IoT Team)  │
│  - iot_ingestion.py     │
│  - Publish raw events   │
│  - Publish sensor events│
└────────────┬────────────┘
             │ MQTT
             │ (TCP/IP)
        ┌────▼────┐
        │  MQTT   │
        │ Broker  │ (localhost:1883 hoặc IP:1883)
        └────┬────┘
             │ MQTT
             │ (TCP/IP)
┌────────────▼────────────┐
│ Machine 2 (Your Machine)│
│  - core_business_service.py
│  - Subscribe sensor events
│  - Create alerts        │
└─────────────────────────┘
```

---

## Bước 1: Chuẩn bị MQTT Broker

### Option A: Broker chạy trên Machine 1 (IoT)

**Machine 1:**
```bash
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto
```

**Ghi nhớ IP của Machine 1** (ví dụ: `192.168.1.100`)

### Option B: Broker chạy trên máy riêng

**Trên máy chạy broker:**
```bash
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto
```

**Ghi nhớ IP** (ví dụ: `192.168.1.50`)

---

## Bước 2: Cấu hình Machine 1 (IoT Ingestion)

### Lệnh khởi động trên Machine 1:

```bash
# Clone/pull repo trên Machine 1
cd lab-05-Thuong1310

# Cài dependencies
py -m pip install -r requirements.txt

# Thiết lập .env với IP của MQTT broker
# Ví dụ: MQTT broker chạy trên 192.168.1.50

set MQTT_BROKER=192.168.1.50
set MQTT_PORT=1883

# Chạy IoT Ingestion
py src/iot_ingestion.py
```

**Hoặc cập nhật `.env`:**
```
MQTT_BROKER=192.168.1.50
MQTT_PORT=1883
```

Rồi chạy:
```bash
py src/iot_ingestion.py
```

---

## Bước 3: Cấu hình Machine 2 (Your Machine - Core Business)

### Lệnh khởi động trên Machine 2:

```bash
# Clone/pull repo trên Machine 2
cd lab-05-Thuong1310

# Cài dependencies
py -m pip install -r requirements.txt

# Thiết lập .env với IP của MQTT broker (trỏ đến Machine 1)
# Ví dụ: MQTT broker chạy trên 192.168.1.50

set MQTT_BROKER=192.168.1.50
set MQTT_PORT=1883

# Chạy Core Business
py src/core_business_service.py
```

**Hoặc cập nhật `.env`:**
```
MQTT_BROKER=192.168.1.50
MQTT_PORT=1883
```

Rồi chạy:
```bash
py src/core_business_service.py
```

---

## Bước 4: Gửi dữ liệu từ Machine 1

### Chạy demo script trên Machine 1 (Terminal riêng)

```bash
# Trên Machine 1, Terminal thứ 2
set MQTT_BROKER=192.168.1.50
set MQTT_PORT=1883

py demo_iot_to_core.py
```

---

## Bước 5: Kiểm tra kết quả

### Monitor trên Machine 2 (Terminal riêng)

```bash
# Xem events sensor được publish từ Machine 1
mosquitto_sub -h 192.168.1.50 -p 1883 -t smart-campus/events/sensor

# Xem alerts được tạo bởi Core Business
mosquitto_sub -h 192.168.1.50 -p 1883 -t smart-campus/events/alert
```

---

## Ví dụ cụ thể

### Machine 1 (192.168.1.100) - Team IoT

**Terminal 1: Khởi động Broker (nếu cần)**
```bash
docker run -d --name mosquitto -p 1883:1883 eclipse-mosquitto
```

**Terminal 2: Chạy IoT Ingestion**
```bash
cd lab-05-Thuong1310
set MQTT_BROKER=192.168.1.100
py src/iot_ingestion.py
```
Output:
```
2026-06-23 10:00:00 INFO Connected to MQTT broker 192.168.1.100:1883
2026-06-23 10:00:00 INFO Subscribed to raw topic: smart-campus/raw/iot/environment
```

**Terminal 3: Publish sample events**
```bash
set MQTT_BROKER=192.168.1.100
py demo_iot_to_core.py
```

---

### Machine 2 (192.168.1.200) - Your Machine (Team Core)

**Terminal 1: Chạy Core Business**
```bash
cd lab-05-Thuong1310
set MQTT_BROKER=192.168.1.100
py src/core_business_service.py
```
Output:
```
2026-06-23 10:00:00 INFO Connected to MQTT broker 192.168.1.100:1883
2026-06-23 10:00:00 INFO Subscribed to events topics: sensor, access, camera
```

**Terminal 2: Monitor alerts**
```bash
mosquitto_sub -h 192.168.1.100 -p 1883 -t smart-campus/events/alert
```
Output (khi có alert):
```
{"event_type": "core.alert.created", "alert_id": "ALT-000001", "severity": "critical", ...}
```

---

## Ghi chú quan trọng

- ✅ **IP phải giống nhau** trên tất cả machines (máy nào chạy broker)
- ✅ **Port 1883** phải open firewall giữa 2 máy
- ✅ Nếu MQTT Broker chạy trên Machine 1 → tất cả machines trỏ `MQTT_BROKER=<IP_Machine_1>`
- ✅ `.env` hoặc environment variables sẽ override cấu hình
- ❌ Đừng dùng `localhost` trên machines khác nhau (nó chỉ trỏ đến máy cục bộ)

---

## Troubleshoot

### Kết nối MQTT bị từ chối

```bash
# Kiểm tra broker đang chạy
netstat -an | findstr :1883

# Kiểm tra ping đến machine kia
ping 192.168.1.100

# Test MQTT connection
mosquitto_sub -h 192.168.1.100 -p 1883 -t test
```

### Không nhận được event

- Kiểm tra IoT Ingestion đang chạy trên Machine 1
- Kiểm tra Core Business đang subscribe đúng topic
- Kiểm tra MQTT_BROKER cấu hình giống nhau ở cả 2 máy

### Firewall chặn

- Mở port 1883 TCP trên máy chạy broker
- Windows: `netsh advfirewall firewall add rule name="MQTT" dir=in action=allow protocol=tcp localport=1883`
- Linux: `ufw allow 1883`
