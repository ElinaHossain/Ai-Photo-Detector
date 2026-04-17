import io
import base64
import math
import statistics
from dataclasses import dataclass

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps


ELA_JPEG_QUALITY = 90
HOTSPOT_INTENSITY_THRESHOLD = 32
HEATMAP_FLOOR_PERCENTILE = 0.6
HEATMAP_CEILING_PERCENTILE = 0.995


@dataclass(frozen=True)
class ElaHeatmap:
    data_url: str
    media_type: str


@dataclass(frozen=True)
class ElaAnalysis:
    score: float
    confidence: float
    verdict: str
    explanation: str
    metrics: dict[str, float]
    heatmap: ElaHeatmap

    def to_forensic_test(self) -> dict[str, object]:
        return {
            "test_name": "Error Level Analysis",
            "score": round(self.score / 100.0, 4),
            "confidence": self.confidence,
            "verdict": self.verdict,
            "details": {
                "ela_score": self.score,
                "explanation": self.explanation,
                "metrics": self.metrics,
                "artifact_map": {
                    "url": self.heatmap.data_url,
                    "mediaType": self.heatmap.media_type,
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


def _recompress_to_jpeg(image: Image.Image) -> Image.Image:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="JPEG",
        quality=ELA_JPEG_QUALITY,
        subsampling=0,
        optimize=False,
        progressive=False,
    )
    buffer.seek(0)
    with Image.open(buffer) as recompressed:
        rgb_image = recompressed.convert("RGB")
        rgb_image.load()
        return rgb_image


def _percentile(sorted_values: list[int], percentile: float) -> float:
    if not sorted_values:
        return 0.0

    rank = (len(sorted_values) - 1) * percentile
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)
    if lower_index == upper_index:
        return float(sorted_values[lower_index])

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    weight = rank - lower_index
    return (lower_value * (1.0 - weight)) + (upper_value * weight)


def _block_mean_variation(image: Image.Image, *, block_size: int = 8) -> float:
    width, height = image.size
    block_means: list[float] = []

    for top in range(0, height, block_size):
        for left in range(0, width, block_size):
            block = image.crop((left, top, min(left + block_size, width), min(top + block_size, height)))
            pixels = list(block.getdata())
            if pixels:
                block_means.append(float(statistics.fmean(pixels)))

    if len(block_means) < 2:
        return 0.0
    return float(statistics.pstdev(block_means))


def _block_difference_stats(
    diff_image: Image.Image,
    original_gray: Image.Image,
    *,
    block_size: int = 8,
) -> dict[str, float]:
    texture_limit = 18.0
    width, height = diff_image.size
    block_means: list[float] = []
    smooth_block_means: list[float] = []

    for top in range(0, height, block_size):
        for left in range(0, width, block_size):
            box = (left, top, min(left + block_size, width), min(top + block_size, height))
            diff_block = diff_image.crop(box)
            diff_pixels = list(diff_block.getdata())
            if not diff_pixels:
                continue

            diff_mean = float(statistics.fmean(diff_pixels))
            block_means.append(diff_mean)

            original_pixels = list(original_gray.crop(box).getdata())
            texture = float(statistics.pstdev(original_pixels)) if len(original_pixels) > 1 else 0.0
            if texture <= texture_limit:
                smooth_block_means.append(diff_mean)

    if not block_means:
        return {
            "median": 0.0,
            "p95": 0.0,
            "p99": 0.0,
            "max": 0.0,
            "std": 0.0,
            "localized_hotspot_ratio": 0.0,
            "smooth_localized_hotspot_ratio": 0.0,
            "smooth_peak_delta": 0.0,
            "smooth_max_delta": 0.0,
        }

    sorted_means = sorted(block_means)
    median = float(statistics.median(sorted_means))
    p95 = _percentile([int(round(value * 1000)) for value in sorted_means], 0.95) / 1000.0
    p99 = _percentile([int(round(value * 1000)) for value in sorted_means], 0.99) / 1000.0
    max_value = float(sorted_means[-1])
    std = float(statistics.pstdev(sorted_means)) if len(sorted_means) > 1 else 0.0
    hotspot_threshold = max(1.75, median + 1.2, p95 + 0.45)
    localized_hotspot_ratio = (
        sum(1 for value in sorted_means if value >= hotspot_threshold) / len(sorted_means)
    ) * 100.0
    smooth_hotspots = [value for value in smooth_block_means if value >= hotspot_threshold]
    smooth_localized_hotspot_ratio = (
        len(smooth_hotspots) / max(1, len(block_means))
    ) * 100.0
    smooth_sorted = sorted(smooth_block_means)
    smooth_p99 = (
        _percentile([int(round(value * 1000)) for value in smooth_sorted], 0.99) / 1000.0
        if smooth_sorted
        else median
    )
    smooth_max = float(smooth_sorted[-1]) if smooth_sorted else median

    return {
        "median": median,
        "p95": p95,
        "p99": p99,
        "max": max_value,
        "std": std,
        "localized_hotspot_ratio": localized_hotspot_ratio,
        "smooth_localized_hotspot_ratio": smooth_localized_hotspot_ratio,
        "smooth_peak_delta": max(0.0, smooth_p99 - median),
        "smooth_max_delta": max(0.0, smooth_max - median),
    }


def _normalize_for_heatmap(diff_gray: Image.Image) -> tuple[Image.Image, float]:
    intensities = sorted(diff_gray.getdata())
    if not intensities:
        return diff_gray.copy(), 0.0

    floor = _percentile(intensities, HEATMAP_FLOOR_PERCENTILE)
    ceiling = _percentile(intensities, HEATMAP_CEILING_PERCENTILE)
    if ceiling <= floor:
        ceiling = max(floor + 1.0, float(intensities[-1]), 1.0)

    dynamic_range = ceiling - floor

    def _stretch(value: int) -> int:
        if value <= floor:
            return 0
        stretched = ((value - floor) / dynamic_range) * 255.0
        gamma_adjusted = math.pow(_clamp(stretched / 255.0, 0.0, 1.0), 0.72) * 255.0
        return int(round(_clamp(gamma_adjusted, 0.0, 255.0)))

    normalized = diff_gray.point(_stretch)
    return normalized, floor


def _build_heatmap(original: Image.Image, diff_gray: Image.Image) -> Image.Image:
    normalized, floor = _normalize_for_heatmap(diff_gray)
    softened = normalized.filter(ImageFilter.GaussianBlur(radius=1.2))
    contrasted = ImageOps.autocontrast(softened, cutoff=0.5)

    def _mask(value: int) -> int:
        if value < 12:
            return 0
        alpha = ((value - 12) / 243.0) * 190.0
        return int(round(_clamp(alpha, 0.0, 190.0)))

    mask = contrasted.point(_mask)
    colorized = ImageOps.colorize(contrasted, black="#0e1422", mid="#2b74ff", white="#ffd27a").convert("RGBA")
    colorized.putalpha(mask)

    base_gray = ImageOps.grayscale(original)
    base_rgb = ImageOps.colorize(base_gray, black="#202735", white="#d7dce5")
    base_rgb = ImageEnhance.Contrast(base_rgb).enhance(1.08)
    base = base_rgb.convert("RGBA")

    final_image = Image.alpha_composite(base, colorized)
    if floor <= 1.0:
        return ImageOps.autocontrast(final_image.convert("RGB"), cutoff=0.25)
    return final_image.convert("RGB")


def _encode_heatmap(heatmap: Image.Image) -> ElaHeatmap:
    buffer = io.BytesIO()
    heatmap.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    media_type = "image/png"
    return ElaHeatmap(
        data_url=f"data:{media_type};base64,{encoded}",
        media_type=media_type,
    )


def _verdict_for_metrics(
    *,
    score: float,
    localized_peak_delta: float,
    localized_max_delta: float,
    localized_hotspot_ratio: float,
    smooth_peak_delta: float,
    smooth_max_delta: float,
    smooth_localized_hotspot_ratio: float,
    hotspot_ratio_pct: float,
) -> str:
    has_clear_hotspot_support = (
        (smooth_peak_delta >= 1.2 and smooth_localized_hotspot_ratio >= 0.35)
        or smooth_max_delta >= 3.0
        or (smooth_localized_hotspot_ratio >= 1.0 and localized_peak_delta >= 1.1)
        or hotspot_ratio_pct >= 2.0
    )
    has_review_level_support = (
        (smooth_peak_delta >= 0.95 and smooth_localized_hotspot_ratio >= 0.2)
        or smooth_max_delta >= 2.2
        or (smooth_localized_hotspot_ratio >= 0.6 and localized_peak_delta >= 0.9)
        or hotspot_ratio_pct >= 1.25
    )

    if score >= 60.0 and has_clear_hotspot_support:
        return "suspicious"
    if score >= 45.0 and has_review_level_support:
        return "inconclusive"
    return "clean"


def _display_score_for_verdict(score: float, verdict: str) -> float:
    if verdict == "clean":
        return round(_clamp(score, 0.0, 24.0), 2)
    if verdict == "inconclusive":
        return round(_clamp(score, 30.0, 54.0), 2)
    return round(score, 2)


def _explanation(
    score: float,
    hotspot_ratio_pct: float,
    p95_intensity: float,
    block_variation: float,
    localized_peak_delta: float,
    verdict: str,
) -> str:
    if verdict == "suspicious" and score >= 75.0:
        return (
            "ELA found concentrated local error hotspots, which can indicate drawn, pasted, or recompressed edits."
        )
    if verdict == "suspicious":
        return (
            "ELA found localized error hotspots. Review the heatmap before treating the image as clean."
        )
    if verdict == "inconclusive":
        return "ELA shows moderate local variation. The signal is not strong enough on its own."
    if localized_peak_delta >= 1.0:
        return (
            "ELA found small local differences, but the pattern is consistent with normal compression or texture. "
            "AI generation is still possible."
        )
    if hotspot_ratio_pct >= 5.0 or p95_intensity >= 40.0 or block_variation >= 18.0:
        return (
            "ELA differences are present but limited, which is more consistent with ordinary compression changes. "
            "AI generation is still possible."
        )
    return (
        "ELA response is diffuse and low intensity, which is typical of uniformly compressed images. "
        "AI generation is still possible."
    )


def analyze_ela(*, image_bytes: bytes, request_id: str) -> ElaAnalysis:
    original = _open_rgb_image(image_bytes)
    recompressed = _recompress_to_jpeg(original)

    diff_rgb = ImageChops.difference(original, recompressed)
    diff_gray = ImageOps.grayscale(diff_rgb)
    intensities = list(diff_gray.getdata())
    sorted_intensities = sorted(intensities)

    total_pixels = max(1, len(intensities))
    mean_intensity = float(statistics.fmean(intensities)) if intensities else 0.0
    std_intensity = float(statistics.pstdev(intensities)) if len(intensities) > 1 else 0.0
    max_intensity = float(sorted_intensities[-1]) if sorted_intensities else 0.0
    p95_intensity = _percentile(sorted_intensities, 0.95)
    p99_intensity = _percentile(sorted_intensities, 0.99)
    hotspot_ratio_pct = (
        sum(1 for value in intensities if value >= HOTSPOT_INTENSITY_THRESHOLD) / total_pixels
    ) * 100.0
    block_variation = _block_mean_variation(diff_gray)
    original_gray = ImageOps.grayscale(original)
    block_stats = _block_difference_stats(diff_gray, original_gray)
    localized_peak_delta = max(0.0, block_stats["p99"] - block_stats["median"])
    localized_max_delta = max(0.0, block_stats["max"] - block_stats["median"])

    mean_norm = _clamp(mean_intensity / 18.0, 0.0, 1.0)
    p95_norm = _clamp(p95_intensity / 70.0, 0.0, 1.0)
    p99_norm = _clamp(p99_intensity / 24.0, 0.0, 1.0)
    max_norm = _clamp(max_intensity / 24.0, 0.0, 1.0)
    hotspot_norm = _clamp(hotspot_ratio_pct / 12.0, 0.0, 1.0)
    block_norm = _clamp(block_variation / 20.0, 0.0, 1.0)
    broad_score = (
        (mean_norm * 0.22)
        + (p95_norm * 0.14)
        + (p99_norm * 0.16)
        + (max_norm * 0.18)
        + (hotspot_norm * 0.16)
        + (block_norm * 0.14)
    ) * 100.0
    localized_score = (
        (_clamp(localized_peak_delta / 1.1, 0.0, 1.0) * 0.42)
        + (_clamp(localized_max_delta / 2.0, 0.0, 1.0) * 0.38)
        + (_clamp(block_stats["localized_hotspot_ratio"] / 2.0, 0.0, 1.0) * 0.20)
    ) * 100.0
    raw_score = round(max(broad_score, localized_score), 2)
    verdict = _verdict_for_metrics(
        score=raw_score,
        localized_peak_delta=localized_peak_delta,
        localized_max_delta=localized_max_delta,
        localized_hotspot_ratio=block_stats["localized_hotspot_ratio"],
        smooth_peak_delta=block_stats["smooth_peak_delta"],
        smooth_max_delta=block_stats["smooth_max_delta"],
        smooth_localized_hotspot_ratio=block_stats["smooth_localized_hotspot_ratio"],
        hotspot_ratio_pct=hotspot_ratio_pct,
    )
    score = _display_score_for_verdict(raw_score, verdict)
    confidence = round(_clamp(0.54 + ((score / 100.0) * 0.4), 0.0, 0.94), 4)

    heatmap = _build_heatmap(original, diff_gray)
    encoded_heatmap = _encode_heatmap(heatmap)

    metrics = {
        "mean_intensity": round((mean_intensity / 255.0) * 100.0, 4),
        "std_intensity": round((std_intensity / 255.0) * 100.0, 4),
        "max_intensity": round((max_intensity / 255.0) * 100.0, 4),
        "p95_intensity": round((p95_intensity / 255.0) * 100.0, 4),
        "p99_intensity": round((p99_intensity / 255.0) * 100.0, 4),
        "raw_ela_score": raw_score,
        "hotspot_ratio": round(hotspot_ratio_pct, 4),
        "block_variation": round((block_variation / 255.0) * 100.0, 4),
        "localized_peak_delta": round((localized_peak_delta / 255.0) * 100.0, 4),
        "localized_max_delta": round((localized_max_delta / 255.0) * 100.0, 4),
        "localized_hotspot_ratio": round(block_stats["localized_hotspot_ratio"], 4),
        "smooth_peak_delta": round((block_stats["smooth_peak_delta"] / 255.0) * 100.0, 4),
        "smooth_max_delta": round((block_stats["smooth_max_delta"] / 255.0) * 100.0, 4),
        "smooth_localized_hotspot_ratio": round(block_stats["smooth_localized_hotspot_ratio"], 4),
    }

    return ElaAnalysis(
        score=score,
        confidence=confidence,
        verdict=verdict,
        explanation=_explanation(
            score,
            hotspot_ratio_pct,
            p95_intensity,
            block_variation,
            localized_peak_delta,
            verdict,
        ),
        metrics=metrics,
        heatmap=encoded_heatmap,
    )
