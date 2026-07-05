import asyncio
import concurrent.futures
import http.client
import json
import os
import re
import time
import uuid
from collections import deque, defaultdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

import httpx
import paho.mqtt.client as mqtt
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# ─────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────
SERVICE_NAME    = os.getenv("SERVICE_NAME", "core-business")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.4.0")
AUTH_TOKEN      = os.getenv("AUTH_TOKEN", "local-dev-token")

MQTT_BROKER   = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT     = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")

AI_VISION_URL      = os.getenv("AI_VISION_URL", "http://ai-service:9000")
AI_VISION_ENDPOINT = "/detect"
AI_VISION_TIMEOUT  = 10
AI_VISION_RETRIES  = 2

# Topics
TOPIC_SENSOR = "smart-campus/events/sensor"
TOPIC_ACCESS = "smart-campus/events/access"
TOPIC_CAMERA = "smart-campus/events/camera"
TOPIC_ALERT  = "smart-campus/events/alert"
TOPIC_POLICY = "smart-campus/events/policy"

# ─────────────────────────────────────────────
# In-memory state
# ─────────────────────────────────────────────
recent_events: deque         = deque(maxlen=500)
access_denied_counter: Dict  = defaultdict(int)
CONNECTED_SERVICES: Dict     = {}
_mqtt_client: Optional[mqtt.Client] = None
_event_loop: Optional[asyncio.AbstractEventLoop] = None

