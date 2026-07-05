# services/policy_engine.py  (phần xử lý kết quả AI Vision)
import logging
from datetime import datetime, time

logger = logging.getLogger(__name__)

# Giờ cho phép vào campus (ví dụ 6:00 - 22:00)
ALLOWED_HOURS = (time(6, 0), time(22, 0))


def is_outside_hours() -> bool:
    now = datetime.now().time()
    return not (ALLOWED_HOURS[0] <= now <= ALLOWED_HOURS[1])


def assess_camera_event(camera_event: dict, vision_result: dict) -> dict | None:
    """
    Áp policy lên kết quả AI Vision để quyết định có tạo alert không.
    Trả về alert dict hoặc None nếu bình thường.
    """
    unknown_person = vision_result.get("unknown_person", False)
    risk_level = vision_result.get("risk_level", "low")
    camera_id = camera_event.get("camera_id", "unknown")
    location = camera_event.get("location", "unknown")

    # Rule 1: Người lạ + ngoài giờ → critical
    if unknown_person and is_outside_hours():
        return _build_alert(
            alert_type="intrusion",
            severity="critical",
            message=f"Phát hiện người lạ ngoài giờ tại {location}",
            origin_event_id=camera_event.get("request_id"),
            target="security_team",
        )

    # Rule 2: Người lạ trong giờ + risk_level cao → high
    if unknown_person and risk_level in ("high", "warning"):
        return _build_alert(
            alert_type="suspicious_person",
            severity="high",
            message=f"Phát hiện người lạ đáng ngờ tại {location}",
            origin_event_id=camera_event.get("request_id"),
            target="security_team",
        )

    # Bình thường → không tạo alert
    logger.info(
        f"[Policy] Camera event bình thường | "
        f"camera={camera_id} risk={risk_level} unknown={unknown_person}"
    )
    return None


def _build_alert(
    alert_type: str,
    severity: str,
    message: str,
    origin_event_id: str,
    target: str,
) -> dict:
    import uuid
    return {
        "event_type": "core.alert.created",
        "source_service": "team-core",
        "alert_id": f"ALT-{uuid.uuid4().hex[:6].upper()}",
        "alert_type": alert_type,
        "severity": severity,
        "message": message,
        "origin_event_id": origin_event_id,
        "target": target,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }