import base64
import io
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


TEST_NAME = "Edge & Boundary Inconsistency Detection"
MAX_ANALYSIS_DIMENSION = 768
SUSPICIOUS_REGION_LIMIT = 6
MIN_REGION_AREA_RATIO = 0.0025
MIN_REGION_AVERAGE_SCORE = 0.7


@dataclass(frozen=True)
class EdgeBoundaryMap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class EdgeBoundaryAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | str]
    artifact_map: EdgeBoundaryMap
    regions: list[dict[str, float]]

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "edge_discontinuity_score": self.score,
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
    target_size = (max(8, round(width * scale)), max(8, round(height * scale)))
    return image.resize(target_size, Image.Resampling.LANCZOS)


def _analysis_block_size(width: int, height: int) -> int:
    min_side = max(1, min(width, height))
    if min_side < 32:
        return max(4, min_side // 2)
    if min_side < 96:
        return max(8, min_side // 4)
    return int(_clamp(round(min_side / 14), 12, 28))


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


def _robust_scale(values: np.ndarray) -> float:
    if values.size == 0:
        return 1.0
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return max(mad * 1.4826, float(np.std(values)) * 0.35, 1e-6)


def _smooth_luma(luma: np.ndarray, radius: float = 1.0) -> np.ndarray:
    image = Image.fromarray(np.clip(luma, 0, 255).astype(np.uint8), mode="L")
    blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))
    return np.asarray(blurred, dtype=np.float64)


def _edge_features(luma: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    smoothed = _smooth_luma(luma, radius=1.0)
    if min(smoothed.shape) < 2:
        zeros = np.zeros_like(smoothed, dtype=np.float64)
        return zeros, zeros, zeros, zeros

    gradient_y, gradient_x = np.gradient(smoothed)
    magnitude = np.sqrt((gradient_x * gradient_x) + (gradient_y * gradient_y))
    orientation = np.arctan2(gradient_y, gradient_x)
    orientation_sin = np.sin(orientation)
    orientation_cos = np.cos(orientation)
    return magnitude, orientation, orientation_sin, orientation_cos


def _neighbor_transition_scores(
    edge_strength: np.ndarray,
    orientation_disorder: np.ndarray,
    brightness: np.ndarray,
) -> np.ndarray:
    rows, cols = edge_strength.shape
    transition_map = np.zeros_like(edge_strength, dtype=np.float64)
    counts = np.zeros_like(edge_strength, dtype=np.float64)

    edge_scale = _robust_scale(edge_strength.ravel())
    disorder_scale = _robust_scale(orientation_disorder.ravel())
    brightness_scale = _robust_scale(brightness.ravel())

    def _add_pair(first: tuple[int, int], second: tuple[int, int]) -> None:
        row_a, col_a = first
        row_b, col_b = second

        edge_delta = abs(float(edge_strength[row_a, col_a] - edge_strength[row_b, col_b]))
        disorder_delta = abs(float(orientation_disorder[row_a, col_a] - orientation_disorder[row_b, col_b]))
        brightness_delta = abs(float(brightness[row_a, col_a] - brightness[row_b, col_b]))

        brightness_weight = float(np.exp(-brightness_delta / max(brightness_scale * 1.8, 2.0)))

        mismatch = (
            _clamp(((edge_delta / edge_scale) - 1.0) / 2.8, 0.0, 1.0) * 0.55
            + _clamp(((disorder_delta / disorder_scale) - 1.0) / 2.6, 0.0, 1.0) * 0.45
        ) * brightness_weight

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


def _build_artifact_map(original: Image.Image, block_map: np.ndarray, analysis_size: tuple[int, int]) -> EdgeBoundaryMap:
    width, height = analysis_size
    heat_values = (np.clip(block_map, 0.0, 1.0) * 255.0).astype(np.uint8)
    heat_image = Image.fromarray(heat_values, mode="L").resize((width, height), Image.Resampling.BILINEAR)
    heat_image = ImageEnhance.Contrast(heat_image).enhance(1.35)

    alpha = heat_image.point(lambda value: 0 if value < 28 else int(_clamp((value - 28) * 0.78, 0.0, 178.0)))
    colorized = ImageOps.colorize(heat_image, black="#101820", mid="#ffd166", white="#ff4f8b").convert("RGBA")
    colorized.putalpha(alpha)

    base = ImageOps.grayscale(original.resize((width, height), Image.Resampling.LANCZOS))
    base_rgb = ImageOps.colorize(base, black="#1d2530", white="#e7edf3")
    final_image = Image.alpha_composite(base_rgb.convert("RGBA"), colorized).convert("RGB")

    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return EdgeBoundaryMap(data_url=f"data:{media_type};base64,{encoded}", media_type=media_type)


def _verdict_for_metrics(
    *,
    raw_score: float,
    strongest_region_delta: float,
    transition_strength: float,
    suspicious_ratio: float,
) -> str:
    strong_local_boundary_mismatch = (
        raw_score >= 0.72
        and strongest_region_delta >= 0.28
        and transition_strength >= 0.34
        and suspicious_ratio >= 0.03
    )
    review_level = (
        raw_score >= 0.48
        and strongest_region_delta >= 0.16
        and transition_strength >= 0.2
        and suspicious_ratio >= 0.015
    )

    if strong_local_boundary_mismatch:
        return "suspicious"
    if review_level:
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
            "Edge and boundary analysis found localized discontinuities in edge structure, "
            "which can indicate pasted boundaries or unnatural compositing transitions."
        )
    if verdict == "inconclusive":
        return (
            "Edge and boundary analysis found moderate local boundary inconsistencies. "
            "The signal is visible but not strong enough on its own."
        )
    if strongest_region_delta >= 0.12 or transition_strength >= 0.14 or score >= 0.18:
        return (
            "Edge variation is weak and broadly consistent with ordinary scene structure. "
            "AI generation is still possible."
        )
    return (
        "No strong edge or boundary discontinuities were found. "
        "AI generation is still possible."
    )


