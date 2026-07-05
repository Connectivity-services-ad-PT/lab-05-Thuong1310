# handlers/camera_event_handler.py
# Được gọi khi Core nhận MQTT event từ topic smart-campus/events/camera

import os
import logging
from services.ai_vision_client import call_ai_vision_detect
from services.policy_engine import assess_camera_event
from services.mqtt_publisher import publish_alert  # module MQTT của nhóm bạn

logger = logging.getLogger(__name__)

AI_VISION_URL = os.getenv("AI_VISION_URL", "http://team-ai-vision:8000")


async def handle_camera_event(camera_event: dict):
    """
    Luồng xử lý khi Core nhận event camera từ MQTT:
    1. Kiểm tra có đáng gọi AI Vision không
    2. Gọi AI Vision REST sync
    3. Áp policy → tạo alert nếu cần
    4. Publish alert sang Notification + Analytics
    """
    risk_level = camera_event.get("risk_level")
    motion_detected = camera_event.get("motion_detected", False)

    # Chỉ gọi AI Vision khi camera báo có motion
    # (Camera đã lọc sẵn, nhưng Core kiểm tra lại để chắc chắn)
    if not motion_detected:
        logger.debug("[Camera Handler] Không có motion, bỏ qua")
        return

    vision_result = await call_ai_vision_detect(
        request_id=camera_event.get("request_id", ""),
        camera_id=camera_event.get("camera_id", ""),
        timestamp=camera_event.get("timestamp", ""),
        location=camera_event.get("location", ""),
        motion_score=camera_event.get("motion_score", 0.0),
        snapshot_url=camera_event.get("snapshot_url", ""),
        ai_vision_base_url=AI_VISION_URL,
    )

    if vision_result is None:
        # AI Vision không phản hồi - ghi log, không crash
        logger.error(
            f"[Camera Handler] Không lấy được kết quả AI Vision "
            f"cho camera={camera_event.get('camera_id')}"
        )
        return

    # Áp policy → quyết định alert
    alert = assess_camera_event(camera_event, vision_result)

    if alert:
        logger.warning(f"[Camera Handler] Tạo alert: {alert}")
        await publish_alert(alert)   # gửi sang Notification + Analytics
    else:
        logger.info("[Camera Handler] Event bình thường, không cần alert")