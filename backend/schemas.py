from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

ACCEPTED_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
}
MAX_UPLOAD_SIZE_BYTES = 10 * 1024 * 1024


class IndicatorStatus(str, Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class Indicator(BaseModel):
    label: str
    value: float = Field(..., ge=0.0, le=100.0)
    status: IndicatorStatus
    explanation: str | None = None


class ELAHeatmap(BaseModel):
    url: str


class ELAMetadata(BaseModel):
    score: float = Field(..., ge=0.0, le=100.0)
    explanation: str
    metrics: dict[str, Any]
    heatmap: ELAHeatmap


class ForensicVerdict(str, Enum):
    CLEAN = "clean"
    SUSPICIOUS = "suspicious"
    INCONCLUSIVE = "inconclusive"


class ForensicTest(BaseModel):
    test_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    confidence: float = Field(..., ge=0.0, le=1.0)
    verdict: ForensicVerdict
    details: dict[str, Any]


class DetectionMetadata(BaseModel):
    requestId: str
    fileName: str
    fileSize: int = Field(..., ge=0)
    mimeType: str
    modelName: str | None = None
    usedFallback: bool | None = None
    deterministicSeed: int | None = None
    ela: ELAMetadata | None = None


class DetectionResponse(BaseModel):
    isAIGenerated: bool
    confidence: float = Field(..., ge=0.0, le=100.0)
    indicators: list[Indicator]
    forensic_tests: list[ForensicTest] = Field(default_factory=list)
    metadata: DetectionMetadata | None = None


class ErrorResponse(BaseModel):
    error_code: str
    message: str
    details: dict[str, Any] | None = None
