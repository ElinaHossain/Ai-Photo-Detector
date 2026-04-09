"""
Error Level Analysis (ELA) forensic module.

Detects suspicious recompression inconsistencies by re-saving the image
at multiple JPEG quality levels and comparing intensity differences.
Multi-quality analysis is more robust than single-pass ELA because
edited regions behave inconsistently across compression levels.
"""

import io
import logging
import os
import uuid

import numpy as np
from PIL import Image, ImageChops, ImageFilter

from .template import forensic_result_template

logger = logging.getLogger(__name__)

# JPEG quality levels for multi-pass ELA. Lower qualities amplify real differences.
ELA_QUALITIES = [int(q) for q in os.getenv("ELA_QUALITIES", "75,85,95").split(",")]

# Directory where heatmap artifacts are stored.
ARTIFACT_DIR = os.getenv("ELA_ARTIFACT_DIR", os.path.join("artifacts", "ela"))

# Amplification scale for the ELA visualization (standard is 10-20).
# This multiplies the raw RGB pixel differences so they're visible.
# The same fixed scale is used for every image — no per-image normalization.
ELA_VIS_SCALE = int(os.getenv("ELA_VIS_SCALE", "15"))


def _ensure_artifact_dir() -> str:
    """Create the artifact output directory if it does not exist."""
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    return ARTIFACT_DIR


def _compute_ela_diff(image: Image.Image, quality: int) -> np.ndarray:
    """
    Re-save the image as JPEG at the given quality and return the
    raw per-pixel absolute difference as a float64 grayscale array.
    """
    buf = io.BytesIO()
    rgb = image.convert("RGB")
    rgb.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")

    diff = ImageChops.difference(rgb, resaved)
    return np.array(diff.convert("L"), dtype=np.float64)


def _compute_ela_rgb_diff(image: Image.Image, quality: int) -> np.ndarray:
    """
    Re-save and return the full RGB difference array (H, W, 3) as float64.
    """
    buf = io.BytesIO()
    rgb = image.convert("RGB")
    rgb.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")
    return np.abs(np.array(rgb, dtype=np.float64) - np.array(resaved, dtype=np.float64))


def _compute_edge_mask(image: Image.Image) -> np.ndarray:
    """
    Build a binary mask of strong natural edges using a Gaussian-smoothed
    gradient. ELA always shows differences at edges; this mask lets us
    suppress those so only unexpected hotspots are counted.
    """
    gray = image.convert("L").filter(ImageFilter.GaussianBlur(radius=1))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_arr = np.array(edges, dtype=np.float64)
    threshold = np.percentile(edge_arr, 85)
    return (edge_arr > threshold).astype(np.float64)


def _compute_ela_map(image: Image.Image) -> Image.Image:
    """
    FotoForensics-style ELA visualization: re-save at quality 90,
    take the RGB pixel difference, and amplify by a fixed scale.

    This is the standard ELA representation — the output looks like
    a darkened version of the original image where brighter regions
    indicate higher compression differences. Uniform brightness = consistent.
    Bright patches against a dark background = possible editing.
    """
    buf = io.BytesIO()
    rgb = image.convert("RGB")
    rgb.save(buf, format="JPEG", quality=90)
    buf.seek(0)
    resaved = Image.open(buf).convert("RGB")

    diff = ImageChops.difference(rgb, resaved)

    # Fixed amplification — same scale for every image.
    ela_img = diff.point(lambda px: min(px * ELA_VIS_SCALE, 255))
    return ela_img


