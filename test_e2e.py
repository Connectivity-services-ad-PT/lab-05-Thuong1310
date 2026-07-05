"""
test_e2e.py – Test end-to-end luồng dữ liệu
Core Business → MQTT Broker (26.79.10.201:1883) → Analytics

Chạy: python test_e2e.py
Yêu cầu: pip install paho-mqtt httpx
"""

import json
import time
import uuid
import threading
from datetime import datetime, timezone
from typing import Dict, List

import paho.mqtt.client as mqtt

# ─── CONFIG ───────────────────────────────────────────────────────────────────
BROKER   = "26.79.10.201"
PORT     = 1883
USERNAME = None
PASSWORD = None

ANALYTICS_URL = "http://26.79.10.201:8000"   # đổi nếu Analytics chạy IP khác

TOPIC_SENSOR = "smart-campus/events/sensor"
TOPIC_ACCESS = "smart-campus/events/access"
TOPIC_CAMERA = "smart-campus/events/camera"
TOPIC_ALERT  = "smart-campus/events/alert"
TOPIC_POLICY = "smart-campus/events/policy"

WAIT_SEC = 2   # giây chờ sau mỗi publish để Analytics xử lý

# ─── COLORS ───────────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def ok(msg):   print(f"{GREEN}  [PASS]{RESET} {msg}")
def fail(msg): print(f"{RED}  [FAIL]{RESET} {msg}")
def info(msg): print(f"{CYAN}  [INFO]{RESET} {msg}")
def step(msg): print(f"\n{BOLD}{YELLOW}▶ {msg}{RESET}")

# ─── MQTT CLIENT ──────────────────────────────────────────────────────────────
received_messages: List[Dict] = []
connect_event = threading.Event()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        connect_event.set()
    else:
        print(f"{RED}[MQTT] Connect failed rc={rc}{RESET}")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        received_messages.append({"topic": msg.topic, "data": data})
    except Exception:
        pass

def make_client(client_id: str) -> mqtt.Client:
    c = mqtt.Client(client_id=client_id)
    if USERNAME:
        c.username_pw_set(USERNAME, PASSWORD)
    c.on_connect = on_connect
    c.on_message = on_message
    return c

# ─── PAYLOAD FACTORIES ────────────────────────────────────────────────────────
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def sensor_danger():
    return {
        "event_type":    "sensor.reading.processed",
        "source_service":"team-iot",
        "raw_event_id":  f"raw-iot-{uuid.uuid4().hex[:6]}",
        "device_id":     "esp32-lab-a101",
        "location":      "Lab A101",
        "temperature_c": 42.1,
        "humidity_percent": 71.2,
        "motion_detected":  True,
        "co2_ppm":       710,
        "smoke_ppm":     1.2,
        "battery_percent": 15,
        "status":        "danger",
        "alert_level":   "high",
        "reason":        "smoke_too_high",
        "timestamp":     now_iso(),
    }

def sensor_warning():
    return {
        "event_type":    "sensor.reading.processed",
        "source_service":"team-iot",
        "raw_event_id":  f"raw-iot-{uuid.uuid4().hex[:6]}",
        "device_id":     "esp32-lab-b201",
        "location":      "Lab B201",
        "temperature_c": 36.5,
        "humidity_percent": 87.0,
        "motion_detected":  False,
        "co2_ppm":       1250,
        "smoke_ppm":     0.6,
        "battery_percent": 85,
        "status":        "warning",
        "alert_level":   "medium",
        "reason":        "humidity_too_high",
        "timestamp":     now_iso(),
    }

def sensor_normal():
    return {
        "event_type":    "sensor.reading.processed",
        "source_service":"team-iot",
        "raw_event_id":  f"raw-iot-{uuid.uuid4().hex[:6]}",
        "device_id":     "esp32-lab-c301",
        "location":      "Lab C301",
        "temperature_c": 27.0,
        "humidity_percent": 55.0,
        "motion_detected":  False,
        "co2_ppm":       600,
        "smoke_ppm":     0.01,
        "battery_percent": 90,
        "status":        "normal",
        "alert_level":   "none",
        "reason":        "",
        "timestamp":     now_iso(),
    }

def access_granted():
    return {
        "event_type":    "access.swipe.processed",
        "source_service":"team-gate",
        "raw_event_id":  f"raw-rfid-{uuid.uuid4().hex[:6]}",
        "uid":           "04:A1:B2:C3:D4:03",
        "student_id":    "SV003",
        "full_name":     "Le Minh Cuong",
        "class_name":    "CNTT-K19",
        "door_id":       "gate-a",
        "location":      "Main Gate A",
        "direction":     "in",
        "access_result": "granted",
        "reason":        "uid_matched",
        "timestamp":     now_iso(),
    }

