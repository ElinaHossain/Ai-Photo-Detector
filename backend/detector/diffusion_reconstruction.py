import base64
import io
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


TEST_NAME = "Diffusion Reconstruction Analysis"
MAX_ANALYSIS_DIMENSION = 640


@dataclass(frozen=True)
class DiffusionReconstructionMap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class DiffusionReconstructionAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | bool | str]
    artifact_map: DiffusionReconstructionMap

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "diffusion_reconstruction_score": self.score,
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


def _proxy_reconstruct(luma_image: Image.Image) -> Image.Image:
    width, height = luma_image.size
    low_size = (max(4, width // 3), max(4, height // 3))
    low_frequency = luma_image.resize(low_size, Image.Resampling.BICUBIC).resize((width, height), Image.Resampling.BICUBIC)
    denoised = luma_image.filter(ImageFilter.GaussianBlur(radius=1.1))
    return Image.blend(low_frequency, denoised, 0.62)


def _block_size(width: int, height: int) -> int:
    min_side = max(1, min(width, height))
    if min_side < 48:
        return max(8, min_side)
    return int(_clamp(round(min_side / 8), 24, 64))


def _block_means(values: np.ndarray, block_size: int) -> np.ndarray:
    height, width = values.shape
    rows = max(1, height // block_size)
    cols = max(1, width // block_size)
    cropped = values[: rows * block_size, : cols * block_size]
    if cropped.size == 0:
        return np.array([[float(np.mean(values))]], dtype=np.float64)
    blocks = cropped.reshape(rows, block_size, cols, block_size).transpose(0, 2, 1, 3)
    return blocks.mean(axis=(2, 3))


def _build_artifact_map(original: Image.Image, residual_map: np.ndarray, analysis_size: tuple[int, int]) -> DiffusionReconstructionMap:
    width, height = analysis_size
    floor = float(np.percentile(residual_map, 45)) if residual_map.size else 0.0
    ceiling = float(np.percentile(residual_map, 98)) if residual_map.size else floor + 1.0
    if ceiling <= floor:
        ceiling = floor + 1.0
    normalized = np.clip((residual_map - floor) / (ceiling - floor), 0.0, 1.0)
    heat_image = Image.fromarray((normalized * 255.0).astype(np.uint8), mode="L")
    heat_image = ImageEnhance.Contrast(heat_image).enhance(1.25)
    alpha = heat_image.point(lambda value: 0 if value < 24 else int(_clamp((value - 24) * 0.68, 0.0, 165.0)))
    colorized = ImageOps.colorize(heat_image, black="#101820", mid="#7fd1ff", white="#ffd27a").convert("RGBA")
    colorized.putalpha(alpha)

    base = ImageOps.grayscale(original.resize((width, height), Image.Resampling.LANCZOS))
    base_rgb = ImageOps.colorize(base, black="#1d2530", white="#e7edf3")
    final_image = Image.alpha_composite(base_rgb.convert("RGBA"), colorized).convert("RGB")

    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return DiffusionReconstructionMap(data_url=f"data:{media_type};base64,{encoded}", media_type=media_type)


def _verdict_for_metrics(*, raw_score: float, low_error_component: float, uniformity_component: float) -> str:
    if raw_score >= 0.74 and low_error_component >= 0.62 and uniformity_component >= 0.45:
        return "suspicious"
    if raw_score >= 0.46 and low_error_component >= 0.38:
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
            "The lightweight reconstruction proxy found unusually low and uniform residual error. "
            "This can support AI-generation suspicion, but it is not a full diffusion-model reconstruction."
        )
    if verdict == "inconclusive":
        return (
            "The lightweight reconstruction proxy found some low-error structure. "
            "The signal is not strong enough on its own."
        )
    return (
        "No strong low-error reconstruction pattern was found. "
        "This is a lightweight proxy, not a full diffusion-model reconstruction, and AI generation is still possible."
    )


def analyze_diffusion_reconstruction(*, image_bytes: bytes, request_id: str) -> DiffusionReconstructionAnalysis:
    original = _open_rgb_image(image_bytes)
    analysis_image = _resize_for_analysis(original)
    luma_image = ImageOps.grayscale(analysis_image)
    luma = np.asarray(luma_image, dtype=np.float64)
    reconstructed = np.asarray(_proxy_reconstruct(luma_image), dtype=np.float64)
    residual = np.abs(luma - reconstructed)

    block_size = _block_size(*luma_image.size)
    residual_blocks = _block_means(residual, block_size)
    texture_blocks = _block_means(np.abs(luma - np.asarray(luma_image.filter(ImageFilter.GaussianBlur(radius=1.2)), dtype=np.float64)), block_size)

    mean_error_pct = float(np.mean(residual) / 255.0 * 100.0)
    p95_error_pct = float(np.percentile(residual, 95) / 255.0 * 100.0)
    block_cv = float(np.std(residual_blocks) / (np.mean(residual_blocks) + 1e-6))
    mean_texture = float(np.mean(texture_blocks))
    texture_residual_gap = max(0.0, mean_texture - float(np.mean(residual_blocks)))

    low_error_component = _clamp((2.2 - mean_error_pct) / 2.2, 0.0, 1.0)
    uniformity_component = _clamp((0.48 - block_cv) / 0.48, 0.0, 1.0)
    texture_gap_component = _clamp(texture_residual_gap / 4.5, 0.0, 1.0)
    p95_component = _clamp((6.0 - p95_error_pct) / 6.0, 0.0, 1.0)

    raw_score = round(
        _clamp(
            (low_error_component * 0.34)
            + (uniformity_component * 0.26)
            + (texture_gap_component * 0.22)
            + (p95_component * 0.18),
            0.0,
            1.0,
        ),
        4,
    )
    verdict = _verdict_for_metrics(
        raw_score=raw_score,
        low_error_component=low_error_component,
        uniformity_component=uniformity_component,
    )
    score = _display_score(raw_score, verdict)
    confidence = round(_clamp(0.48 + (score * 0.3), 0.0, 0.78), 4)
    artifact_map = _build_artifact_map(analysis_image, residual, analysis_size=luma_image.size)

    metrics: dict[str, float | bool | str] = {
        "diffusion_reconstruction_score": score,
        "raw_diffusion_reconstruction_score": raw_score,
        "true_diffusion_model_available": False,
        "proxy_method": "multiscale denoise reconstruction",
        "mean_reconstruction_error": round(mean_error_pct, 4),
        "p95_reconstruction_error": round(p95_error_pct, 4),
        "residual_block_variation": round(block_cv, 4),
        "texture_residual_gap": round(texture_residual_gap, 4),
        "request_id": request_id,
    }

    return DiffusionReconstructionAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(verdict),
        metrics=metrics,
        artifact_map=artifact_map,
    )