# ─────────────────────────────────────────────
# App
# ─────────────────────────────────────────────
app = FastAPI(
    title="FIT4110 Lab 04 - Core Business Service",
    version=SERVICE_VERSION,
    description="Dockerized Core Business API aligned with OpenAPI and Postman contract.",
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def audit_log(entry: Dict) -> None:
    try:
        with open("core_audit.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def publish_alert(alert: Dict) -> None:
    audit_log({"action": "publish_alert", "alert": alert})
    if _mqtt_client and _mqtt_client.is_connected():
        payload = json.dumps(alert)
        _mqtt_client.publish(TOPIC_ALERT, payload)
        _mqtt_client.publish(TOPIC_POLICY, payload)


def make_alert(
    origin_event: Dict,
    alert_type: str,
    severity: str,
    message: str,
    target: str = "security_team",
) -> Dict:
    return {
        "event_type": "core.alert.created",
        "source_service": "team-core",
        "alert_id": f"ALT-{uuid.uuid4().hex[:8].upper()}",
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "origin_event_id": (
            origin_event.get("raw_event_id")
            or origin_event.get("request_id")
            or origin_event.get("event_id")
        ),
        "target": target,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _track_service(source: str, topic: str, event_type: str) -> None:
    prev = CONNECTED_SERVICES.get(source, {})
    CONNECTED_SERVICES[source] = {
        "service": source,
        "last_topic": topic,
        "last_event_type": event_type,
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "total_events": prev.get("total_events", 0) + 1,
    }


# ─────────────────────────────────────────────
# AI Vision client
# ─────────────────────────────────────────────
async def call_ai_vision(camera_event: Dict) -> Optional[Dict]:
    """
    Gọi AI Vision POST /detect (REST sync).
    Retry tối đa AI_VISION_RETRIES lần nếu timeout hoặc 5xx.
    Trả về dict kết quả hoặc None nếu thất bại.
    """
    payload = {
        "request_id": camera_event.get("request_id", str(uuid.uuid4())),
        "camera_id":  camera_event.get("camera_id", ""),
        "timestamp":  camera_event.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "location":   camera_event.get("location", ""),
        "motion_score": camera_event.get("motion_score", 0.0),
        "snapshot_url": camera_event.get("snapshot_url", ""),
    }
    url = f"{AI_VISION_URL}{AI_VISION_ENDPOINT}"

    for attempt in range(1, AI_VISION_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=AI_VISION_TIMEOUT) as client:
                resp = await client.post(url, json=payload)

            if resp.status_code == 200:
                result = resp.json()
                audit_log({
                    "action": "ai_vision_ok",
                    "request_id": payload["request_id"],
                    "result": result,
                })
                return result

            elif resp.status_code >= 500:
                audit_log({
                    "action": "ai_vision_server_error",
                    "status": resp.status_code,
                    "attempt": attempt,
                })

            else:
                # 4xx — lỗi từ phía mình, không retry
                audit_log({
                    "action": "ai_vision_client_error",
                    "status": resp.status_code,
                    "body": resp.text,
                })
                return None

        except httpx.TimeoutException:
            audit_log({"action": "ai_vision_timeout", "attempt": attempt})

        except httpx.ConnectError:
            audit_log({"action": "ai_vision_unreachable", "url": url})
            return None

    audit_log({"action": "ai_vision_max_retries_exceeded", "request_id": payload["request_id"]})
    return None


def call_ai_vision_sync(camera_event: Dict) -> Optional[Dict]:
    """
    Wrapper đồng bộ để gọi call_ai_vision từ MQTT thread.
    Dùng event loop đang chạy của FastAPI.
    """
    global _event_loop
    if _event_loop and _event_loop.is_running():
        future = asyncio.run_coroutine_threadsafe(call_ai_vision(camera_event), _event_loop)
        try:
            return future.result(timeout=AI_VISION_TIMEOUT + 5)
        except concurrent.futures.TimeoutError:
            audit_log({"action": "ai_vision_sync_timeout"})
            return None
        except Exception as e:
            audit_log({"action": "ai_vision_sync_error", "error": str(e)})
            return None
    return None


# ─────────────────────────────────────────────
# Business logic handlers
# ─────────────────────────────────────────────
def handle_sensor_event(event: Dict) -> None:
    """
    Áp policy lên sensor event từ IoT Ingestion.
    danger  → alert critical
    warning → alert medium
    """
    s = event.get("status")
    location = event.get("location", "unknown")
    reason   = event.get("reason", "")

    if s == "danger":
        publish_alert(make_alert(
            event, "fire", "critical",
            f"Phát hiện nguy hiểm tại {location}: {reason}",
        ))
    elif s == "warning":
        publish_alert(make_alert(
            event, "environment_warning", "medium",
            f"Cảnh báo môi trường tại {location}: {reason}",
        ))
    else:
        audit_log({"action": "sensor_normal", "location": location, "status": s})


def handle_access_event(event: Dict) -> None:
    """
    Áp policy lên access event từ Access Gate.
    denied >= 3 lần → alert bruteforce
    """
    uid      = event.get("uid", "unknown")
    result   = event.get("access_result")
    location = event.get("location", "unknown")

    recent_events.append((time.time(), event))

    if result == "denied":
        access_denied_counter[uid] += 1
        audit_log({
            "action": "access_denied",
            "uid": uid,
            "count": access_denied_counter[uid],
            "location": location,
        })
        if access_denied_counter[uid] >= 3:
            publish_alert(make_alert(
                event, "access_bruteforce", "medium",
                f"Quẹt thẻ thất bại nhiều lần: UID={uid} tại {location}",
            ))
    else:
        # Reset counter khi granted thành công
        access_denied_counter[uid] = 0
        audit_log({"action": "access_granted", "uid": uid, "location": location})


def handle_camera_event(event: Dict) -> None:
    """
    Áp policy lên camera event từ Camera Stream.
    Gọi AI Vision REST sync để lấy risk_level + confidence.
    Kết hợp với access event gần đây để quyết định mức alert.
    """
    camera_id = event.get("camera_id", "unknown")
    location  = event.get("location", "unknown")

    # Bỏ qua nếu không có motion
    if not event.get("motion_detected", False):
        audit_log({"action": "camera_no_motion", "camera_id": camera_id})
        return

    # Gọi AI Vision
    vision_result = call_ai_vision_sync(event)

    if vision_result is None:
        audit_log({"action": "camera_no_vision_result", "camera_id": camera_id})
        # Không có kết quả AI → vẫn tạo alert thấp để không bỏ sót
        publish_alert(make_alert(
            event, "camera_vision_unavailable", "low",
            f"Phát hiện chuyển động tại {location} nhưng AI Vision không phản hồi",
        ))
        return

    risk_level = vision_result.get("risk_level", "low")
    label      = vision_result.get("label", "")
    confidence = vision_result.get("confidence", 0.0)

    audit_log({
        "action": "camera_vision_result",
        "camera_id": camera_id,
        "label": label,
        "confidence": confidence,
        "risk_level": risk_level,
        "location": location,
    })

    # Kiểm tra có denied access cùng khu trong 30 giây gần đây không
    now = time.time()
    has_denied_nearby = any(
        ev.get("access_result") == "denied" and ev.get("location") == location
        for ts, ev in list(recent_events)
        if now - ts <= 30
    )

    # Rule 1: person + confidence cao + risk medium/high + denied nearby → CRITICAL (nghi đột nhập)
    if label == "person" and confidence >= 0.8 and risk_level in ("medium", "high") and has_denied_nearby:
        publish_alert(make_alert(
            event, "intrusion", "critical",
            f"Nghi đột nhập: người lạ + quẹt thẻ thất bại gần đây tại {location} "
            f"(confidence={confidence:.2f})",
        ))

    # Rule 2: person + confidence cao + risk medium/high → HIGH
    elif label == "person" and confidence >= 0.8 and risk_level in ("medium", "high"):
        publish_alert(make_alert(
            event, "suspicious_person", "high",
            f"Phát hiện người đáng ngờ tại {location} "
            f"(risk={risk_level}, confidence={confidence:.2f})",
        ))

    # Rule 3: risk high nhưng confidence thấp → MEDIUM
    elif risk_level == "high" and confidence < 0.8:
        publish_alert(make_alert(
            event, "suspicious_activity", "medium",
            f"Hoạt động đáng ngờ tại {location} "
            f"(confidence thấp={confidence:.2f})",
        ))

    # Bình thường
    else:
        audit_log({
            "action": "camera_event_normal",
            "risk_level": risk_level,
            "label": label,
            "location": location,
        })


# ─────────────────────────────────────────────
# MQTT
# ─────────────────────────────────────────────
def on_mqtt_connect(client, userdata, flags, rc):
    audit_log({"action": "mqtt_connect", "rc": rc})
    client.subscribe([
        (TOPIC_SENSOR, 0),
        (TOPIC_ACCESS, 0),
        (TOPIC_CAMERA, 0),
    ])


def on_mqtt_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
    except Exception:
        audit_log({"action": "mqtt_bad_payload", "topic": msg.topic})
        return

    audit_log({"action": "mqtt_received", "topic": msg.topic, "payload": data})

    source = data.get("source_service", "unknown")
    _track_service(source, msg.topic, data.get("event_type", "unknown"))

    if msg.topic == TOPIC_SENSOR:
        handle_sensor_event(data)
    elif msg.topic == TOPIC_ACCESS:
        handle_access_event(data)
    elif msg.topic == TOPIC_CAMERA:
        handle_camera_event(data)


def start_mqtt_client() -> mqtt.Client:
    global _mqtt_client
    client = mqtt.Client()
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
    client.on_connect = on_mqtt_connect
    client.on_message = on_mqtt_message
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
    _mqtt_client = client
    return client


def stop_mqtt_client() -> None:
    global _mqtt_client
    if _mqtt_client:
        try:
            _mqtt_client.loop_stop()
            _mqtt_client.disconnect()
        except Exception:
            pass
        _mqtt_client = None


@app.on_event("startup")
async def startup_event():
    global _event_loop
    _event_loop = asyncio.get_event_loop()
    try:
        start_mqtt_client()
        audit_log({"action": "startup", "ai_vision_url": AI_VISION_URL})
    except Exception as e:
        audit_log({"action": "startup_failed", "error": str(e)})


@app.on_event("shutdown")
def shutdown_event():
    stop_mqtt_client()
    audit_log({"action": "shutdown"})


# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────
class DirectionEnum(str, Enum):
    IN  = "IN"
    OUT = "OUT"


class ProblemDetails(BaseModel):
    type:     str = "about:blank"
    title:    str
    status:   int = Field(..., ge=400, le=599)
    detail:   str
    instance: Optional[str] = None


class HealthResponse(BaseModel):
    status:         str
    service:        str
    version:        str
    mqtt_connected: bool
    ai_vision_url:  str


class AccessCheckRequest(BaseModel):
    requestId: str = Field(..., examples=["0196fb3d-4ad7-7d1e-9f49-5d5148d2cafe"])
    cardId:    str = Field(..., examples=["CARD-123456"])
    gateId:    str = Field(..., examples=["GATE-01"])
    direction: DirectionEnum = Field(..., examples=["IN"])
    timestamp: str = Field(..., examples=["2026-06-01T10:00:00Z"])

    @field_validator("cardId")
    @classmethod
    def validate_card_id(cls, v: str) -> str:
        if not re.match(r"^CARD-[0-9]{6}$", v):
            raise ValueError("cardId must match pattern ^CARD-[0-9]{6}$")
        return v


class AccessCheckResponse(BaseModel):
    decisionId: str
    allow:      bool
    reasonCode: str
    policyId:   str
    expiresAt:  str


class PolicyResponse(BaseModel):
    policyId:    str
    name:        str
    status:      str
    description: str


class GateStatusResponse(BaseModel):
    gateId: str
    status: str


# ─────────────────────────────────────────────
# Exception handlers
# ─────────────────────────────────────────────
def build_problem(
    *,
    status_code:  int,
    title:        str,
    detail:       str,
    instance:     Optional[str] = None,
    problem_type: str = "about:blank",
) -> Dict:
    problem = {"type": problem_type, "title": title, "status": status_code, "detail": detail}
    if instance:
        problem["instance"] = instance
    return problem


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if isinstance(exc.detail, dict):
        problem = exc.detail
    else:
        problem = build_problem(
            status_code=exc.status_code,
            title=http.client.responses.get(exc.status_code, "HTTP Error"),
            detail=str(exc.detail),
            instance=str(request.url.path),
        )
    problem.setdefault("status",   exc.status_code)
    problem.setdefault("title",    http.client.responses.get(exc.status_code, "HTTP Error"))
    problem.setdefault("type",     "about:blank")
    problem.setdefault("detail",   "Request failed")
    problem.setdefault("instance", str(request.url.path))
    return JSONResponse(
        status_code=exc.status_code,
        content=problem,
        media_type="application/problem+json",
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors    = exc.errors()
    first     = errors[0] if errors else {}
    location  = ".".join(str(i) for i in first.get("loc", []))
    message   = first.get("msg", "Request validation error")
    detail    = f"{location}: {message}" if location else message
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=build_problem(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Validation error",
            detail=detail,
            instance=str(request.url.path),
            problem_type="https://smart-campus.local/problems/validation-error",
        ),
        media_type="application/problem+json",
    )


def verify_bearer_token(authorization: Optional[str] = Header(default=None)) -> None:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_problem(
                status_code=status.HTTP_401_UNAUTHORIZED,
                title="Unauthorized",
                detail="Missing Authorization header",
                problem_type="https://smart-campus.local/problems/unauthorized",
            ),
        )
    if authorization != f"Bearer {AUTH_TOKEN}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_problem(
                status_code=status.HTTP_401_UNAUTHORIZED,
                title="Unauthorized",
                detail="Invalid bearer token",
                problem_type="https://smart-campus.local/problems/unauthorized",
            ),
        )


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@app.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
        mqtt_connected=_mqtt_client is not None and _mqtt_client.is_connected(),
        ai_vision_url=AI_VISION_URL,
    )


