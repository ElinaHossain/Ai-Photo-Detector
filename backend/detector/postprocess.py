from dataclasses import dataclass

from backend.detector.predict import PredictionOutput


@dataclass(frozen=True)
class PostprocessOutput:
    isAIGenerated: bool
    confidence: float
    indicators: list[dict[str, float | str]]


def _status_for_value(value: float) -> str:
    if value >= 75:
        return "pass"
    if value >= 50:
        return "warning"
    return "fail"


def postprocess_prediction(*, prediction: PredictionOutput, threshold: float = 60.0) -> PostprocessOutput:
    confidence = round(float(prediction.ai_probability), 2)
    is_ai_generated = confidence >= threshold

    return PostprocessOutput(
        isAIGenerated=is_ai_generated,
        confidence=confidence,
        indicators=[],
    )
