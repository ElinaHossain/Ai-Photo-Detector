import base64
import io
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


TEST_NAME = "Semantic Consistency Analysis"
MAX_ANALYSIS_DIMENSION = 640


@dataclass(frozen=True)
class SemanticArtifactMap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class SemanticConsistencyAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | bool | str]
    artifact_map: SemanticArtifactMap

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "semantic_consistency_score": self.score,
                "explanation": self.explanation,
                "metrics": self.metrics,
                "artifact_map": {
                    "url": self.artifact_map.data_url,
                    "mediaType": self.artifact_map.media_type,
                },
            },
        }


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _open_rgb_image(image_bytes: bytes) -> Image.Image:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            rgb_image = image.convert("RGB")
            rgb_image.load()
            return rgb_image
    except OSError as exc:
        raise ValueError("Unable to decode uploaded image bytes.") from exc


def _resize_for_analysis(image: Image.Image) -> Image.Image:
    width, height = image.size
    longest_side = max(width, height)
    if longest_side <= MAX_ANALYSIS_DIMENSION:
        return image.copy()

    scale = MAX_ANALYSIS_DIMENSION / longest_side
    target_size = (max(8, round(width * scale)), max(8, round(height * scale)))
    return image.resize(target_size, Image.Resampling.LANCZOS)


def _block_size(width: int, height: int) -> int:
    min_side = max(1, min(width, height))
    if min_side < 48:
        return max(8, min_side)
    return int(_clamp(round(min_side / 8), 24, 64))


