import base64
import io
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


TEST_NAME = "AI Frequency Fingerprint Analysis"
MAX_ANALYSIS_DIMENSION = 640


@dataclass(frozen=True)
class FrequencyArtifactMap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class FrequencyFingerprintAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | str]
    artifact_map: FrequencyArtifactMap

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "frequency_fingerprint_score": self.score,
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


def _fft_power(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = values.shape
    centered = values.astype(np.float64) - float(np.mean(values))
    window = np.outer(np.hanning(height), np.hanning(width))
    spectrum = np.fft.fftshift(np.fft.fft2(centered * window))
    power = np.log1p(np.abs(spectrum))

    y_coords, x_coords = np.indices(power.shape)
    center_y = (height - 1) / 2.0
    center_x = (width - 1) / 2.0
    radius = np.sqrt((x_coords - center_x) ** 2 + (y_coords - center_y) ** 2)
    radius = radius / max(float(np.max(radius)), 1.0)
    return power, radius


def _robust_z(value: float, values: np.ndarray) -> float:
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scale = max(mad * 1.4826, float(np.std(values)) * 0.35, 1e-6)
    return (value - median) / scale


def _frequency_features(values: np.ndarray) -> dict[str, float]:
    power, radius = _fft_power(values)
    valid = radius > 0.035
    high = radius > 0.42
    mid = (radius > 0.16) & (radius <= 0.42)
    total_energy = float(np.sum(power[valid])) + 1e-6
    high_frequency_ratio = float(np.sum(power[high]) / total_energy)
    mid_frequency_ratio = float(np.sum(power[mid]) / total_energy)

    bins = np.linspace(0.045, 0.95, 28)
    profile_values: list[float] = []
    profile_radii: list[float] = []
    for low, high_edge in zip(bins[:-1], bins[1:]):
        mask = (radius >= low) & (radius < high_edge)
        if np.any(mask):
            profile_values.append(float(np.mean(power[mask])))
            profile_radii.append((low + high_edge) / 2.0)

    if len(profile_values) >= 4:
        x_values = np.log(np.array(profile_radii, dtype=np.float64))
        y_values = np.log(np.maximum(np.array(profile_values, dtype=np.float64), 1e-6))
        slope = float(np.polyfit(x_values, y_values, 1)[0])
    else:
        slope = -1.8

    ring_values = power[(radius > 0.12) & (radius < 0.88)]
    peak_z = max(0.0, _robust_z(float(np.max(ring_values)) if ring_values.size else 0.0, ring_values))
    profile_array = np.array(profile_values, dtype=np.float64) if profile_values else np.array([0.0])
    radial_irregularity = float(np.std(profile_array) / (np.mean(profile_array) + 1e-6))

    return {
        "spectral_slope": slope,
        "high_frequency_ratio": high_frequency_ratio,
        "mid_frequency_ratio": mid_frequency_ratio,
        "periodic_peak_z": peak_z,
        "radial_irregularity": radial_irregularity,
    }


def _block_size(width: int, height: int) -> int:
    min_side = max(1, min(width, height))
    if min_side < 48:
        return max(8, min_side)
    return int(_clamp(round(min_side / 6), 32, 80))


def _block_frequency_map(luma: np.ndarray, block_size: int) -> np.ndarray:
    height, width = luma.shape
    stride = max(8, block_size // 2)
    rows = max(1, 1 + max(0, height - block_size) // stride)
    cols = max(1, 1 + max(0, width - block_size) // stride)
    scores = np.zeros((rows, cols), dtype=np.float64)

    for row in range(rows):
        for col in range(cols):
            top = min(row * stride, max(0, height - block_size))
            left = min(col * stride, max(0, width - block_size))
            patch = luma[top : min(top + block_size, height), left : min(left + block_size, width)]
            if patch.size < 16:
                continue
            features = _frequency_features(patch)
            peak_component = _clamp((features["periodic_peak_z"] - 4.0) / 14.0, 0.0, 1.0)
            slope_component = _clamp((abs(features["spectral_slope"] + 1.8) - 0.45) / 1.2, 0.0, 1.0)
            high_component = max(
                _clamp((0.16 - features["high_frequency_ratio"]) / 0.12, 0.0, 1.0),
                _clamp((features["high_frequency_ratio"] - 0.52) / 0.24, 0.0, 1.0),
            )
            scores[row, col] = _clamp(
                (peak_component * 0.42) + (slope_component * 0.34) + (high_component * 0.24),
                0.0,
                1.0,
            )
    return scores


def _build_artifact_map(original: Image.Image, block_map: np.ndarray, analysis_size: tuple[int, int]) -> FrequencyArtifactMap:
    width, height = analysis_size
    heat_values = (np.clip(block_map, 0.0, 1.0) * 255.0).astype(np.uint8)
    heat_image = Image.fromarray(heat_values, mode="L").resize((width, height), Image.Resampling.BILINEAR)
    heat_image = ImageEnhance.Contrast(heat_image).enhance(1.3)

    alpha = heat_image.point(lambda value: 0 if value < 30 else int(_clamp((value - 30) * 0.72, 0.0, 170.0)))
    colorized = ImageOps.colorize(heat_image, black="#101820", mid="#3dd6a7", white="#ff4f8b").convert("RGBA")
    colorized.putalpha(alpha)

    base = ImageOps.grayscale(original.resize((width, height), Image.Resampling.LANCZOS))
    base_rgb = ImageOps.colorize(base, black="#1d2530", white="#e7edf3")
    final_image = Image.alpha_composite(base_rgb.convert("RGBA"), colorized).convert("RGB")

    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return FrequencyArtifactMap(data_url=f"data:{media_type};base64,{encoded}", media_type=media_type)


def _verdict_for_metrics(*, raw_score: float, periodic_component: float, slope_component: float) -> str:
    if raw_score >= 0.7 and (periodic_component >= 0.45 or slope_component >= 0.55):
        return "suspicious"
    if raw_score >= 0.42 and (periodic_component >= 0.28 or slope_component >= 0.32):
        return "inconclusive"
    return "clean"


def _display_score(raw_score: float, verdict: str) -> float:
    if verdict == "suspicious":
        return round(_clamp(raw_score, 0.55, 1.0), 4)
    if verdict == "inconclusive":
        return round(_clamp(raw_score * 0.78, 0.28, 0.5), 4)
    return round(_clamp(raw_score * 0.45, 0.0, 0.24), 4)


def _explanation(verdict: str) -> str:
    if verdict == "suspicious":
        return (
            "Frequency analysis found generator-like spectral structure. "
            "This is supporting AI evidence, not proof on its own."
        )
    if verdict == "inconclusive":
        return (
            "Frequency analysis found mild spectral irregularity. "
            "The signal is not strong enough on its own."
        )
    return "No strong generator-like frequency fingerprint was found. AI generation is still possible."


def analyze_frequency_fingerprint(*, image_bytes: bytes, request_id: str) -> FrequencyFingerprintAnalysis:
    original = _open_rgb_image(image_bytes)
    analysis_image = _resize_for_analysis(original)
    luma = np.asarray(ImageOps.grayscale(analysis_image), dtype=np.float64)
    height, width = luma.shape

    features = _frequency_features(luma)
    block_size = _block_size(width, height)
    block_map = _block_frequency_map(luma, block_size)
    patch_variation = float(np.std(block_map)) if block_map.size else 0.0
    localized_peak = float(np.percentile(block_map, 95)) if block_map.size else 0.0

    periodic_component = _clamp((features["periodic_peak_z"] - 4.5) / 15.0, 0.0, 1.0)
    slope_component = _clamp((abs(features["spectral_slope"] + 1.8) - 0.42) / 1.25, 0.0, 1.0)
    high_component = max(
        _clamp((0.16 - features["high_frequency_ratio"]) / 0.12, 0.0, 1.0),
        _clamp((features["high_frequency_ratio"] - 0.52) / 0.24, 0.0, 1.0),
    )
    local_component = _clamp(localized_peak / 0.72, 0.0, 1.0)
    uniformity_component = _clamp((0.08 - patch_variation) / 0.08, 0.0, 1.0) * high_component

    raw_score = round(
        _clamp(
            (periodic_component * 0.3)
            + (slope_component * 0.26)
            + (high_component * 0.2)
            + (local_component * 0.16)
            + (uniformity_component * 0.08),
            0.0,
            1.0,
        ),
        4,
    )
    verdict = _verdict_for_metrics(
        raw_score=raw_score,
        periodic_component=periodic_component,
        slope_component=slope_component,
    )
    score = _display_score(raw_score, verdict)
    confidence = round(_clamp(0.54 + (score * 0.34), 0.0, 0.9), 4)
    artifact_map = _build_artifact_map(analysis_image, block_map, analysis_size=(width, height))

    metrics: dict[str, float | str] = {
        "frequency_fingerprint_score": score,
        "raw_frequency_fingerprint_score": raw_score,
        "spectral_slope": round(features["spectral_slope"], 4),
        "high_frequency_ratio": round(features["high_frequency_ratio"], 4),
        "periodic_peak_z": round(features["periodic_peak_z"], 4),
        "radial_irregularity": round(features["radial_irregularity"], 4),
        "localized_spectral_peak": round(localized_peak, 4),
        "spectral_patch_variation": round(patch_variation, 4),
        "request_id": request_id,
    }

    return FrequencyFingerprintAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(verdict),
        metrics=metrics,
        artifact_map=artifact_map,
    )
