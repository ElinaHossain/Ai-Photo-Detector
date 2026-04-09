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
    explanation: str
    metrics: dict[str, float]
    heatmap: ElaHeatmap


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


def _explanation(score: float, hotspot_ratio_pct: float, p95_intensity: float, block_variation: float) -> str:
    if score >= 75.0:
        return (
            "ELA found concentrated high-intensity recompression differences, suggesting localized editing "
            "or inconsistent JPEG history."
        )
    if score >= 45.0:
        return (
            "ELA shows moderate recompression variation. The image contains uneven hotspots that may warrant "
            "closer review."
        )
    if hotspot_ratio_pct >= 5.0 or p95_intensity >= 40.0 or block_variation >= 18.0:
        return "ELA differences are present but limited, which is more consistent with ordinary compression changes."
    return "ELA response is diffuse and low intensity, which is typical of uniformly compressed images."


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
    hotspot_ratio_pct = (
        sum(1 for value in intensities if value >= HOTSPOT_INTENSITY_THRESHOLD) / total_pixels
    ) * 100.0
    block_variation = _block_mean_variation(diff_gray)

    mean_norm = _clamp(mean_intensity / 18.0, 0.0, 1.0)
    p95_norm = _clamp(p95_intensity / 70.0, 0.0, 1.0)
    hotspot_norm = _clamp(hotspot_ratio_pct / 12.0, 0.0, 1.0)
    block_norm = _clamp(block_variation / 20.0, 0.0, 1.0)
    score = round(((mean_norm * 0.35) + (p95_norm * 0.2) + (hotspot_norm * 0.25) + (block_norm * 0.2)) * 100.0, 2)

    heatmap = _build_heatmap(original, diff_gray)
    encoded_heatmap = _encode_heatmap(heatmap)

    metrics = {
        "mean_intensity": round((mean_intensity / 255.0) * 100.0, 4),
        "std_intensity": round((std_intensity / 255.0) * 100.0, 4),
        "max_intensity": round((max_intensity / 255.0) * 100.0, 4),
        "p95_intensity": round((p95_intensity / 255.0) * 100.0, 4),
        "hotspot_ratio": round(hotspot_ratio_pct, 4),
        "block_variation": round((block_variation / 255.0) * 100.0, 4),
    }

    return ElaAnalysis(
        score=score,
        explanation=_explanation(score, hotspot_ratio_pct, p95_intensity, block_variation),
        metrics=metrics,
        heatmap=encoded_heatmap,
    )