def _compute_metrics(ela_array: np.ndarray, edge_mask: np.ndarray) -> dict:
    """
    Derive statistical anomaly metrics from a grayscale ELA intensity array.
    Uses an adaptive hotspot threshold and edge suppression.
    """
    mean_intensity = float(np.mean(ela_array))
    std_intensity = float(np.std(ela_array))
    p95_intensity = float(np.percentile(ela_array, 95))

    # Adaptive hotspot threshold: mean + 2 * std (outlier detection).
    hotspot_threshold = mean_intensity + 2.0 * std_intensity
    hotspot_pixels = ela_array > hotspot_threshold
    hotspot_ratio = float(np.mean(hotspot_pixels))

    # Edge-suppressed hotspot ratio: ignore hotspots that sit on natural edges.
    if edge_mask.shape == ela_array.shape:
        non_edge_hotspots = hotspot_pixels & (edge_mask == 0)
        edge_suppressed_hotspot_ratio = float(np.mean(non_edge_hotspots))
    else:
        edge_suppressed_hotspot_ratio = hotspot_ratio

    # Block variation: divide into 8x8 blocks and measure std of block means.
    h, w = ela_array.shape
    block_size = 8
    blocks_h = max(h // block_size, 1)
    blocks_w = max(w // block_size, 1)
    cropped = ela_array[: blocks_h * block_size, : blocks_w * block_size]
    blocks = cropped.reshape(blocks_h, block_size, blocks_w, block_size)
    block_means = blocks.mean(axis=(1, 3))
    block_variation = float(np.std(block_means))

    return {
        "mean_intensity": round(mean_intensity, 3),
        "std_intensity": round(std_intensity, 3),
        "p95_intensity": round(p95_intensity, 3),
        "hotspot_threshold": round(hotspot_threshold, 3),
        "hotspot_ratio": round(hotspot_ratio, 4),
        "edge_suppressed_hotspot_ratio": round(edge_suppressed_hotspot_ratio, 4),
        "block_variation": round(block_variation, 3),
    }


def _score_from_metrics(metrics: dict, cross_quality_std: float) -> float:
    """
    Combine metrics into a single anomaly score in [0.0, 1.0].

    Uses edge-suppressed hotspot ratio so natural edges do not inflate
    the score, and cross-quality standard deviation to detect regions
    that compress inconsistently across quality levels.
    """
    mean_norm = min(metrics["mean_intensity"] / 50.0, 1.0)
    hotspot_norm = min(metrics["edge_suppressed_hotspot_ratio"] / 0.08, 1.0)
    p95_norm = min(metrics["p95_intensity"] / 150.0, 1.0)
    block_norm = min(metrics["block_variation"] / 25.0, 1.0)
    cross_q_norm = min(cross_quality_std / 8.0, 1.0)

    score = (
        mean_norm * 0.20
        + hotspot_norm * 0.25
        + p95_norm * 0.15
        + block_norm * 0.15
        + cross_q_norm * 0.25
    )
    return round(min(max(score, 0.0), 1.0), 3)


def _explain(score: float, metrics: dict) -> str:
    """Generate a human-readable explanation for the ELA result."""
    hr = metrics["edge_suppressed_hotspot_ratio"]
    mi = metrics["mean_intensity"]
    if score >= 0.6:
        return (
            f"ELA detected significant recompression inconsistencies "
            f"(mean intensity {mi:.1f}, "
            f"edge-suppressed hotspot ratio {hr:.2%}). "
            f"This may indicate the image was edited or composited."
        )
    if score >= 0.3:
        return (
            f"ELA shows moderate variation in recompression levels "
            f"(mean intensity {mi:.1f}, "
            f"edge-suppressed hotspot ratio {hr:.2%}). "
            f"Some regions differ from others but the signal is inconclusive."
        )
    return (
        f"ELA shows uniform recompression levels "
        f"(mean intensity {mi:.1f}, "
        f"edge-suppressed hotspot ratio {hr:.2%}). "
        f"No strong evidence of localized editing."
    )


def _save_heatmap(ela_map: Image.Image) -> str:
    """
    Save the ELA heatmap as a PNG artifact and return the filename.
    """
    _ensure_artifact_dir()
    filename = f"ela_{uuid.uuid4().hex[:12]}.png"
    path = os.path.join(ARTIFACT_DIR, filename)
    ela_map.save(path, format="PNG")
    logger.info("ELA heatmap saved: %s", path)
    return filename


def run(image_bytes: bytes) -> dict:
    """
    Run Error Level Analysis on raw image bytes.

    Parameters
    ----------
    image_bytes : bytes
        Raw image file content (JPEG, PNG, or WebP).

    Returns
    -------
    dict
        Forensic result following the standard template.
    """
    result = forensic_result_template("Error Level Analysis (ELA)")

    try:
        image = Image.open(io.BytesIO(image_bytes))
    except Exception as exc:
        logger.warning("ELA: could not open image - %s", exc)
        result["details"] = {"error": "Could not decode image for ELA."}
        return result

    try:
        # Multi-quality ELA: compute diffs at each quality level.
        diffs = [_compute_ela_diff(image, q) for q in ELA_QUALITIES]
        diff_stack = np.stack(diffs, axis=0)
        avg_diff = np.mean(diff_stack, axis=0)

        # Cross-quality std: mean per-pixel std across quality levels.
        # Local edits tend to vary inconsistently across recompression settings.
        cross_quality_std = float(np.mean(np.std(diff_stack, axis=0)))

        # Build edge mask for suppression (resize to match diff if needed).
        edge_mask = _compute_edge_mask(image)
        if edge_mask.shape != avg_diff.shape:
            edge_mask = np.array(
                Image.fromarray((edge_mask * 255).astype(np.uint8)).resize(
                    (avg_diff.shape[1], avg_diff.shape[0]), Image.NEAREST
                ), dtype=np.float64,
            ) / 255.0

        metrics = _compute_metrics(avg_diff, edge_mask)
        metrics["cross_quality_std"] = round(cross_quality_std, 3)

        score = _score_from_metrics(metrics, cross_quality_std)
        confidence = min(0.5 + score * 0.5, 1.0)

        # Generate FotoForensics-style RGB ELA visualization.
        ela_map = _compute_ela_map(image)
        heatmap_filename = _save_heatmap(ela_map)

        result["score"] = score
        result["confidence"] = round(confidence, 3)

        if score >= 0.6:
            result["verdict"] = "suspicious"
        elif score >= 0.3:
            result["verdict"] = "inconclusive"
        else:
            result["verdict"] = "clean"

        result["details"] = {
            "metrics": metrics,
            "explanation": _explain(score, metrics),
            "heatmap_filename": heatmap_filename,
        }
    except Exception as exc:
        logger.exception("ELA: analysis failed - %s", exc)
        result["details"] = {"error": f"ELA analysis failed: {exc}"}

    return result