def _block_scores(values: np.ndarray, block_size: int) -> np.ndarray:
    height, width = values.shape
    rows = max(1, height // block_size)
    cols = max(1, width // block_size)
    cropped = values[: rows * block_size, : cols * block_size]
    if cropped.size == 0:
        return np.array([[float(np.mean(values))]], dtype=np.float64)
    blocks = cropped.reshape(rows, block_size, cols, block_size).transpose(0, 2, 1, 3)
    return blocks.mean(axis=(2, 3))


def _semantic_proxy_map(luma: np.ndarray) -> tuple[np.ndarray, dict[str, float]]:
    smoothed_image = Image.fromarray(np.clip(luma, 0, 255).astype(np.uint8), mode="L").filter(
        ImageFilter.GaussianBlur(radius=0.9)
    )
    smoothed = np.asarray(smoothed_image, dtype=np.float64)
    if min(luma.shape) < 2:
        gradient = np.zeros_like(luma, dtype=np.float64)
        orientation = np.zeros_like(luma, dtype=np.float64)
    else:
        gradient_y, gradient_x = np.gradient(smoothed)
        gradient = np.sqrt((gradient_x * gradient_x) + (gradient_y * gradient_y))
        orientation = np.arctan2(gradient_y, gradient_x)

    edge_threshold = float(np.percentile(gradient, 82)) if gradient.size else 0.0
    edge_mask = gradient >= max(edge_threshold, 2.0)
    block_size = _block_size(luma.shape[1], luma.shape[0])
    edge_density = _block_scores(edge_mask.astype(np.float64), block_size)

    orientation_sin = _block_scores(np.sin(orientation) * edge_mask, block_size)
    orientation_cos = _block_scores(np.cos(orientation) * edge_mask, block_size)
    orientation_coherence = np.sqrt((orientation_sin * orientation_sin) + (orientation_cos * orientation_cos))
    orientation_disorder = np.clip(edge_density - orientation_coherence, 0.0, 1.0)

    local_contrast = _block_scores(np.abs(luma - smoothed), block_size)
    contrast_z = (local_contrast - float(np.median(local_contrast))) / (float(np.std(local_contrast)) + 1e-6)
    contrast_outliers = np.clip((contrast_z - 1.0) / 2.6, 0.0, 1.0)

    fragment_component = np.clip((edge_density - 0.24) / 0.32, 0.0, 1.0)
    block_map = np.clip((fragment_component * 0.42) + (orientation_disorder * 0.36) + (contrast_outliers * 0.22), 0.0, 1.0)

    metrics = {
        "edge_fragment_ratio": float(np.mean(fragment_component > 0.35)),
        "orientation_disorder": float(np.percentile(orientation_disorder, 90)) if orientation_disorder.size else 0.0,
        "local_contrast_outlier_ratio": float(np.mean(contrast_outliers > 0.45)),
        "semantic_proxy_peak": float(np.percentile(block_map, 95)) if block_map.size else 0.0,
        "semantic_proxy_variation": float(np.std(block_map)) if block_map.size else 0.0,
    }
    return block_map, metrics


def _build_artifact_map(original: Image.Image, block_map: np.ndarray, analysis_size: tuple[int, int]) -> SemanticArtifactMap:
    width, height = analysis_size
    heat_values = (np.clip(block_map, 0.0, 1.0) * 255.0).astype(np.uint8)
    heat_image = Image.fromarray(heat_values, mode="L").resize((width, height), Image.Resampling.BILINEAR)
    heat_image = ImageEnhance.Contrast(heat_image).enhance(1.25)

    alpha = heat_image.point(lambda value: 0 if value < 32 else int(_clamp((value - 32) * 0.64, 0.0, 160.0)))
    colorized = ImageOps.colorize(heat_image, black="#101820", mid="#b8e986", white="#ff4f8b").convert("RGBA")
    colorized.putalpha(alpha)

    base = ImageOps.grayscale(original.resize((width, height), Image.Resampling.LANCZOS))
    base_rgb = ImageOps.colorize(base, black="#1d2530", white="#e7edf3")
    final_image = Image.alpha_composite(base_rgb.convert("RGBA"), colorized).convert("RGB")

    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return SemanticArtifactMap(data_url=f"data:{media_type};base64,{encoded}", media_type=media_type)


def _verdict_for_metrics(*, raw_score: float, peak_score: float, fragment_ratio: float) -> str:
    if raw_score >= 0.72 and peak_score >= 0.58 and fragment_ratio >= 0.08:
        return "suspicious"
    if raw_score >= 0.45 and peak_score >= 0.35:
        return "inconclusive"
    return "clean"


def _display_score(raw_score: float, verdict: str) -> float:
    if verdict == "suspicious":
        return round(_clamp(raw_score, 0.55, 0.82), 4)
    if verdict == "inconclusive":
        return round(_clamp(raw_score * 0.76, 0.28, 0.48), 4)
    return round(_clamp(raw_score * 0.42, 0.0, 0.24), 4)


def _explanation(verdict: str) -> str:
    if verdict == "suspicious":
        return (
            "Rules-based semantic analysis found fragmented edges and local contrast patterns often worth reviewing. "
            "No VLM is configured, so treat this as supporting evidence only."
        )
    if verdict == "inconclusive":
        return (
            "Rules-based semantic analysis found mild structure worth reviewing. "
            "No VLM is configured, so this cannot assess anatomy, text, or reflections directly."
        )
    return (
        "No strong rules-based semantic anomaly was found. "
        "No VLM is configured, so AI generation is still possible."
    )


def analyze_semantic_consistency(*, image_bytes: bytes, request_id: str) -> SemanticConsistencyAnalysis:
    original = _open_rgb_image(image_bytes)
    analysis_image = _resize_for_analysis(original)
    luma = np.asarray(ImageOps.grayscale(analysis_image), dtype=np.float64)
    block_map, proxy_metrics = _semantic_proxy_map(luma)

    peak_score = proxy_metrics["semantic_proxy_peak"]
    fragment_ratio = proxy_metrics["edge_fragment_ratio"]
    raw_score = round(
        _clamp(
            (peak_score * 0.42)
            + (_clamp(proxy_metrics["orientation_disorder"] / 0.42, 0.0, 1.0) * 0.26)
            + (_clamp(fragment_ratio / 0.18, 0.0, 1.0) * 0.2)
            + (_clamp(proxy_metrics["local_contrast_outlier_ratio"] / 0.16, 0.0, 1.0) * 0.12),
            0.0,
            1.0,
        ),
        4,
    )
    verdict = _verdict_for_metrics(
        raw_score=raw_score,
        peak_score=peak_score,
        fragment_ratio=fragment_ratio,
    )
    score = _display_score(raw_score, verdict)
    confidence = round(_clamp(0.44 + (score * 0.28), 0.0, 0.76), 4)
    artifact_map = _build_artifact_map(analysis_image, block_map, analysis_size=analysis_image.size)

    metrics: dict[str, float | bool | str] = {
        "semantic_consistency_score": score,
        "raw_semantic_consistency_score": raw_score,
        "vlm_model_available": False,
        "proxy_method": "edge fragmentation and local contrast heuristics",
        "edge_fragment_ratio": round(proxy_metrics["edge_fragment_ratio"], 4),
        "orientation_disorder": round(proxy_metrics["orientation_disorder"], 4),
        "local_contrast_outlier_ratio": round(proxy_metrics["local_contrast_outlier_ratio"], 4),
        "semantic_proxy_peak": round(proxy_metrics["semantic_proxy_peak"], 4),
        "request_id": request_id,
    }

    return SemanticConsistencyAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(verdict),
        metrics=metrics,
        artifact_map=artifact_map,
    )
