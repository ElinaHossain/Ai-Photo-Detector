import base64
import io
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


TEST_NAME = "Noise Pattern / Texture Consistency Analysis"
MAX_ANALYSIS_DIMENSION = 768
SUSPICIOUS_REGION_LIMIT = 6
MIN_REGION_AREA_RATIO = 0.0025
MIN_REGION_AVERAGE_SCORE = 0.7


@dataclass(frozen=True)
class NoiseTextureMap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class NoiseTextureAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | str]
    artifact_map: NoiseTextureMap
    regions: list[dict[str, float]]

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "noise_variance_score": self.score,
                "explanation": self.explanation,
                "metrics": self.metrics,
                "artifact_map": {
                    "url": self.artifact_map.data_url,
                    "mediaType": self.artifact_map.media_type,
                },
                "regions": self.regions,
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
    target_size = (max(4, round(width * scale)), max(4, round(height * scale)))
    return image.resize(target_size, Image.Resampling.LANCZOS)


def _analysis_block_size(width: int, height: int) -> int:
    min_side = max(1, min(width, height))
    if min_side <= 1:
        return 1
    if min_side < 16:
        return min(min_side, max(2, min_side // 3))
    if min_side < 64:
        return max(4, min_side // 4)
    return int(_clamp(round(min_side / 12), 12, 32))


def _crop_to_block_grid(array: np.ndarray, block_size: int) -> np.ndarray:
    height, width = array.shape
    crop_height = max(block_size, (height // block_size) * block_size)
    crop_width = max(block_size, (width // block_size) * block_size)
    return array[: min(crop_height, height), : min(crop_width, width)]


def _block_view(array: np.ndarray, block_size: int) -> np.ndarray:
    cropped = _crop_to_block_grid(array, block_size)
    height, width = cropped.shape
    blocks_h = max(1, height // block_size)
    blocks_w = max(1, width // block_size)
    cropped = cropped[: blocks_h * block_size, : blocks_w * block_size]
    return cropped.reshape(blocks_h, block_size, blocks_w, block_size).transpose(0, 2, 1, 3)


def _block_mean(array: np.ndarray, block_size: int) -> np.ndarray:
    return _block_view(array, block_size).mean(axis=(2, 3))


def _block_std(array: np.ndarray, block_size: int) -> np.ndarray:
    return _block_view(array, block_size).std(axis=(2, 3))


def _robust_scale(values: np.ndarray) -> float:
    if values.size == 0:
        return 1.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return max(mad * 1.4826, float(np.std(values)) * 0.35, 1e-6)


def _robust_z(values: np.ndarray) -> np.ndarray:
    median = float(np.median(values))
    return (values - median) / _robust_scale(values)


def _smooth_luma(luma: np.ndarray, radius: float = 1.15) -> np.ndarray:
    image = Image.fromarray(np.clip(luma, 0, 255).astype(np.uint8), mode="L")
    blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(blurred, dtype=np.float64)


def _texture_expected_scores(noise: np.ndarray, texture: np.ndarray, brightness: np.ndarray) -> np.ndarray:
    flat_noise = noise.ravel()
    flat_texture = texture.ravel()
    flat_brightness = brightness.ravel()
    if flat_noise.size < 4 or float(np.ptp(flat_noise)) <= 1e-6:
        return np.zeros_like(noise, dtype=np.float64)

    texture_boundaries = np.quantile(flat_texture, [0.34, 0.67])
    brightness_boundaries = np.quantile(flat_brightness, [0.34, 0.67])
    texture_bins = np.digitize(flat_texture, texture_boundaries, right=False)
    brightness_bins = np.digitize(flat_brightness, brightness_boundaries, right=False)
    scores = np.zeros_like(flat_noise, dtype=np.float64)

    global_scale = _robust_scale(flat_noise)
    global_median = float(np.median(flat_noise))

    for texture_bin in range(3):
        texture_mask = texture_bins == texture_bin
        texture_noise = flat_noise[texture_mask]
        texture_expected = float(np.median(texture_noise)) if texture_noise.size >= 4 else global_median
        texture_scale = max(_robust_scale(texture_noise), global_scale * 0.65) if texture_noise.size >= 4 else global_scale

        for brightness_bin in range(3):
            mask = texture_mask & (brightness_bins == brightness_bin)
            bin_noise = flat_noise[mask]
            if bin_noise.size < 5:
                expected = texture_expected
                scale = texture_scale
            else:
                expected = float(np.median(bin_noise))
                scale = max(_robust_scale(bin_noise), texture_scale * 0.65, global_scale * 0.5)

            z_values = np.abs((flat_noise[mask] - expected) / scale)
            scores[mask] = np.clip((z_values - 1.25) / 3.1, 0.0, 1.0)

    return scores.reshape(noise.shape)


def _neighbor_transition_scores(noise: np.ndarray, texture: np.ndarray, brightness: np.ndarray) -> np.ndarray:
    rows, cols = noise.shape
    transition_map = np.zeros_like(noise, dtype=np.float64)
    counts = np.zeros_like(noise, dtype=np.float64)
    noise_scale = _robust_scale(noise.ravel())
    texture_scale = _robust_scale(texture.ravel())
    brightness_scale = _robust_scale(brightness.ravel())

    def _add_pair(first: tuple[int, int], second: tuple[int, int]) -> None:
        row_a, col_a = first
        row_b, col_b = second
        noise_delta = abs(float(noise[row_a, col_a] - noise[row_b, col_b]))
        texture_delta = abs(float(texture[row_a, col_a] - texture[row_b, col_b]))
        brightness_delta = abs(float(brightness[row_a, col_a] - brightness[row_b, col_b]))
        texture_weight = float(np.exp(-texture_delta / max(texture_scale * 1.8, 1.0)))
        brightness_weight = float(np.exp(-brightness_delta / max(brightness_scale * 1.6, 2.0)))
        similarity_weight = texture_weight * brightness_weight
        mismatch = _clamp(((noise_delta / noise_scale) - 1.2) / 2.5, 0.0, 1.0) * similarity_weight
        transition_map[row_a, col_a] += mismatch
        transition_map[row_b, col_b] += mismatch
        counts[row_a, col_a] += 1.0
        counts[row_b, col_b] += 1.0

    for row in range(rows):
        for col in range(cols):
            if col + 1 < cols:
                _add_pair((row, col), (row, col + 1))
            if row + 1 < rows:
                _add_pair((row, col), (row + 1, col))

    return transition_map / np.maximum(counts, 1.0)


def _regional_means(block_scores: np.ndarray, region_count: int = 4) -> np.ndarray:
    rows = np.array_split(block_scores, min(region_count, block_scores.shape[0]), axis=0)
    means: list[float] = []
    for row_slice in rows:
        cols = np.array_split(row_slice, min(region_count, block_scores.shape[1]), axis=1)
        for region in cols:
            means.append(float(np.mean(region)))
    return np.array(means, dtype=np.float64)


def _connected_regions(mask: np.ndarray, block_scores: np.ndarray) -> list[dict[str, float]]:
    visited = np.zeros(mask.shape, dtype=bool)
    regions: list[dict[str, float]] = []
    rows, cols = mask.shape

    for start_row in range(rows):
        for start_col in range(cols):
            if visited[start_row, start_col] or not mask[start_row, start_col]:
                continue

            queue: deque[tuple[int, int]] = deque([(start_row, start_col)])
            visited[start_row, start_col] = True
            cells: list[tuple[int, int]] = []

            while queue:
                row, col = queue.popleft()
                cells.append((row, col))
                for next_row, next_col in ((row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)):
                    if (
                        0 <= next_row < rows
                        and 0 <= next_col < cols
                        and not visited[next_row, next_col]
                        and mask[next_row, next_col]
                    ):
                        visited[next_row, next_col] = True
                        queue.append((next_row, next_col))

            cell_rows = [cell[0] for cell in cells]
            cell_cols = [cell[1] for cell in cells]
            min_row, max_row = min(cell_rows), max(cell_rows)
            min_col, max_col = min(cell_cols), max(cell_cols)
            region_score = float(np.mean([block_scores[row, col] for row, col in cells]))
            region_width = (max_col - min_col + 1) / cols
            region_height = (max_row - min_row + 1) / rows
            region_area = region_width * region_height
            if region_area < MIN_REGION_AREA_RATIO or region_score < MIN_REGION_AVERAGE_SCORE:
                continue

            regions.append(
                {
                    "x": round(min_col / cols, 4),
                    "y": round(min_row / rows, 4),
                    "width": round(region_width, 4),
                    "height": round(region_height, 4),
                    "score": round(_clamp(region_score, 0.0, 1.0), 4),
                }
            )

    regions.sort(key=lambda region: region["score"] * region["width"] * region["height"], reverse=True)
    return regions[:SUSPICIOUS_REGION_LIMIT]


def _build_artifact_map(original: Image.Image, block_map: np.ndarray, analysis_size: tuple[int, int]) -> NoiseTextureMap:
    width, height = analysis_size
    heat_values = (np.clip(block_map, 0.0, 1.0) * 255.0).astype(np.uint8)
    heat_image = Image.fromarray(heat_values, mode="L").resize((width, height), Image.Resampling.BILINEAR)
    heat_image = ImageEnhance.Contrast(heat_image).enhance(1.35)

    alpha = heat_image.point(lambda value: 0 if value < 28 else int(_clamp((value - 28) * 0.78, 0.0, 178.0)))
    colorized = ImageOps.colorize(heat_image, black="#101820", mid="#28c2ff", white="#ff4f8b").convert("RGBA")
    colorized.putalpha(alpha)

    base = ImageOps.grayscale(original.resize((width, height), Image.Resampling.LANCZOS))
    base_rgb = ImageOps.colorize(base, black="#1d2530", white="#e7edf3")
    final_image = Image.alpha_composite(base_rgb.convert("RGBA"), colorized).convert("RGB")

    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return NoiseTextureMap(data_url=f"data:{media_type};base64,{encoded}", media_type=media_type)


def _verdict_for_metrics(
    *,
    raw_score: float,
    strongest_region_delta: float,
    transition_strength: float,
    suspicious_ratio: float,
) -> str:
    strong_local_mismatch = (
        raw_score >= 0.72
        and strongest_region_delta >= 0.34
        and transition_strength >= 0.4
        and suspicious_ratio >= 0.04
    )
    transition_mismatch = raw_score >= 0.8 and transition_strength >= 0.55 and strongest_region_delta >= 0.24
    if strong_local_mismatch or transition_mismatch:
        return "suspicious"

    review_level = (
        raw_score >= 0.48
        and strongest_region_delta >= 0.18
        and transition_strength >= 0.24
        and suspicious_ratio >= 0.02
    )
    localized_noise_shift = (
        raw_score >= 0.6
        and strongest_region_delta >= 0.3
        and transition_strength >= 0.24
        and suspicious_ratio >= 0.005
    )
    if review_level or localized_noise_shift:
        return "inconclusive"
    return "clean"


def _display_score_for_verdict(raw_score: float, verdict: str) -> float:
    if verdict == "suspicious":
        return round(_clamp(raw_score, 0.55, 1.0), 4)
    if verdict == "inconclusive":
        return round(_clamp(raw_score * 0.82, 0.28, 0.48), 4)
    return round(_clamp(raw_score * 0.58, 0.0, 0.24), 4)


def _explanation(
    score: float,
    strongest_region_delta: float,
    transition_strength: float,
    verdict: str,
) -> str:
    if verdict == "suspicious":
        return (
            "Noise and texture analysis found localized residual mismatches between comparable regions, "
            "which can indicate synthetic texture or composited image content."
        )
    if verdict == "inconclusive":
        return (
            "Noise and texture analysis found uneven residual transitions. "
            "The pattern is visible but not strong enough on its own."
        )
    if strongest_region_delta >= 0.12 or transition_strength >= 0.16 or score >= 0.18:
        return (
            "Noise and texture variation is weak and consistent with ordinary scene detail or camera processing. "
            "AI generation is still possible."
        )
    return (
        "Noise residuals and texture descriptors are broadly consistent across the image. "
        "AI generation is still possible."
    )


def analyze_noise_texture(*, image_bytes: bytes, request_id: str) -> NoiseTextureAnalysis:
    original = _open_rgb_image(image_bytes)
    analysis_image = _resize_for_analysis(original)
    luma_image = ImageOps.grayscale(analysis_image)
    luma = np.asarray(luma_image, dtype=np.float64)
    height, width = luma.shape
    block_size = _analysis_block_size(width, height)

    smoothed = _smooth_luma(luma)
    structure = _smooth_luma(luma, radius=2.4)
    residual = luma - smoothed
    if min(structure.shape) < 2:
        gradient = np.zeros_like(structure, dtype=np.float64)
    else:
        gradient_y, gradient_x = np.gradient(structure)
        gradient = np.sqrt((gradient_x * gradient_x) + (gradient_y * gradient_y))

    residual_std = _block_std(residual, block_size)
    residual_mean_abs = _block_mean(np.abs(residual), block_size)
    luma_std = _block_std(structure, block_size)
    gradient_mean = _block_mean(gradient, block_size)
    brightness = _block_mean(luma, block_size)

    texture_descriptor = (luma_std * 0.58) + (gradient_mean * 0.42)
    noise_strength = (residual_std * 0.7) + (residual_mean_abs * 0.3)
    brightness_penalty = 1.0 + (np.abs(brightness - np.median(brightness)) / 255.0)
    texture_adjusted_noise = noise_strength / (1.0 + (texture_descriptor * 0.12)) / brightness_penalty

    outlier_scores = _texture_expected_scores(texture_adjusted_noise, texture_descriptor, brightness)
    transition_scores = _neighbor_transition_scores(texture_adjusted_noise, texture_descriptor, brightness)
    normalized_noise_z = np.clip((np.abs(_robust_z(texture_adjusted_noise)) - 1.15) / 3.2, 0.0, 1.0)
    block_scores = np.clip((outlier_scores * 0.46) + (transition_scores * 0.42) + (normalized_noise_z * 0.12), 0.0, 1.0)

    region_means = _regional_means(block_scores)
    strongest_region_delta = float(np.max(region_means) - np.median(region_means)) if region_means.size else 0.0
    regional_variation = float(np.std(region_means)) if region_means.size else 0.0
    transition_strength = float(np.percentile(transition_scores, 95)) if transition_scores.size else 0.0
    outlier_strength = float(np.percentile(outlier_scores, 97)) if outlier_scores.size else 0.0
    suspicious_threshold = max(float(np.percentile(block_scores, 95)), 0.72) if block_scores.size else 0.72
    suspicious_mask = block_scores >= suspicious_threshold
    suspicious_ratio = float(np.mean(suspicious_mask)) if suspicious_mask.size else 0.0

    block_reliability = _clamp((float(np.sqrt(max(block_scores.size, 1))) - 2.0) / 4.0, 0.45, 1.0)
    raw_score = round(
        _clamp(
            (
                (_clamp(outlier_strength / 0.82, 0.0, 1.0) * 0.3)
                + (_clamp(transition_strength / 0.62, 0.0, 1.0) * 0.32)
                + (_clamp(strongest_region_delta / 0.4, 0.0, 1.0) * 0.16)
                + (_clamp(regional_variation / 0.28, 0.0, 1.0) * 0.08)
                + (_clamp(suspicious_ratio / 0.1, 0.0, 1.0) * 0.14)
            )
            * block_reliability,
            0.0,
            1.0,
        ),
        4,
    )

    verdict = _verdict_for_metrics(
        raw_score=raw_score,
        strongest_region_delta=strongest_region_delta,
        transition_strength=transition_strength,
        suspicious_ratio=suspicious_ratio,
    )
    score = _display_score_for_verdict(raw_score, verdict)
    confidence = round(_clamp(0.56 + (score * 0.36) + min(suspicious_ratio, 0.12), 0.0, 0.94), 4)

    regions = _connected_regions(suspicious_mask, block_scores) if verdict == "suspicious" else []
    artifact_map = _build_artifact_map(
        analysis_image,
        block_scores,
        analysis_size=(block_scores.shape[1] * block_size, block_scores.shape[0] * block_size),
    )

    metrics: dict[str, float | str] = {
        "noise_variance_score": score,
        "raw_noise_variance_score": raw_score,
        "regional_variation": round(regional_variation, 4),
        "strongest_region_delta": round(strongest_region_delta, 4),
        "noise_transition_strength": round(transition_strength, 4),
        "texture_outlier_strength": round(outlier_strength, 4),
        "suspicious_region_ratio": round(suspicious_ratio, 4),
        "sample_reliability": round(block_reliability, 4),
        "mean_texture_descriptor": round(float(np.mean(texture_descriptor)), 4),
        "mean_noise_residual": round(float(np.mean(noise_strength)), 4),
        "analyzed_blocks": float(block_scores.size),
        "request_id": request_id,
    }

    return NoiseTextureAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(score, strongest_region_delta, transition_strength, verdict),
        metrics=metrics,
        artifact_map=artifact_map,
        regions=regions,
    )
