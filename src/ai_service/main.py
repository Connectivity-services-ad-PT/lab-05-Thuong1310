from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

SERVICE_NAME = "ai-service"
SERVICE_VERSION = "0.5.0"

app = FastAPI(
    title="FIT4110 Lab 05 - AI Service",
    version=SERVICE_VERSION,
    description="Mock AI service used in Docker Compose stack.",
)


class Prediction(BaseModel):
    objects: List[str]
    confidence: List[float]


class DetectionResponse(BaseModel):
    detection_id: str
    camera_id: str
    label: str
    confidence: float
    risk_level: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": SERVICE_NAME, "version": SERVICE_VERSION}


@app.post("/predict", response_model=Prediction)
def predict() -> Prediction:
    return Prediction(objects=["person", "bicycle"], confidence=[0.98, 0.85])


@app.post("/detect", response_model=DetectionResponse)
def detect(payload: dict) -> DetectionResponse:
    # Trả về cấu trúc DetectionResponse chuẩn xác theo hợp đồng ai-vision.openapi.yaml
    camera_id = payload.get("camera_id", "CAM01")
    return DetectionResponse(
        detection_id="DET001",
        camera_id=camera_id,
        label="person",
        confidence=0.91,
        risk_level="medium"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)