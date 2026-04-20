import base64
import io
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


TEST_NAME = "Resampling / Scaling Detection"
MAX_ANALYSIS_DIMENSION = 768
SUSPICIOUS_REGION_LIMIT = 6
MIN_REGION_AREA_RATIO = 0.0025
MIN_REGION_AVERAGE_SCORE = 0.7


@dataclass(frozen=True)
class ResamplingMap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class ResamplingAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | str]
    artifact_map: ResamplingMap
    regions: list[dict[str, float]]

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "resampling_probability": self.score,
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
    return int(_clamp(round(min_side / 12), 12, 28))


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


def _high_pass(luma: np.ndarray, radius: float = 1.25) -> np.ndarray:
    image = Image.fromarray(np.clip(luma, 0, 255).astype(np.uint8), mode="L")
    blurred = image.filter(ImageFilter.GaussianBlur(radius=radius))
    blurred_arr = np.asarray(blurred, dtype=np.float64)
    return luma - blurred_arr


def _periodicity_features(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = values.shape
    if height < 4 or width < 4:
        zeros = np.zeros_like(values, dtype=np.float64)
        return zeros, zeros

    row_diff = np.abs(values[:, 1:] - values[:, :-1])
    col_diff = np.abs(values[1:, :] - values[:-1, :])

    row_periodicity = np.zeros_like(values, dtype=np.float64)
    col_periodicity = np.zeros_like(values, dtype=np.float64)

    for shift in (2, 3, 4):
        if row_diff.shape[1] > shift:
            row_periodicity[:, shift:] += np.abs(row_diff[:, shift:] - row_diff[:, :-shift])
        if col_diff.shape[0] > shift:
            col_periodicity[shift:, :] += np.abs(col_diff[shift:, :] - col_diff[:-shift, :])

    return row_periodicity, col_periodicity


def _neighbor_transition_scores(
    row_energy: np.ndarray,
    col_energy: np.ndarray,
    brightness: np.ndarray,
) -> np.ndarray:
    rows, cols = row_energy.shape
    transition_map = np.zeros_like(row_energy, dtype=np.float64)
    counts = np.zeros_like(row_energy, dtype=np.float64)

    row_scale = _robust_scale(row_energy.ravel())
    col_scale = _robust_scale(col_energy.ravel())
    brightness_scale = _robust_scale(brightness.ravel())

    def _add_pair(first: tuple[int, int], second: tuple[int, int]) -> None:
        row_a, col_a = first
        row_b, col_b = second

        row_delta = abs(float(row_energy[row_a, col_a] - row_energy[row_b, col_b]))
        col_delta = abs(float(col_energy[row_a, col_a] - col_energy[row_b, col_b]))
        brightness_delta = abs(float(brightness[row_a, col_a] - brightness[row_b, col_b]))

        brightness_weight = float(np.exp(-brightness_delta / max(brightness_scale * 1.8, 2.0)))

        mismatch = (
            _clamp(((row_delta / row_scale) - 1.0) / 2.8, 0.0, 1.0) * 0.5
            + _clamp(((col_delta / col_scale) - 1.0) / 2.8, 0.0, 1.0) * 0.5
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


def _build_artifact_map(original: Image.Image, block_map: np.ndarray, analysis_size: tuple[int, int]) -> ResamplingMap:
    width, height = analysis_size
    heat_values = (np.clip(block_map, 0.0, 1.0) * 255.0).astype(np.uint8)
    heat_image = Image.fromarray(heat_values, mode="L").resize((width, height), Image.Resampling.BILINEAR)
    heat_image = ImageEnhance.Contrast(heat_image).enhance(1.35)

    alpha = heat_image.point(lambda value: 0 if value < 28 else int(_clamp((value - 28) * 0.78, 0.0, 178.0)))
    colorized = ImageOps.colorize(heat_image, black="#101820", mid="#7bdff2", white="#ffd166").convert("RGBA")
    colorized.putalpha(alpha)

    base = ImageOps.grayscale(original.resize((width, height), Image.Resampling.LANCZOS))
    base_rgb = ImageOps.colorize(base, black="#1d2530", white="#e7edf3")
    final_image = Image.alpha_composite(base_rgb.convert("RGBA"), colorized).convert("RGB")

    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return ResamplingMap(data_url=f"data:{media_type};base64,{encoded}", media_type=media_type)


def _verdict_for_metrics(
    *,
    raw_score: float,
    strongest_region_delta: float,
    transition_strength: float,
    suspicious_ratio: float,
) -> str:
    strong_resampling_signal = (
        raw_score >= 0.72
        and strongest_region_delta >= 0.24
        and transition_strength >= 0.3
        and suspicious_ratio >= 0.025
    )
    review_level = (
        raw_score >= 0.48
        and strongest_region_delta >= 0.14
        and transition_strength >= 0.18
        and suspicious_ratio >= 0.01
    )

    if strong_resampling_signal:
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
            "Resampling analysis found localized interpolation-like periodicity, "
            "which can indicate resizing, scaling, or transformed image regions."
        )
    if verdict == "inconclusive":
        return (
            "Resampling analysis found moderate interpolation-like patterns. "
            "The signal is visible but not strong enough on its own."
        )
    if strongest_region_delta >= 0.1 or transition_strength >= 0.12 or score >= 0.18:
        return (
            "Resampling-related variation is weak and may be consistent with ordinary processing. "
            "AI generation is still possible."
        )
    return (
        "No strong resampling or scaling artifacts were found. "
        "AI generation is still possible."
    )


def analyze_resampling_detection(*, image_bytes: bytes, request_id: str) -> ResamplingAnalysis:
    original = _open_rgb_image(image_bytes)
    analysis_image = _resize_for_analysis(original)
    luma_image = ImageOps.grayscale(analysis_image)
    luma = np.asarray(luma_image, dtype=np.float64)
    height, width = luma.shape
    block_size = _analysis_block_size(width, height)

    high_pass = _high_pass(luma, radius=1.25)
    row_periodicity, col_periodicity = _periodicity_features(high_pass)

    row_energy = _block_mean(np.abs(row_periodicity), block_size)
    col_energy = _block_mean(np.abs(col_periodicity), block_size)
    brightness = _block_mean(luma, block_size)

    transition_scores = _neighbor_transition_scores(row_energy, col_energy, brightness)

    row_scale = _robust_scale(row_energy.ravel())
    col_scale = _robust_scale(col_energy.ravel())
    normalized_row_z = np.clip((np.abs((row_energy - np.median(row_energy)) / row_scale) - 1.1) / 2.8, 0.0, 1.0)
    normalized_col_z = np.clip((np.abs((col_energy - np.median(col_energy)) / col_scale) - 1.1) / 2.8, 0.0, 1.0)

    block_scores = np.clip(
        (transition_scores * 0.42)
        + (normalized_row_z * 0.29)
        + (normalized_col_z * 0.29),
        0.0,
        1.0,
    )

    region_means = _regional_means(block_scores)
    strongest_region_delta = float(np.max(region_means) - np.median(region_means)) if region_means.size else 0.0
    regional_variation = float(np.std(region_means)) if region_means.size else 0.0
    transition_strength = float(np.percentile(transition_scores, 95)) if transition_scores.size else 0.0
    row_peak = float(np.percentile(row_energy, 95)) if row_energy.size else 0.0
    col_peak = float(np.percentile(col_energy, 95)) if col_energy.size else 0.0
    suspicious_threshold = max(float(np.percentile(block_scores, 95)), 0.72) if block_scores.size else 0.72
    suspicious_mask = block_scores >= suspicious_threshold
    suspicious_ratio = float(np.mean(suspicious_mask)) if suspicious_mask.size else 0.0

    raw_score = round(
        _clamp(
            (_clamp(transition_strength / 0.58, 0.0, 1.0) * 0.36)
            + (_clamp(row_peak / 6.0, 0.0, 1.0) * 0.2)
            + (_clamp(col_peak / 6.0, 0.0, 1.0) * 0.2)
            + (_clamp(strongest_region_delta / 0.34, 0.0, 1.0) * 0.14)
            + (_clamp(suspicious_ratio / 0.08, 0.0, 1.0) * 0.10),
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
        "resampling_probability": score,
        "raw_resampling_score": raw_score,
        "regional_variation": round(regional_variation, 4),
        "strongest_region_delta": round(strongest_region_delta, 4),
        "transition_strength": round(transition_strength, 4),
        "row_periodicity_peak": round(row_peak, 4),
        "column_periodicity_peak": round(col_peak, 4),
        "suspicious_region_ratio": round(suspicious_ratio, 4),
        "mean_row_energy": round(float(np.mean(row_energy)), 4),
        "mean_column_energy": round(float(np.mean(col_energy)), 4),
        "analyzed_blocks": float(block_scores.size),
        "request_id": request_id,
    }

    return ResamplingAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(score, strongest_region_delta, transition_strength, verdict),
        metrics=metrics,
        artifact_map=artifact_map,
        regions=regions,
    )
