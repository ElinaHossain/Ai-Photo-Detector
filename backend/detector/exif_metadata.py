from dataclasses import dataclass
from typing import Any
import io

from PIL import Image, ExifTags


TEST_NAME = "EXIF Metadata Analysis"


@dataclass(frozen=True)
class ExifMetadataAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | str | bool | None]

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "exif_present": self.metrics.get("exif_present", False),
                "software_tag": self.metrics.get("software_tag"),
                "camera_model": self.metrics.get("camera_model"),
                "explanation": self.explanation,
                "metrics": self.metrics,
            },
        }


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _explanation(verdict: str, exif_present: bool, software_tag: str | None) -> str:
    if verdict == "suspicious":
        return (
            "Metadata contains software or editing indicators that may suggest the image "
            "was generated, exported, or modified by non-camera tools."
        )
    if verdict == "inconclusive":
        if not exif_present:
            return (
                "No EXIF metadata was found. This can happen for screenshots, downloads, "
                "or edited images, so the signal is inconclusive."
            )
        return (
            "Metadata is present but does not provide strong evidence for or against "
            "AI generation."
        )
    if software_tag:
        return (
            "Metadata is present and does not show strong suspicious indicators, though "
            "software export metadata may still reflect ordinary processing."
        )
    return (
        "Metadata appears broadly consistent with a normal image file and does not show "
        "strong suspicious indicators."
    )


def analyze_exif_metadata(*, image_bytes: bytes, request_id: str) -> ExifMetadataAnalysis:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            exif = image.getexif()
            image_info = image.info
    except OSError as exc:
        raise ValueError("Unable to decode uploaded image bytes.") from exc

    exif_present = bool(exif and len(exif) > 0)

    exif_lookup: dict[str, Any] = {}
    if exif_present:
        for tag_id, value in exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, str(tag_id))
            exif_lookup[str(tag_name)] = value

    software_tag = exif_lookup.get("Software") or image_info.get("software")
    camera_model = exif_lookup.get("Model")
    make = exif_lookup.get("Make")
    datetime_original = exif_lookup.get("DateTimeOriginal")
    artist = exif_lookup.get("Artist")

    software_text = str(software_tag).lower() if software_tag is not None else ""
    suspicious_software_keywords = (
        "photoshop",
        "gimp",
        "canva",
        "stable diffusion",
        "midjourney",
        "dall-e",
        "openai",
        "comfyui",
        "automatic1111",
        "invokeai",
        "firefly",
    )

    suspicious_software = any(keyword in software_text for keyword in suspicious_software_keywords)
    missing_camera_info = not camera_model and not make

    if suspicious_software:
        raw_score = 0.82
        verdict = "suspicious"
        confidence = 0.88
    elif not exif_present:
        raw_score = 0.38
        verdict = "inconclusive"
        confidence = 0.68
    elif missing_camera_info and software_tag:
        raw_score = 0.42
        verdict = "inconclusive"
        confidence = 0.72
    else:
        raw_score = 0.08
        verdict = "clean"
        confidence = 0.78 if exif_present else 0.6

    metrics: dict[str, float | str | bool | None] = {
        "exif_present": exif_present,
        "software_tag": str(software_tag) if software_tag is not None else None,
        "camera_model": str(camera_model) if camera_model is not None else None,
        "camera_make": str(make) if make is not None else None,
        "datetime_original": str(datetime_original) if datetime_original is not None else None,
        "artist": str(artist) if artist is not None else None,
        "suspicious_software_detected": suspicious_software,
        "missing_camera_info": missing_camera_info,
        "request_id": request_id,
    }

    return ExifMetadataAnalysis(
        score=round(_clamp(raw_score, 0.0, 1.0), 4),
        confidence=round(_clamp(confidence, 0.0, 1.0), 4),
        verdict=verdict,
        explanation=_explanation(verdict, exif_present, str(software_tag) if software_tag is not None else None),
        metrics=metrics,
    )