def analyze_edge_boundary(*, image_bytes: bytes, request_id: str) -> EdgeBoundaryAnalysis:
    original = _open_rgb_image(image_bytes)
    analysis_image = _resize_for_analysis(original)
    luma_image = ImageOps.grayscale(analysis_image)
    luma = np.asarray(luma_image, dtype=np.float64)
    height, width = luma.shape
    block_size = _analysis_block_size(width, height)

    magnitude, _, orientation_sin, orientation_cos = _edge_features(luma)
    brightness = _block_mean(luma, block_size)
    edge_strength = _block_mean(magnitude, block_size)

    sin_mean = _block_mean(orientation_sin, block_size)
    cos_mean = _block_mean(orientation_cos, block_size)
    orientation_coherence = np.sqrt((sin_mean * sin_mean) + (cos_mean * cos_mean))
    edge_density = _block_mean((magnitude > np.percentile(magnitude, 75)).astype(np.float64), block_size)
    orientation_disorder = np.clip(edge_density - orientation_coherence, 0.0, 1.0)

    transition_scores = _neighbor_transition_scores(edge_strength, orientation_disorder, brightness)
    edge_strength_scale = _robust_scale(edge_strength.ravel())
    disorder_scale = _robust_scale(orientation_disorder.ravel())

    normalized_edge_z = np.clip((np.abs((edge_strength - np.median(edge_strength)) / edge_strength_scale) - 1.2) / 3.0, 0.0, 1.0)
    normalized_disorder_z = np.clip((np.abs((orientation_disorder - np.median(orientation_disorder)) / disorder_scale) - 1.1) / 2.8, 0.0, 1.0)

    block_scores = np.clip(
        (transition_scores * 0.48)
        + (normalized_disorder_z * 0.32)
        + (normalized_edge_z * 0.20),
        0.0,
        1.0,
    )

    region_means = _regional_means(block_scores)
    strongest_region_delta = float(np.max(region_means) - np.median(region_means)) if region_means.size else 0.0
    regional_variation = float(np.std(region_means)) if region_means.size else 0.0
    transition_strength = float(np.percentile(transition_scores, 95)) if transition_scores.size else 0.0
    disorder_peak = float(np.percentile(orientation_disorder, 95)) if orientation_disorder.size else 0.0
    suspicious_threshold = max(float(np.percentile(block_scores, 95)), 0.72) if block_scores.size else 0.72
    suspicious_mask = block_scores >= suspicious_threshold
    suspicious_ratio = float(np.mean(suspicious_mask)) if suspicious_mask.size else 0.0

    raw_score = round(
        _clamp(
            (_clamp(transition_strength / 0.62, 0.0, 1.0) * 0.38)
            + (_clamp(disorder_peak / 0.58, 0.0, 1.0) * 0.24)
            + (_clamp(strongest_region_delta / 0.36, 0.0, 1.0) * 0.18)
            + (_clamp(regional_variation / 0.24, 0.0, 1.0) * 0.08)
            + (_clamp(suspicious_ratio / 0.08, 0.0, 1.0) * 0.12),
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
    confidence = round(_clamp(0.56 + (score * 0.34) + min(suspicious_ratio, 0.1), 0.0, 0.92), 4)

    regions = _connected_regions(suspicious_mask, block_scores) if verdict == "suspicious" else []
    artifact_map = _build_artifact_map(
        analysis_image,
        block_scores,
        analysis_size=(block_scores.shape[1] * block_size, block_scores.shape[0] * block_size),
    )

    metrics: dict[str, float | str] = {
        "edge_discontinuity_score": score,
        "raw_edge_discontinuity_score": raw_score,
        "regional_variation": round(regional_variation, 4),
        "strongest_region_delta": round(strongest_region_delta, 4),
        "boundary_transition_strength": round(transition_strength, 4),
        "orientation_disorder_peak": round(disorder_peak, 4),
        "suspicious_region_ratio": round(suspicious_ratio, 4),
        "mean_edge_strength": round(float(np.mean(edge_strength)), 4),
        "mean_orientation_disorder": round(float(np.mean(orientation_disorder)), 4),
        "analyzed_blocks": float(block_scores.size),
        "request_id": request_id,
    }

    return EdgeBoundaryAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(score, strongest_region_delta, transition_strength, verdict),
        metrics=metrics,
        artifact_map=artifact_map,
        regions=regions,
    )
