import base64
import io
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageEnhance, ImageOps


TEST_NAME = "JPEG Compression Artifact Analysis"
BLOCK_SIZE = 8
MAX_ANALYSIS_DIMENSION = 768
SUSPICIOUS_REGION_LIMIT = 6


@dataclass(frozen=True)
class ArtifactMap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class JPEGArtifactAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | bool | str]
    artifact_map: ArtifactMap
    regions: list[dict[str, float]]

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "block_inconsistency_score": self.score,
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
    target_size = (max(BLOCK_SIZE, round(width * scale)), max(BLOCK_SIZE, round(height * scale)))
    return image.resize(target_size, Image.Resampling.LANCZOS)


def _crop_to_block_grid(luma: np.ndarray) -> np.ndarray:
    height, width = luma.shape
    crop_height = (height // BLOCK_SIZE) * BLOCK_SIZE
    crop_width = (width // BLOCK_SIZE) * BLOCK_SIZE
    if crop_height == 0 or crop_width == 0:
        raise ValueError("Image is too small for JPEG artifact analysis.")
    return luma[:crop_height, :crop_width]


def _dct_basis(size: int = BLOCK_SIZE) -> np.ndarray:
    basis = np.zeros((size, size), dtype=np.float64)
    factor = math.pi / (2.0 * size)
    for frequency in range(size):
        scale = math.sqrt(1.0 / size) if frequency == 0 else math.sqrt(2.0 / size)
        for position in range(size):
            basis[frequency, position] = scale * math.cos((2 * position + 1) * frequency * factor)
    return basis


def _blocks_from_luma(luma: np.ndarray) -> np.ndarray:
    height, width = luma.shape
    blocks_h = height // BLOCK_SIZE
    blocks_w = width // BLOCK_SIZE
    blocks = luma.reshape(blocks_h, BLOCK_SIZE, blocks_w, BLOCK_SIZE)
    return blocks.transpose(0, 2, 1, 3)


def _high_frequency_energy(blocks: np.ndarray) -> np.ndarray:
    basis = _dct_basis()
    centered_blocks = blocks.astype(np.float64) - 128.0
    coeffs = np.einsum("ux,ijxy,vy->ijuv", basis, centered_blocks, basis, optimize=True)

    frequency_mask = np.fromfunction(lambda u, v: (u + v) >= 6, (BLOCK_SIZE, BLOCK_SIZE), dtype=int)
    return np.mean(np.abs(coeffs[:, :, frequency_mask]), axis=2)


def _boundary_ratios(blocks: np.ndarray) -> np.ndarray:
    blocks_h, blocks_w = blocks.shape[:2]
    ratios = np.zeros((blocks_h, blocks_w), dtype=np.float64)
    counts = np.zeros((blocks_h, blocks_w), dtype=np.float64)

    horizontal_internal = np.abs(blocks[:, :, 1:, :] - blocks[:, :, :-1, :]).mean(axis=(2, 3))
    vertical_internal = np.abs(blocks[:, :, :, 1:] - blocks[:, :, :, :-1]).mean(axis=(2, 3))
    internal_reference = ((horizontal_internal + vertical_internal) / 2.0) + 1.0

    if blocks_w > 1:
        right_boundaries = np.abs(blocks[:, :-1, :, -1] - blocks[:, 1:, :, 0]).mean(axis=2)
        right_ratios = right_boundaries / internal_reference[:, :-1]
        ratios[:, :-1] += right_ratios
        ratios[:, 1:] += right_ratios
        counts[:, :-1] += 1.0
        counts[:, 1:] += 1.0

    if blocks_h > 1:
        bottom_boundaries = np.abs(blocks[:-1, :, -1, :] - blocks[1:, :, 0, :]).mean(axis=2)
        bottom_ratios = bottom_boundaries / internal_reference[:-1, :]
        ratios[:-1, :] += bottom_ratios
        ratios[1:, :] += bottom_ratios
        counts[:-1, :] += 1.0
        counts[1:, :] += 1.0

    return ratios / np.maximum(counts, 1.0)


def _robust_z(values: np.ndarray) -> np.ndarray:
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    scale = max(mad * 1.4826, float(np.std(values)) * 0.35, 1e-6)
    return (values - median) / scale


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
            regions.append(
                {
                    "x": round(min_col / cols, 4),
                    "y": round(min_row / rows, 4),
                    "width": round((max_col - min_col + 1) / cols, 4),
                    "height": round((max_row - min_row + 1) / rows, 4),
                    "score": round(_clamp(region_score, 0.0, 1.0), 4),
                }
            )

    regions.sort(key=lambda region: region["score"] * region["width"] * region["height"], reverse=True)
    return regions[:SUSPICIOUS_REGION_LIMIT]


def _score_map(raw_scores: np.ndarray) -> np.ndarray:
    floor = float(np.percentile(raw_scores, 50))
    ceiling = float(np.percentile(raw_scores, 98))
    if ceiling <= floor:
        ceiling = floor + 1.0
    normalized = (raw_scores - floor) / (ceiling - floor)
    return np.clip(normalized, 0.0, 1.0)


def _build_artifact_map(original: Image.Image, block_map: np.ndarray, analysis_size: tuple[int, int]) -> ArtifactMap:
    width, height = analysis_size
    heat_values = (np.clip(block_map, 0.0, 1.0) * 255.0).astype(np.uint8)
    heat_image = Image.fromarray(heat_values, mode="L").resize((width, height), Image.Resampling.BILINEAR)
    heat_image = ImageEnhance.Contrast(heat_image).enhance(1.4)

    alpha = heat_image.point(lambda value: 0 if value < 35 else int(_clamp((value - 35) * 0.82, 0.0, 180.0)))
    colorized = ImageOps.colorize(heat_image, black="#101820", mid="#ffb000", white="#ff2d2d").convert("RGBA")
    colorized.putalpha(alpha)

    base = ImageOps.grayscale(original.resize((width, height), Image.Resampling.LANCZOS))
    base_rgb = ImageOps.colorize(base, black="#1d2530", white="#e7edf3")
    final_image = Image.alpha_composite(base_rgb.convert("RGBA"), colorized).convert("RGB")

    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return ArtifactMap(data_url=f"data:{media_type};base64,{encoded}", media_type=media_type)


def _explanation(score: float, region_variation: float, suspicious_ratio: float) -> str:
    if score >= 0.5:
        return (
            "JPEG artifact analysis found localized 8x8 block and DCT energy inconsistencies, "
            "which can indicate pasted or recompressed regions."
        )
    if score >= 0.25:
        return (
            "JPEG artifact analysis found moderate regional compression variation. "
            "The signal is visible but not strong enough on its own."
        )
    if region_variation > 0.3 or suspicious_ratio > 0.08:
        return "JPEG artifact variation is present but weak, which can happen after ordinary resizing or saving."
    return "JPEG compression artifacts are broadly consistent across the image."


def analyze_jpeg_artifacts(*, image_bytes: bytes, mime_type: str, request_id: str) -> JPEGArtifactAnalysis:
    original = _open_rgb_image(image_bytes)
    analysis_image = _resize_for_analysis(original)
    luma_image = ImageOps.grayscale(analysis_image)
    luma = _crop_to_block_grid(np.asarray(luma_image, dtype=np.float64))
    blocks = _blocks_from_luma(luma)

    high_frequency = _high_frequency_energy(blocks)
    boundary_ratio = _boundary_ratios(blocks)

    hf_z = _robust_z(high_frequency)
    boundary_z = _robust_z(boundary_ratio)
    raw_block_scores = (hf_z * 0.58) + (boundary_z * 0.42)
    normalized_block_scores = _score_map(raw_block_scores)

    region_means = _regional_means(normalized_block_scores)
    region_variation = float(np.std(region_means))
    strongest_region_delta = float(np.max(region_means) - np.median(region_means)) if region_means.size else 0.0
    dct_variation = float(np.std(high_frequency) / (np.mean(high_frequency) + 1e-6))
    boundary_grid_strength = float(np.mean(np.maximum(boundary_ratio - 1.0, 0.0)))

    suspicious_threshold = max(float(np.percentile(normalized_block_scores, 92)), 0.62)
    suspicious_mask = normalized_block_scores >= suspicious_threshold
    suspicious_ratio = float(np.mean(suspicious_mask))

    region_component = _clamp(strongest_region_delta / 0.34, 0.0, 1.0)
    distribution_component = _clamp(region_variation / 0.24, 0.0, 1.0)
    dct_component = _clamp(dct_variation / 1.25, 0.0, 1.0)
    boundary_component = _clamp(boundary_grid_strength / 1.1, 0.0, 1.0)
    hotspot_component = _clamp(suspicious_ratio / 0.16, 0.0, 1.0)

    score = round(
        _clamp(
            (region_component * 0.28)
            + (distribution_component * 0.18)
            + (dct_component * 0.22)
            + (boundary_component * 0.18)
            + (hotspot_component * 0.14),
            0.0,
            1.0,
        ),
        4,
    )

    source_is_jpeg = mime_type == "image/jpeg" and image_bytes.startswith(b"\xff\xd8\xff")
    confidence = round(_clamp(0.52 + (score * 0.42) + (0.06 if source_is_jpeg else 0.0), 0.0, 1.0), 4)
    verdict = "suspicious" if score >= 0.5 else "inconclusive" if score >= 0.25 else "clean"

    regions = _connected_regions(suspicious_mask, normalized_block_scores)
    artifact_map = _build_artifact_map(
        analysis_image,
        normalized_block_scores,
        analysis_size=(luma.shape[1], luma.shape[0]),
    )

    metrics: dict[str, float | bool | str] = {
        "source_is_jpeg": source_is_jpeg,
        "block_inconsistency_score": score,
        "regional_variation": round(region_variation, 4),
        "strongest_region_delta": round(strongest_region_delta, 4),
        "dct_energy_variation": round(dct_variation, 4),
        "block_grid_strength": round(boundary_grid_strength, 4),
        "suspicious_block_ratio": round(suspicious_ratio, 4),
        "analyzed_blocks": float(normalized_block_scores.size),
        "request_id": request_id,
    }

    return JPEGArtifactAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(score, region_variation, suspicious_ratio),
        metrics=metrics,
        artifact_map=artifact_map,
        regions=regions,
    )