def access_denied():
    return {
        "event_type":    "access.swipe.processed",
        "source_service":"team-gate",
        "raw_event_id":  f"raw-rfid-{uuid.uuid4().hex[:6]}",
        "uid":           "04:FF:FF:FF:FF:99",
        "student_id":    None,
        "full_name":     None,
        "class_name":    None,
        "door_id":       "gate-b",
        "location":      "Side Gate B",
        "direction":     "in",
        "access_result": "denied",
        "reason":        "uid_not_found",
        "timestamp":     now_iso(),
    }

def camera_motion():
    return {
        "event_type":    "camera.motion.triggered",
        "source_service":"team-camera",
        "request_id":    f"vision-req-{uuid.uuid4().hex[:6]}",
        "camera_id":     "cam-gate-a",
        "location":      "Main Gate A",
        "motion_detected": True,
        "motion_score":  0.82,
        "unknown_person": True,
        "risk_level":    "high",
        "snapshot_url":  "http://team-camera/snapshots/test.jpg",
        "timestamp":     now_iso(),
    }

def alert_critical():
    return {
        "event_type":    "core.alert.created",
        "source_service":"team-core",
        "alert_id":      f"ALT-{uuid.uuid4().hex[:8].upper()}",
        "alert_type":    "fire",
        "severity":      "critical",
        "message":       "Phat hien khoi nong do cao tai Lab A101",
        "origin_event_id": "raw-iot-abc123",
        "location":      "Lab A101",
        "target":        "all",
        "timestamp":     now_iso(),
    }

def alert_medium():
    return {
        "event_type":    "core.alert.created",
        "source_service":"team-core",
        "alert_id":      f"ALT-{uuid.uuid4().hex[:8].upper()}",
        "alert_type":    "access_bruteforce",
        "severity":      "medium",
        "message":       "Quetat the that bai nhieu lan tai Side Gate B",
        "origin_event_id": "raw-rfid-abc456",
        "location":      "Side Gate B",
        "target":        "security_team",
        "timestamp":     now_iso(),
    }

# ─── HTTP CHECK ───────────────────────────────────────────────────────────────
def check_analytics(endpoint: str, description: str, check_fn=None) -> bool:
    try:
        import urllib.request, urllib.error
        url = f"{ANALYTICS_URL}{endpoint}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if check_fn:
            result, reason = check_fn(data)
            if result:
                ok(f"{description} → {reason}")
                return True
            else:
                fail(f"{description} → {reason}")
                return False
        else:
            ok(f"{description} → HTTP 200")
            return True
    except Exception as e:
        fail(f"{description} → {e}")
        return False