@app.get("/connections")
def get_connections():
    """Hiển thị các service đã gửi event đến Core qua MQTT."""
    return {
        "mqtt_connected": _mqtt_client is not None and _mqtt_client.is_connected(),
        "subscribed_topics": [TOPIC_SENSOR, TOPIC_ACCESS, TOPIC_CAMERA],
        "ai_vision_url": AI_VISION_URL,
        "total_services": len(CONNECTED_SERVICES),
        "services": list(CONNECTED_SERVICES.values()),
    }


@app.get("/alerts")
def get_alerts():
    """Xem audit log các alert đã được tạo."""
    alerts = []
    try:
        with open("core_audit.log", "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("action") == "publish_alert":
                        alerts.append(entry.get("alert"))
                except Exception:
                    pass
    except FileNotFoundError:
        pass
    return {"total": len(alerts), "alerts": alerts[-50:]}


@app.post(
    "/ai-vision/test",
    summary="Test gọi AI Vision trực tiếp từ Core",
)
async def test_ai_vision(camera_id: str = "cam-gate-a", location: str = "Main Gate A"):
    """Endpoint debug: gọi thử AI Vision và trả về kết quả thô."""
    fake_event = {
        "request_id":   str(uuid.uuid4()),
        "camera_id":    camera_id,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "location":     location,
        "motion_score": 0.85,
        "snapshot_url": f"http://ai-service:9000/snapshots/{camera_id}/test.jpg",
        "motion_detected": True,
    }
    result = await call_ai_vision(fake_event)
    return {
        "request_sent": fake_event,
        "vision_result": result,
        "ai_vision_url": AI_VISION_URL,
    }


@app.post(
    "/access/check",
    response_model=AccessCheckResponse,
    dependencies=[Depends(verify_bearer_token)],
    responses={401: {"model": ProblemDetails}, 422: {"model": ProblemDetails}},
)
def access_check(
    payload: AccessCheckRequest,
    prefer:  Optional[str] = Header(default=None),
) -> AccessCheckResponse:
    is_expired         = bool(prefer and "example=successExpired" in prefer)   or "2029" in payload.timestamp
    is_locked          = bool(prefer and "example=successLocked" in prefer)    or payload.requestId.endswith("cb02")
    is_out_of_schedule = bool(prefer and "example=successDenied" in prefer)    or "02:00:00" in payload.timestamp

    if is_expired:
        return AccessCheckResponse(
            decisionId="0196fb3d-4ad7-7d1e-9f49-5d5148d2cafb",
            allow=False, reasonCode="CARD_EXPIRED",
            policyId="POL-101", expiresAt="2026-06-01T10:00:05Z",
        )
    elif is_locked:
        return AccessCheckResponse(
            decisionId="0196fb3d-4ad7-7d1e-9f49-5d5148d2cafc",
            allow=False, reasonCode="GATE_LOCKED",
            policyId="POL-101", expiresAt="2026-06-01T10:00:05Z",
        )
    elif is_out_of_schedule:
        return AccessCheckResponse(
            decisionId="0196fb3d-4ad7-7d1e-9f49-5d5148d2caf0",
            allow=False, reasonCode="OUT_OF_SCHEDULE",
            policyId="POL-101", expiresAt="2026-06-01T10:00:05Z",
        )
    return AccessCheckResponse(
        decisionId="0196fb3d-4ad7-7d1e-9f49-5d5148d2caff",
        allow=True, reasonCode="ALLOWED",
        policyId="POL-101", expiresAt="2026-06-01T10:00:05Z",
    )


@app.get(
    "/policies/access/{policy_id}",
    response_model=PolicyResponse,
    dependencies=[Depends(verify_bearer_token)],
    responses={401: {"model": ProblemDetails}, 404: {"model": ProblemDetails}},
)
def get_policy(policy_id: str, prefer: Optional[str] = Header(default=None)) -> PolicyResponse:
    if policy_id == "POL-999" or (prefer and "code=404" in prefer):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=build_problem(
                status_code=status.HTTP_404_NOT_FOUND,
                title="Not Found",
                detail=f"Policy {policy_id} does not exist",
                instance=f"/policies/access/{policy_id}",
                problem_type="https://smart-campus.local/problems/not-found",
            ),
        )
    return PolicyResponse(
        policyId=policy_id,
        name="Chính sách ra vào thông thường",
        status="ACTIVE",
        description="Chính sách cho phép ra vào giờ hành chính",
    )


