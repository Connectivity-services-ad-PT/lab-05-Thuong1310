# services/ai_vision_client.py
import httpx
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Đặt trong .env: AI_VISION_URL=http://team-ai-vision:8000
# Tên service phải khớp với service name trong docker-compose.yml của nhóm AI Vision

AI_VISION_DETECT_ENDPOINT = "/api/v1/detect"
TIMEOUT_SECONDS = 10
MAX_RETRIES = 2


async def call_ai_vision_detect(
    request_id: str,
    camera_id: str,
    timestamp: str,
    location: str,
    motion_score: float,
    snapshot_url: str,
    ai_vision_base_url: str,
) -> Optional[dict]:
    """
    Gọi AI Vision POST /api/v1/detect (REST sync).
    Retry tối đa 2 lần nếu timeout hoặc 5xx.
    Trả về dict kết quả hoặc None nếu thất bại.
    """
    payload = {
        "request_id": request_id,
        "camera_id": camera_id,
        "timestamp": timestamp,
        "location": location,
        "motion_score": motion_score,
        "snapshot_url": snapshot_url,
    }

    url = f"{ai_vision_base_url}{AI_VISION_DETECT_ENDPOINT}"

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=payload)

            if response.status_code == 200:
                result = response.json()
                logger.info(
                    f"[AI Vision] OK | request_id={request_id} "
                    f"risk_level={result.get('risk_level')} "
                    f"unknown_person={result.get('unknown_person')}"
                )
                return result

            elif response.status_code >= 500:
                logger.warning(
                    f"[AI Vision] Server error {response.status_code} "
                    f"attempt={attempt}/{MAX_RETRIES} request_id={request_id}"
                )

            else:
                # 4xx - lỗi từ phía mình, không retry
                logger.error(
                    f"[AI Vision] Client error {response.status_code} "
                    f"body={response.text} request_id={request_id}"
                )
                return None

        except httpx.TimeoutException:
            logger.warning(
                f"[AI Vision] Timeout attempt={attempt}/{MAX_RETRIES} "
                f"request_id={request_id}"
            )
        except httpx.ConnectError:
            logger.error(
                f"[AI Vision] Cannot connect to {url} - "
                f"kiểm tra service name trong docker-compose"
            )
            return None

    logger.error(
        f"[AI Vision] Hết retry, bỏ qua request_id={request_id}"
    )
    return None