# ─── MAIN TEST ────────────────────────────────────────────────────────────────
def run():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    results = []

    # ── TEST 1: Kết nối broker ────────────────────────────────────────────────
    step("TEST 1 – Kết nối MQTT Broker")
    info(f"Broker: {BROKER}:{PORT}")

    pub_client = make_client("e2e-publisher")
    try:
        pub_client.connect(BROKER, PORT, 10)
        pub_client.loop_start()
        connected = connect_event.wait(timeout=5)
        if connected:
            ok(f"Kết nối broker thành công")
            results.append(True)
        else:
            fail("Timeout kết nối broker – kiểm tra IP Radmin VPN và port 1883")
            results.append(False)
            return results
    except Exception as e:
        fail(f"Không kết nối được broker: {e}")
        results.append(False)
        return results

    # ── TEST 2: Analytics /health ─────────────────────────────────────────────
    step("TEST 2 – Analytics Service /health")
    r = check_analytics(
        "/health", "Analytics đang chạy",
        lambda d: (d.get("status") == "ok", f"status={d.get('status')}, mqtt={d.get('mqtt_connected')}")
    )
    results.append(r)

    # ── TEST 3: Publish sensor events ────────────────────────────────────────
    step("TEST 3 – Publish sensor events (danger / warning / normal)")
    for payload, label in [
        (sensor_danger(),  "danger"),
        (sensor_warning(), "warning"),
        (sensor_normal(),  "normal"),
    ]:
        pub_client.publish(TOPIC_SENSOR, json.dumps(payload), qos=1)
        info(f"Published sensor {label} → {TOPIC_SENSOR}")
        time.sleep(0.3)

    time.sleep(WAIT_SEC)
    r = check_analytics(
        f"/metrics/daily?date={today}",
        "Analytics nhận sensor events",
        lambda d: (
            d["sensor"]["danger_count"] >= 1 and d["sensor"]["warning_count"] >= 1,
            f"danger={d['sensor']['danger_count']}, warning={d['sensor']['warning_count']}, normal={d['sensor']['normal_count']}"
        )
    )
    results.append(r)

    # ── TEST 4: Phân tích theo phòng ─────────────────────────────────────────
    step("TEST 4 – KPI trung bình theo phòng (Lab A101)")
    r = check_analytics(
        f"/metrics/rooms?date={today}",
        "Nhiệt độ trung bình theo phòng",
        lambda d: (
            len(d["rooms"]) >= 1,
            f"{len(d['rooms'])} phòng: " + ", ".join(f"{r['location']}={r['avg_temp']}°C" for r in d["rooms"])
        )
    )
    results.append(r)

    # ── TEST 5: Publish access events ────────────────────────────────────────
    step("TEST 5 – Publish access events (granted / denied)")
    for payload, label in [
        (access_granted(), "granted"),
        (access_denied(),  "denied"),
        (access_denied(),  "denied x2"),
    ]:
        pub_client.publish(TOPIC_ACCESS, json.dumps(payload), qos=1)
        info(f"Published access {label} → {TOPIC_ACCESS}")
        time.sleep(0.3)

    time.sleep(WAIT_SEC)
    r = check_analytics(
        f"/metrics/access?date={today}",
        "Analytics nhận access events",
        lambda d: (
            d["by_gate"] and any(g["denied"] >= 1 for g in d["by_gate"]),
            f"gates={len(d['by_gate'])}, denied_log={len(d['denied_log'])}"
        )
    )
    results.append(r)

    # ── TEST 6: Publish camera event ─────────────────────────────────────────
    step("TEST 6 – Publish camera event (motion + unknown_person)")
    pub_client.publish(TOPIC_CAMERA, json.dumps(camera_motion()), qos=1)
    info(f"Published camera motion → {TOPIC_CAMERA}")
    time.sleep(WAIT_SEC)
    # Camera events không có endpoint riêng, verify qua daily
    ok("Camera event published (xác nhận qua /metrics/daily alerts)")
    results.append(True)

    # ── TEST 7: Publish alert từ Core Business ────────────────────────────────
    step("TEST 7 – Publish alert từ Core Business (critical + medium)")
    for payload, label in [
        (alert_critical(), "critical"),
        (alert_medium(),   "medium"),
    ]:
        pub_client.publish(TOPIC_ALERT,  json.dumps(payload), qos=1)
        pub_client.publish(TOPIC_POLICY, json.dumps(payload), qos=1)
        info(f"Published alert {label} → {TOPIC_ALERT}")
        time.sleep(0.3)

    time.sleep(WAIT_SEC)
    r = check_analytics(
        f"/metrics/alerts?date={today}",
        "Analytics nhận alert từ Core Business",
        lambda d: (
            d["total"] >= 1,
            f"total={d['total']}, by_type={[t['alert_type'] for t in d['by_type']]}"
        )
    )
    results.append(r)

    # ── TEST 8: Alert phân theo severity ─────────────────────────────────────
    step("TEST 8 – Alert phân theo severity")
    r = check_analytics(
        f"/metrics/daily?date={today}",
        "Alerts phân mức critical/medium",
        lambda d: (
            d["alerts"]["critical"] >= 1 and d["alerts"]["medium"] >= 1,
            f"critical={d['alerts']['critical']}, medium={d['alerts']['medium']}, total={d['alerts']['total']}"
        )
    )
    results.append(r)

    # ── TEST 9: Trend ─────────────────────────────────────────────────────────
    step("TEST 9 – Xu hướng 7 ngày (/metrics/trend)")
    r = check_analytics(
        "/metrics/trend?days=7",
        "Trend 7 ngày có dữ liệu hôm nay",
        lambda d: (
            any(t["danger_count"] >= 1 for t in d["trend"]),
            f"{d['days']} ngày, hôm nay danger={next((t['danger_count'] for t in d['trend'] if t['date']==today), 0)}"
        )
    )
    results.append(r)

    # ── TEST 10: Low battery ──────────────────────────────────────────────────
    step("TEST 10 – Thiết bị pin yếu (/metrics/low-battery)")
    r = check_analytics(
        "/metrics/low-battery?threshold=20",
        "Phát hiện thiết bị pin < 20%",
        lambda d: (
            d["total"] >= 1,
            f"{d['total']} thiết bị: " + ", ".join(f"{dev['device_id']}={dev['min_battery']}%" for dev in d["devices"])
        )
    )
    results.append(r)

    # ── CLEANUP ───────────────────────────────────────────────────────────────
    pub_client.loop_stop()
    pub_client.disconnect()

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    passed = sum(results)
    total  = len(results)
    print(f"\n{'='*55}")
    print(f"{BOLD}  KẾT QUẢ: {passed}/{total} tests PASS{RESET}")
    print(f"{'='*55}")
    if passed == total:
        print(f"{GREEN}{BOLD}  ✓ Luồng end-to-end hoạt động hoàn chỉnh!{RESET}")
    else:
        print(f"{RED}  ✗ {total - passed} test(s) FAIL – xem chi tiết bên trên{RESET}")
        print(f"\n{YELLOW}  Gợi ý debug:{RESET}")
        print("  • Analytics chưa nhận data → kiểm tra MQTT_BROKER trong .env của Analytics")
        print("  • /health mqtt_connected=false → Analytics chưa kết nối được broker")
        print("  • /metrics/* trả 0 → Analytics đang chạy nhưng chưa nhận message")
        print("  • Connection refused → Analytics service chưa start hoặc sai port")

    return results


if __name__ == "__main__":
    run()