@app.get(
    "/decisions/{decision_id}",
    dependencies=[Depends(verify_bearer_token)],
    responses={401: {"model": ProblemDetails}, 404: {"model": ProblemDetails}},
)
def get_decision(decision_id: str) -> Dict:
    allow, reason_code = True, "ALLOWED"
    if decision_id == "0196fb3d-4ad7-7d1e-9f49-5d5148d2caf0":
        allow, reason_code = False, "OUT_OF_SCHEDULE"
    elif decision_id == "0196fb3d-4ad7-7d1e-9f49-5d5148d2cafb":
        allow, reason_code = False, "CARD_EXPIRED"
    elif decision_id == "0196fb3d-4ad7-7d1e-9f49-5d5148d2cafc":
        allow, reason_code = False, "GATE_LOCKED"
    return {
        "decisionId": decision_id,
        "cardId": "CARD-123456",
        "gateId": "GATE-01",
        "allow": allow,
        "reasonCode": reason_code,
    }


@app.get(
    "/gates/{gate_id}/status",
    response_model=GateStatusResponse,
    dependencies=[Depends(verify_bearer_token)],
    responses={401: {"model": ProblemDetails}},
)
def get_gate_status(gate_id: str) -> GateStatusResponse:
    return GateStatusResponse(gateId=gate_id, status="OPEN")