import base64
import io
from dataclasses import dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageOps


TEST_NAME = "Copy-Move (Clone) Detection"
MAX_ANALYSIS_DIMENSION = 640
DESCRIPTOR_GRID = 8
MIN_TEXTURE_STD = 4.0
SIMILARITY_THRESHOLD = 0.92
MAX_MATCH_PAIRS = 6000
MIN_CLUSTER_MATCHES = 5
SUSPICIOUS_REGION_LIMIT = 6


@dataclass(frozen=True)
class CopyMoveMap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class CopyMoveAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float | str]
    artifact_map: CopyMoveMap
    regions: list[dict[str, float]]
    clone_pairs: list[dict[str, Any]]

    def to_forensic_test(self) -> dict[str, Any]:
        return {
            "test_name": TEST_NAME,
            "score": self.score,
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "clone_score": self.score,
                "matching_regions": len(self.regions),
                "explanation": self.explanation,
                "metrics": self.metrics,
                "artifact_map": {
                    "url": self.artifact_map.data_url,
                    "mediaType": self.artifact_map.media_type,
                },
                "regions": self.regions,
                "clone_pairs": self.clone_pairs,
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


def _patch_geometry(width: int, height: int) -> tuple[int, int]:
    min_side = max(1, min(width, height))
    if min_side < 16:
        patch_size = max(4, min_side)
    elif min_side < 96:
        patch_size = max(12, min_side // 4)
    else:
        patch_size = int(_clamp(round(min_side / 9), 20, 36))
    patch_size = min(patch_size, width, height)
    stride = 4 if patch_size <= 24 else max(6, patch_size // 3)
    return patch_size, stride


def _pool_to_grid(values: np.ndarray, grid_size: int) -> np.ndarray:
    rows = np.array_split(values, grid_size, axis=0)
    pooled: list[float] = []
    for row in rows:
        cols = np.array_split(row, grid_size, axis=1)
        pooled.extend(float(np.mean(col)) for col in cols if col.size)
    return np.array(pooled, dtype=np.float64)


def _patch_descriptor(patch: np.ndarray) -> np.ndarray | None:
    texture_std = float(np.std(patch))
    if texture_std < MIN_TEXTURE_STD:
        return None

    centered = patch - float(np.mean(patch))
    if min(patch.shape) < 2:
        gradient = np.zeros_like(patch, dtype=np.float64)
    else:
        gradient_y, gradient_x = np.gradient(patch)
        gradient = np.sqrt((gradient_x * gradient_x) + (gradient_y * gradient_y))
        gradient = gradient - float(np.mean(gradient))

    grid_size = min(DESCRIPTOR_GRID, patch.shape[0], patch.shape[1])
    descriptor = np.concatenate(
        [
            _pool_to_grid(centered, grid_size),
            _pool_to_grid(gradient, grid_size),
        ]
    )
    norm = float(np.linalg.norm(descriptor))
    if norm <= 1e-6:
        return None
    return descriptor / norm


def _extract_patch_descriptors(
    luma: np.ndarray,
    *,
    patch_size: int,
    stride: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    height, width = luma.shape
    descriptors: list[np.ndarray] = []
    positions: list[tuple[int, int]] = []
    stats: list[tuple[float, float]] = []

    if height < patch_size or width < patch_size:
        return (
            np.empty((0, 0), dtype=np.float64),
            np.empty((0, 2), dtype=np.float64),
            np.empty((0, 2), dtype=np.float64),
        )

    for top in range(0, height - patch_size + 1, stride):
        for left in range(0, width - patch_size + 1, stride):
            patch = luma[top : top + patch_size, left : left + patch_size]
            descriptor = _patch_descriptor(patch)
            if descriptor is None:
                continue
            descriptors.append(descriptor)
            positions.append((left, top))
            stats.append((float(np.mean(patch)), float(np.std(patch))))

    if not descriptors:
        return (
            np.empty((0, 0), dtype=np.float64),
            np.empty((0, 2), dtype=np.float64),
            np.empty((0, 2), dtype=np.float64),
        )

    return np.vstack(descriptors), np.array(positions, dtype=np.float64), np.array(stats, dtype=np.float64)


def _candidate_pairs(
    luma: np.ndarray,
    descriptors: np.ndarray,
    positions: np.ndarray,
    stats: np.ndarray,
    *,
    patch_size: int,
) -> list[dict[str, float | int]]:
    pair_count = int(descriptors.shape[0])
    if pair_count < 2:
        return []

    similarity = descriptors @ descriptors.T
    upper_rows, upper_cols = np.triu_indices(pair_count, k=1)
    deltas = positions[upper_cols] - positions[upper_rows]
    distances = np.sqrt(np.sum(deltas * deltas, axis=1))
    mean_delta = np.abs(stats[upper_cols, 0] - stats[upper_rows, 0])
    std_delta = np.abs(stats[upper_cols, 1] - stats[upper_rows, 1])
    mask = (
        (similarity[upper_rows, upper_cols] >= SIMILARITY_THRESHOLD)
        & (distances >= patch_size * 1.35)
        & (mean_delta <= 7.0)
        & (std_delta <= 5.0)
    )
    matched_rows = upper_rows[mask]
    matched_cols = upper_cols[mask]
    scores = similarity[matched_rows, matched_cols]

    if scores.size > MAX_MATCH_PAIRS:
        keep = np.argsort(scores)[-MAX_MATCH_PAIRS:]
        matched_rows = matched_rows[keep]
        matched_cols = matched_cols[keep]
        scores = scores[keep]

    pairs: list[dict[str, float | int]] = []
    for index_a, index_b, score in zip(matched_rows, matched_cols, scores):
        x_a, y_a = positions[index_a]
        x_b, y_b = positions[index_b]
        left_a = int(x_a)
        top_a = int(y_a)
        left_b = int(x_b)
        top_b = int(y_b)
        patch_a = luma[top_a : top_a + patch_size, left_a : left_a + patch_size]
        patch_b = luma[top_b : top_b + patch_size, left_b : left_b + patch_size]
        if patch_a.shape != patch_b.shape or patch_a.size == 0:
            continue
        photometric_rmse = float(np.sqrt(np.mean((patch_a - patch_b) ** 2)))
        if photometric_rmse > 10.0:
            continue

        pairs.append(
            {
                "source_index": int(index_a),
                "target_index": int(index_b),
                "source_x": float(x_a),
                "source_y": float(y_a),
                "target_x": float(x_b),
                "target_y": float(y_b),
                "dx": float(x_b - x_a),
                "dy": float(y_b - y_a),
                "similarity": float(score),
                "photometric_rmse": photometric_rmse,
            }
        )
    return pairs


def _box_from_points(points: list[tuple[float, float]], patch_size: int) -> tuple[float, float, float, float]:
    min_x = min(point[0] for point in points)
    min_y = min(point[1] for point in points)
    max_x = max(point[0] for point in points) + patch_size
    max_y = max(point[1] for point in points) + patch_size
    return min_x, min_y, max_x, max_y


def _area(box: tuple[float, float, float, float]) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _intersection_over_union(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    union = _area(first) + _area(second) - intersection
    return 0.0 if union <= 0.0 else intersection / union


def _region_from_box(
    box: tuple[float, float, float, float],
    *,
    width: int,
    height: int,
    score: float,
) -> dict[str, float]:
    left, top, right, bottom = box
    return {
        "x": round(_clamp(left / width, 0.0, 1.0), 4),
        "y": round(_clamp(top / height, 0.0, 1.0), 4),
        "width": round(_clamp((right - left) / width, 0.0, 1.0), 4),
        "height": round(_clamp((bottom - top) / height, 0.0, 1.0), 4),
        "score": round(_clamp(score, 0.0, 1.0), 4),
    }


def _cluster_pairs(
    pairs: list[dict[str, float | int]],
    *,
    width: int,
    height: int,
    patch_size: int,
    stride: int,
) -> list[dict[str, Any]]:
    clusters: dict[tuple[int, int], list[dict[str, float | int]]] = {}
    for pair in pairs:
        dx = float(pair["dx"])
        dy = float(pair["dy"])
        key = (round(dx / stride), round(dy / stride))
        clusters.setdefault(key, []).append(pair)

    image_area = max(1.0, float(width * height))
    accepted: list[dict[str, Any]] = []
    for cluster_pairs in clusters.values():
        if len(cluster_pairs) < MIN_CLUSTER_MATCHES:
            continue

        dx_values = np.array([float(pair["dx"]) for pair in cluster_pairs], dtype=np.float64)
        dy_values = np.array([float(pair["dy"]) for pair in cluster_pairs], dtype=np.float64)
        offset_std = float(np.sqrt(np.var(dx_values) + np.var(dy_values)))
        displacement = float(np.sqrt(np.mean(dx_values) ** 2 + np.mean(dy_values) ** 2))
        if displacement < patch_size * 1.5:
            continue

        coherence = 1.0 - _clamp(offset_std / max(stride, 1), 0.0, 1.0)
        if coherence < 0.62:
            continue

        source_points = sorted({(float(pair["source_x"]), float(pair["source_y"])) for pair in cluster_pairs})
        target_points = sorted({(float(pair["target_x"]), float(pair["target_y"])) for pair in cluster_pairs})
        if len(source_points) < MIN_CLUSTER_MATCHES or len(target_points) < MIN_CLUSTER_MATCHES:
            continue

        source_box = _box_from_points(source_points, patch_size)
        target_box = _box_from_points(target_points, patch_size)
        if _intersection_over_union(source_box, target_box) > 0.12:
            continue

        source_area = _area(source_box)
        target_area = _area(target_box)
        source_area_ratio = source_area / image_area
        target_area_ratio = target_area / image_area
        if min(source_area_ratio, target_area_ratio) < 0.004:
            continue
        if max(source_area_ratio, target_area_ratio) > 0.12:
            continue

        source_density = (len(source_points) * stride * stride) / max(source_area, 1.0)
        target_density = (len(target_points) * stride * stride) / max(target_area, 1.0)
        density = min(source_density, target_density)
        if density < 0.1:
            continue

        mean_similarity = float(np.mean([float(pair["similarity"]) for pair in cluster_pairs]))
        mean_photometric_rmse = float(np.mean([float(pair["photometric_rmse"]) for pair in cluster_pairs]))
        match_component = _clamp((len(cluster_pairs) - MIN_CLUSTER_MATCHES + 1) / 22.0, 0.0, 1.0)
        area_component = _clamp((min(source_area_ratio, target_area_ratio) - 0.004) / 0.035, 0.0, 1.0)
        density_component = _clamp(density / 0.46, 0.0, 1.0)
        similarity_component = _clamp((mean_similarity - SIMILARITY_THRESHOLD) / (1.0 - SIMILARITY_THRESHOLD), 0.0, 1.0)
        photometric_component = _clamp((8.0 - mean_photometric_rmse) / 8.0, 0.0, 1.0)
        cluster_score = _clamp(
            (match_component * 0.24)
            + (area_component * 0.18)
            + (density_component * 0.14)
            + (similarity_component * 0.16)
            + (photometric_component * 0.18)
            + (coherence * 0.1),
            0.0,
            1.0,
        )

        accepted.append(
            {
                "score": cluster_score,
                "match_count": len(cluster_pairs),
                "mean_similarity": mean_similarity,
                "mean_photometric_rmse": mean_photometric_rmse,
                "displacement": displacement,
                "coherence": coherence,
                "density": density,
                "source_box": source_box,
                "target_box": target_box,
            }
        )

    accepted.sort(key=lambda cluster: float(cluster["score"]), reverse=True)
    return accepted[: SUSPICIOUS_REGION_LIMIT // 2]


def _verdict_for_metrics(
    *,
    raw_score: float,
    match_count: int,
    coherence: float,
    region_area_ratio: float,
    mean_similarity: float,
    mean_photometric_rmse: float,
) -> str:
    if (
        raw_score >= 0.62
        and match_count >= 10
        and coherence >= 0.72
        and region_area_ratio >= 0.008
        and mean_similarity >= 0.985
        and mean_photometric_rmse <= 5.5
    ):
        return "suspicious"
    if (
        raw_score >= 0.42
        and match_count >= 7
        and coherence >= 0.62
        and region_area_ratio >= 0.004
        and mean_similarity >= 0.975
        and mean_photometric_rmse <= 7.5
    ):
        return "inconclusive"
    return "clean"


def _display_score_for_verdict(raw_score: float, verdict: str) -> float:
    if verdict == "suspicious":
        return round(_clamp(raw_score, 0.55, 1.0), 4)
    if verdict == "inconclusive":
        return round(_clamp(raw_score * 0.82, 0.28, 0.5), 4)
    return round(_clamp(raw_score * 0.45, 0.0, 0.24), 4)


def _explanation(score: float, match_count: int, verdict: str) -> str:
    if verdict == "suspicious":
        return (
            "Copy-move analysis found duplicated textured regions with a consistent geometric offset, "
            "which can indicate cloned or pasted image content."
        )
    if verdict == "inconclusive":
        return (
            "Copy-move analysis found a small cluster of similar regions. "
            "The geometry is coherent but the support is limited."
        )
    if score >= 0.16 or match_count > 0:
        return (
            "Copy-move analysis found weak repeated texture, but geometric filtering reduced it below clone evidence. "
            "AI generation is still possible."
        )
    return "No coherent duplicated regions were found. AI generation is still possible."


def _build_artifact_map(
    original: Image.Image,
    *,
    analysis_size: tuple[int, int],
    clone_pairs: list[dict[str, Any]],
) -> CopyMoveMap:
    width, height = analysis_size
    base = ImageOps.grayscale(original.resize((width, height), Image.Resampling.LANCZOS))
    base_rgb = ImageOps.colorize(base, black="#1d2530", white="#e7edf3")
    base_rgb = ImageEnhance.Contrast(base_rgb).enhance(1.06).convert("RGBA")
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay, "RGBA")

    for index, pair in enumerate(clone_pairs[:3]):
        source = pair.get("source")
        target = pair.get("target")
        if not isinstance(source, dict) or not isinstance(target, dict):
            continue

        def _pixel_box(region: dict[str, Any]) -> tuple[int, int, int, int]:
            left = int(round(float(region.get("x", 0.0)) * width))
            top = int(round(float(region.get("y", 0.0)) * height))
            right = int(round((float(region.get("x", 0.0)) + float(region.get("width", 0.0))) * width))
            bottom = int(round((float(region.get("y", 0.0)) + float(region.get("height", 0.0))) * height))
            return left, top, right, bottom

        source_box = _pixel_box(source)
        target_box = _pixel_box(target)
        alpha = max(78, 150 - (index * 24))
        draw.rectangle(source_box, fill=(40, 194, 255, 42), outline=(40, 194, 255, alpha), width=3)
        draw.rectangle(target_box, fill=(255, 79, 139, 42), outline=(255, 79, 139, alpha), width=3)
        source_center = ((source_box[0] + source_box[2]) // 2, (source_box[1] + source_box[3]) // 2)
        target_center = ((target_box[0] + target_box[2]) // 2, (target_box[1] + target_box[3]) // 2)
        draw.line((source_center, target_center), fill=(255, 210, 122, alpha), width=2)

    final_image = Image.alpha_composite(base_rgb, overlay).convert("RGB")
    buffer = io.BytesIO()
    final_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return CopyMoveMap(data_url=f"data:{media_type};base64,{encoded}", media_type=media_type)


def analyze_copy_move(*, image_bytes: bytes, request_id: str) -> CopyMoveAnalysis:
    original = _open_rgb_image(image_bytes)
    analysis_image = _resize_for_analysis(original)
    luma = np.asarray(ImageOps.grayscale(analysis_image), dtype=np.float64)
    height, width = luma.shape
    patch_size, stride = _patch_geometry(width, height)
    descriptors, positions, stats = _extract_patch_descriptors(luma, patch_size=patch_size, stride=stride)
    pairs = _candidate_pairs(luma, descriptors, positions, stats, patch_size=patch_size)
    clusters = _cluster_pairs(
        pairs,
        width=width,
        height=height,
        patch_size=patch_size,
        stride=stride,
    )

    strongest_cluster = clusters[0] if clusters else None
    raw_score = round(float(strongest_cluster["score"]) if strongest_cluster else 0.0, 4)
    match_count = int(strongest_cluster["match_count"]) if strongest_cluster else 0
    coherence = float(strongest_cluster["coherence"]) if strongest_cluster else 0.0
    mean_similarity = float(strongest_cluster["mean_similarity"]) if strongest_cluster else 0.0
    mean_photometric_rmse = float(strongest_cluster["mean_photometric_rmse"]) if strongest_cluster else 0.0
    region_area_ratio = (
        min(_area(strongest_cluster["source_box"]), _area(strongest_cluster["target_box"])) / max(1.0, float(width * height))
        if strongest_cluster
        else 0.0
    )
    verdict = _verdict_for_metrics(
        raw_score=raw_score,
        match_count=match_count,
        coherence=coherence,
        region_area_ratio=region_area_ratio,
        mean_similarity=mean_similarity,
        mean_photometric_rmse=mean_photometric_rmse,
    )
    score = _display_score_for_verdict(raw_score, verdict)
    confidence = round(_clamp(0.54 + (score * 0.38) + min(match_count / 220.0, 0.08), 0.0, 0.95), 4)

    regions: list[dict[str, float]] = []
    clone_pairs: list[dict[str, Any]] = []
    if verdict != "clean":
        for cluster_index, cluster in enumerate(clusters):
            cluster_score = float(cluster["score"])
            cluster_similarity = float(cluster["mean_similarity"])
            cluster_rmse = float(cluster["mean_photometric_rmse"])
            if cluster_similarity < 0.975 or cluster_rmse > 7.5 or cluster_score < raw_score * 0.72:
                continue
            source_region = _region_from_box(cluster["source_box"], width=width, height=height, score=cluster_score)
            target_region = _region_from_box(cluster["target_box"], width=width, height=height, score=cluster_score)
            regions.extend([source_region, target_region])
            clone_pairs.append(
                {
                    "source": source_region,
                    "target": target_region,
                    "score": round(cluster_score, 4),
                    "match_count": int(cluster["match_count"]),
                    "mean_similarity": round(cluster_similarity, 4),
                    "mean_photometric_rmse": round(cluster_rmse, 4),
                    "displacement": round(float(cluster["displacement"]), 2),
                }
            )

    regions = regions[:SUSPICIOUS_REGION_LIMIT]
    artifact_map = _build_artifact_map(
        analysis_image,
        analysis_size=(width, height),
        clone_pairs=clone_pairs,
    )

    metrics: dict[str, float | str] = {
        "clone_score": score,
        "raw_clone_score": raw_score,
        "strongest_cluster_similarity": round(mean_similarity, 4),
        "strongest_cluster_rmse": round(mean_photometric_rmse, 4),
        "strongest_cluster_matches": float(match_count),
        "offset_coherence": round(coherence, 4),
        "clone_region_area_ratio": round(region_area_ratio, 4),
        "cluster_count": float(len(clusters)),
        "candidate_patch_count": float(descriptors.shape[0]) if descriptors.ndim == 2 else 0.0,
        "candidate_match_count": float(len(pairs)),
        "patch_size": float(patch_size),
        "stride": float(stride),
        "request_id": request_id,
    }

    return CopyMoveAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(score, match_count, verdict),
        metrics=metrics,
        artifact_map=artifact_map,
        regions=regions,
        clone_pairs=clone_pairs,
    )
