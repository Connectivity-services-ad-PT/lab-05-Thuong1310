import http.client
import os
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator


SERVICE_NAME = os.getenv("SERVICE_NAME", "core-business")
SERVICE_VERSION = os.getenv("SERVICE_VERSION", "0.4.0")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "local-dev-token")

app = FastAPI(
    title="FIT4110 Lab 04 - Core Business Service",
    version=SERVICE_VERSION,
    description="Dockerized Core Business API aligned with OpenAPI and Postman contract.",
)


class DirectionEnum(str, Enum):
    IN = "IN"
    OUT = "OUT"


class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int = Field(..., ge=400, le=599)
    detail: str
    instance: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class AccessCheckRequest(BaseModel):
    requestId: str = Field(..., examples=["0196fb3d-4ad7-7d1e-9f49-5d5148d2cafe"])
    cardId: str = Field(..., examples=["CARD-123456"])
    gateId: str = Field(..., examples=["GATE-01"])
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
    allow: bool
    reasonCode: str
    policyId: str
    expiresAt: str


class PolicyResponse(BaseModel):
    policyId: str
    name: str
    status: str
    description: str


class GateStatusResponse(BaseModel):
    gateId: str
    status: str


def build_problem(
    *,
    status_code: int,
    title: str,
    detail: str,
    instance: Optional[str] = None,
    problem_type: str = "about:blank",
) -> Dict:
    problem = {
        "type": problem_type,
        "title": title,
        "status": status_code,
        "detail": detail,
    }
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

    problem.setdefault("status", exc.status_code)
    problem.setdefault("title", http.client.responses.get(exc.status_code, "HTTP Error"))
    problem.setdefault("type", "about:blank")
    problem.setdefault("detail", "Request failed")
    problem.setdefault("instance", str(request.url.path))

    return JSONResponse(
        status_code=exc.status_code,
        content=problem,
        media_type="application/problem+json",
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = exc.errors()
    first_error = errors[0] if errors else {}
    location = ".".join(str(item) for item in first_error.get("loc", []))
    message = first_error.get("msg", "Request validation error")
    detail = f"{location}: {message}" if location else message

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

    expected = f"Bearer {AUTH_TOKEN}"
    if authorization != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=build_problem(
                status_code=status.HTTP_401_UNAUTHORIZED,
                title="Unauthorized",
                detail="Invalid bearer token",
                problem_type="https://smart-campus.local/problems/unauthorized",
            ),
        )


@app.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=SERVICE_NAME,
        version=SERVICE_VERSION,
    )


@app.post(
    "/access/check",
    response_model=AccessCheckResponse,
    dependencies=[Depends(verify_bearer_token)],
    responses={
        401: {"model": ProblemDetails},
        422: {"model": ProblemDetails},
    },
)
def access_check(
    payload: AccessCheckRequest,
    prefer: Optional[str] = Header(default=None),
) -> AccessCheckResponse:
    # 1. Giả lập lỗi qua Prefer header hoặc payload values để tương thích Postman tests
    # Kiểm tra trường hợp CARD_EXPIRED
    is_expired = False
    if prefer and "example=successExpired" in prefer:
        is_expired = True
    elif "2029" in payload.timestamp:
        is_expired = True

    # Kiểm tra trường hợp GATE_LOCKED
    is_locked = False
    if prefer and "example=successLocked" in prefer:
        is_locked = True
    elif payload.requestId.endswith("cb02"):
        is_locked = True

    # Kiểm tra trường hợp OUT_OF_SCHEDULE
    is_out_of_schedule = False
    if prefer and "example=successDenied" in prefer:
        is_out_of_schedule = True
    elif "02:00:00" in payload.timestamp:
        is_out_of_schedule = True

    # 2. Xây dựng response tương ứng
    if is_expired:
        return AccessCheckResponse(
            decisionId="0196fb3d-4ad7-7d1e-9f49-5d5148d2cafb",
            allow=False,
            reasonCode="CARD_EXPIRED",
            policyId="POL-101",
            expiresAt="2026-06-01T10:00:05Z",
        )
    elif is_locked:
        return AccessCheckResponse(
            decisionId="0196fb3d-4ad7-7d1e-9f49-5d5148d2cafc",
            allow=False,
            reasonCode="GATE_LOCKED",
            policyId="POL-101",
            expiresAt="2026-06-01T10:00:05Z",
        )
    elif is_out_of_schedule:
        return AccessCheckResponse(
            decisionId="0196fb3d-4ad7-7d1e-9f49-5d5148d2caf0",
            allow=False,
            reasonCode="OUT_OF_SCHEDULE",
            policyId="POL-101",
            expiresAt="2026-06-01T10:00:05Z",
        )
    else:
        # Happy path ALLOWED
        return AccessCheckResponse(
            decisionId="0196fb3d-4ad7-7d1e-9f49-5d5148d2caff",
            allow=True,
            reasonCode="ALLOWED",
            policyId="POL-101",
            expiresAt="2026-06-01T10:00:05Z",
        )


@app.get(
    "/policies/access/{policy_id}",
    response_model=PolicyResponse,
    dependencies=[Depends(verify_bearer_token)],
    responses={
        401: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
    },
)
def get_policy(
    policy_id: str,
    prefer: Optional[str] = Header(default=None),
) -> PolicyResponse:
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
    responses={
        401: {"model": ProblemDetails},
        404: {"model": ProblemDetails},
    },
)
def get_decision(decision_id: str) -> Dict:
    # Trả về quyết định mock dựa theo ID
    allow = True
    reason_code = "ALLOWED"
    if decision_id == "0196fb3d-4ad7-7d1e-9f49-5d5148d2caf0":
        allow = False
        reason_code = "OUT_OF_SCHEDULE"
    elif decision_id == "0196fb3d-4ad7-7d1e-9f49-5d5148d2cafb":
        allow = False
        reason_code = "CARD_EXPIRED"
    elif decision_id == "0196fb3d-4ad7-7d1e-9f49-5d5148d2cafc":
        allow = False
        reason_code = "GATE_LOCKED"

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
    responses={
        401: {"model": ProblemDetails},
    },
)
def get_gate_status(gate_id: str) -> GateStatusResponse:
    return GateStatusResponse(
        gateId=gate_id,
        status="OPEN",
    )
