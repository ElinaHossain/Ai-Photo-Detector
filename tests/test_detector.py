import io
import math

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from backend.detector.ela import analyze_ela, _verdict_for_metrics as _ela_verdict_for_metrics
from backend.detector.jpeg_artifacts import analyze_jpeg_artifacts, _verdict_for_metrics
from backend.detector.postprocess import _status_for_value, postprocess_prediction
from backend.detector.predict import ModelUnavailableError, PredictionOutput, predict_scores
from backend.detector.preprocess import preprocess_image


class TestPreprocessImage:
    def test_returns_expected_model_input_and_metadata(self, sample_png_bytes):
        result = preprocess_image(image_bytes=sample_png_bytes, mime_type="image/png")

        assert set(result.model_input) == {"entropy", "zero_ratio", "size_log", "size_norm"}
        assert result.metadata == {
            "mime_type": "image/png",
            "byte_length": len(sample_png_bytes),
            "deterministic": False,
        }
        assert 0.0 <= result.model_input["entropy"] <= 8.0
        assert 0.0 <= result.model_input["zero_ratio"] <= 1.0
        assert result.model_input["size_log"] == pytest.approx(math.log1p(len(sample_png_bytes)))
        assert 0.0 <= result.model_input["size_norm"] <= 1.0

    def test_rejects_empty_bytes(self):
        with pytest.raises(ValueError, match="empty"):
            preprocess_image(image_bytes=b"", mime_type="image/png")

    def test_rejects_unsupported_mime_type(self, sample_png_bytes):
        with pytest.raises(ValueError, match="Unsupported MIME type"):
            preprocess_image(image_bytes=sample_png_bytes, mime_type="image/gif")

    def test_rejects_mime_signature_mismatch(self, sample_png_bytes):
        with pytest.raises(ValueError, match="does not match"):
            preprocess_image(image_bytes=sample_png_bytes, mime_type="image/jpeg")

    def test_accepts_valid_webp_signature(self, sample_webp_bytes):
        result = preprocess_image(
            image_bytes=sample_webp_bytes,
            mime_type="image/webp",
            deterministic=True,
        )

        assert result.metadata["mime_type"] == "image/webp"
        assert result.metadata["deterministic"] is True

    def test_includes_inline_ela_heatmap_when_request_id_is_present(self):
        image = Image.new("RGB", (12, 12), color=(180, 190, 200))
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")

        result = preprocess_image(
            image_bytes=buffer.getvalue(),
            mime_type="image/png",
            request_id="req-123",
        )

        assert "ela" in result.metadata
        heatmap = result.metadata["ela"]["heatmap"]
        assert heatmap["mediaType"] == "image/png"
        assert heatmap["url"].startswith("data:image/png;base64,")
        assert "artifact" not in result.metadata["ela"]
        test_names = [test["test_name"] for test in result.metadata["forensic_tests"]]
        assert test_names == ["Error Level Analysis", "Compression Artifact Analysis"]


class TestJPEGArtifactAnalysis:
    @staticmethod
    def _jpeg_bytes(image: Image.Image, *, quality: int) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, subsampling=0)
        return buffer.getvalue()

    @staticmethod
    def _textured_image(size: tuple[int, int] = (192, 192)) -> Image.Image:
        width, height = size
        y_coords, x_coords = np.mgrid[0:height, 0:width]
        red = 80 + x_coords * 0.55 + 18 * np.sin(y_coords / 9)
        green = 90 + y_coords * 0.45 + 16 * np.cos(x_coords / 13)
        blue = 120 + (x_coords + y_coords) * 0.25 + 10 * np.sin((x_coords + y_coords) / 11)
        noise = np.random.default_rng(7).normal(0, 4, (height, width))
        pixels = np.stack([red + noise, green + noise, blue + noise], axis=2)
        return Image.fromarray(np.clip(pixels, 0, 255).astype("uint8"), "RGB")

    def test_scores_localized_recompression_above_clean_baseline(self):
        base_image = self._textured_image()
        clean_bytes = self._jpeg_bytes(base_image, quality=92)

        recompressed_base = Image.open(io.BytesIO(clean_bytes)).convert("RGB")
        patch = recompressed_base.crop((64, 64, 136, 136))
        low_quality_patch = Image.open(io.BytesIO(self._jpeg_bytes(patch, quality=25))).convert("RGB")
        manipulated = recompressed_base.copy()
        manipulated.paste(low_quality_patch, (64, 64))
        manipulated_bytes = self._jpeg_bytes(manipulated, quality=95)

        clean = analyze_jpeg_artifacts(
            image_bytes=clean_bytes,
            mime_type="image/jpeg",
            request_id="clean",
        )
        edited = analyze_jpeg_artifacts(
            image_bytes=manipulated_bytes,
            mime_type="image/jpeg",
            request_id="edited",
        )

        assert edited.score > clean.score + 0.15
        assert edited.metrics["block_inconsistency_score"] == edited.score
        assert edited.verdict == "suspicious"
        assert edited.artifact_map.data_url.startswith("data:image/png;base64,")
        assert edited.regions

    def test_moderate_score_without_grid_mismatch_is_clean(self):
        verdict = _verdict_for_metrics(
            raw_score=0.57,
            source_is_jpeg=True,
            strongest_region_delta=0.18,
            boundary_grid_strength=0.04,
        )

        assert verdict == "clean"

    def test_borderline_score_with_partial_support_is_inconclusive(self):
        verdict = _verdict_for_metrics(
            raw_score=0.65,
            source_is_jpeg=True,
            strongest_region_delta=0.2,
            boundary_grid_strength=0.04,
        )

        assert verdict == "inconclusive"

    def test_localized_grid_mismatch_remains_suspicious(self):
        verdict = _verdict_for_metrics(
            raw_score=0.51,
            source_is_jpeg=True,
            strongest_region_delta=0.31,
            boundary_grid_strength=0.21,
        )

        assert verdict == "suspicious"

    def test_non_jpeg_can_still_report_strong_compression_evidence(self):
        verdict = _verdict_for_metrics(
            raw_score=0.72,
            source_is_jpeg=False,
            strongest_region_delta=0.35,
            boundary_grid_strength=0.18,
        )

        assert verdict == "suspicious"


class TestElaAnalysis:
    @staticmethod
    def _jpeg_bytes(image: Image.Image, *, quality: int) -> bytes:
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=quality, subsampling=0)
        return buffer.getvalue()

    @staticmethod
    def _photo_like_image(size: tuple[int, int] = (256, 256)) -> Image.Image:
        width, height = size
        rng = np.random.default_rng(11)
        y_coords, x_coords = np.mgrid[0:height, 0:width]
        red = 70 + x_coords * 0.42 + rng.normal(0, 5, (height, width))
        green = 84 + y_coords * 0.36 + rng.normal(0, 5, (height, width))
        blue = 112 + (x_coords + y_coords) * 0.16 + rng.normal(0, 5, (height, width))
        pixels = np.stack([red, green, blue], axis=2)
        return Image.fromarray(np.clip(pixels, 0, 255).astype("uint8"), "RGB").filter(
            ImageFilter.GaussianBlur(0.7)
        )

    def test_pasted_smooth_object_scores_above_clean_baseline(self):
        base_image = self._photo_like_image()
        clean_bytes = self._jpeg_bytes(base_image, quality=85)

        edited = Image.open(io.BytesIO(clean_bytes)).convert("RGB")
        patch = Image.new("RGB", (74, 64), (235, 235, 245))
        draw = ImageDraw.Draw(patch)
        draw.ellipse((8, 8, 66, 56), fill=(30, 120, 230))
        draw.rectangle((28, 18, 48, 48), fill=(250, 60, 60))
        edited.paste(patch, (78, 72))
        edited_bytes = self._jpeg_bytes(edited, quality=85)

        clean = analyze_ela(image_bytes=clean_bytes, request_id="clean")
        pasted = analyze_ela(image_bytes=edited_bytes, request_id="pasted")

        assert pasted.score > clean.score + 25.0
        assert pasted.verdict == "suspicious"
        assert pasted.to_forensic_test()["test_name"] == "Error Level Analysis"
        assert pasted.to_forensic_test()["details"]["artifact_map"]["url"].startswith("data:image/png;base64,")

    def test_moderate_ela_score_without_hotspot_support_stays_clean(self):
        verdict = _ela_verdict_for_metrics(
            score=32.2,
            localized_peak_delta=0.62,
            localized_max_delta=1.1,
            localized_hotspot_ratio=0.0,
            smooth_peak_delta=0.2,
            smooth_max_delta=0.5,
            smooth_localized_hotspot_ratio=0.0,
            hotspot_ratio_pct=0.0,
        )

        assert verdict == "clean"

    def test_moderate_ela_score_with_hotspot_support_is_inconclusive(self):
        verdict = _ela_verdict_for_metrics(
            score=48.0,
            localized_peak_delta=0.95,
            localized_max_delta=1.4,
            localized_hotspot_ratio=0.0,
            smooth_peak_delta=0.98,
            smooth_max_delta=1.4,
            smooth_localized_hotspot_ratio=0.3,
            hotspot_ratio_pct=0.0,
        )

        assert verdict == "inconclusive"

    def test_textured_hotspots_without_smooth_support_stay_clean(self):
        verdict = _ela_verdict_for_metrics(
            score=79.7,
            localized_peak_delta=1.4,
            localized_max_delta=3.2,
            localized_hotspot_ratio=2.5,
            smooth_peak_delta=0.2,
            smooth_max_delta=0.4,
            smooth_localized_hotspot_ratio=0.0,
            hotspot_ratio_pct=0.0,
        )

        assert verdict == "clean"

    def test_high_texture_outdoor_scene_stays_clean(self):
        rng = np.random.default_rng(23)
        width, height = 256, 256
        y_coords, x_coords = np.mgrid[0:height, 0:width]
        base = np.stack(
            [
                80 + x_coords * 0.18 + rng.normal(0, 18, (height, width)),
                95 + y_coords * 0.16 + rng.normal(0, 18, (height, width)),
                110 + (x_coords + y_coords) * 0.08 + rng.normal(0, 18, (height, width)),
            ],
            axis=2,
        )
        image = Image.fromarray(np.clip(base, 0, 255).astype("uint8"), "RGB").filter(
            ImageFilter.GaussianBlur(0.35)
        )
        draw = ImageDraw.Draw(image)
        for _ in range(35):
            draw.line(
                (
                    int(rng.integers(0, width)),
                    int(rng.integers(0, height)),
                    int(rng.integers(0, width)),
                    int(rng.integers(0, height)),
                ),
                fill=(20, 30, 25),
                width=int(rng.integers(1, 3)),
            )
        for _ in range(120):
            draw.point(
                (int(rng.integers(0, width)), int(rng.integers(0, height))),
                fill=(245, 245, 230),
            )

        analysis = analyze_ela(
            image_bytes=self._jpeg_bytes(image, quality=86),
            request_id="natural-texture",
        )

        assert analysis.verdict == "clean"


class TestPredictScores:
    def test_returns_prediction_contract_from_provider(self, monkeypatch):
        monkeypatch.setenv("BITMIND_API_KEY", "test-key")
        monkeypatch.setattr(
            "backend.detector.predict._run_bitmind_inference",
            lambda api_key, metadata=None: {
                "ai_probability": 61.5,
                "provider_score": 61.5,
                "provider_is_ai": True,
            },
        )

        result = predict_scores(
            model_input={"entropy": 1.0},
            metadata={"image_bytes": b"123", "mime_type": "image/png"},
            allow_fallback=False,
        )

        assert isinstance(result, PredictionOutput)
        assert isinstance(result.ai_probability, float)
        assert isinstance(result.raw_scores, dict)
        assert isinstance(result.model_name, str)
        assert isinstance(result.used_fallback, bool)
        assert result.ai_probability == pytest.approx(61.5)
        assert 0.0 <= result.ai_probability <= 100.0
        assert result.model_name == "bitmind_api"
        assert result.used_fallback is False

    def test_clamps_out_of_range_ai_probability(self, monkeypatch):
        monkeypatch.setenv("BITMIND_API_KEY", "test-key")
        monkeypatch.setattr(
            "backend.detector.predict._run_bitmind_inference",
            lambda api_key, metadata=None: {"ai_probability": 250.0},
        )

        result = predict_scores(
            model_input={"entropy": 1.0},
            metadata={"image_bytes": b"123", "mime_type": "image/png"},
            allow_fallback=False,
        )

        assert result.ai_probability == 100.0

    def test_provider_real_verdict_with_high_score_becomes_low_ai_probability(self, monkeypatch):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"is_ai": False, "score": 91.9}

        monkeypatch.setenv("BITMIND_API_KEY", "test-key")
        monkeypatch.setattr("backend.detector.predict.requests.post", lambda *args, **kwargs: Response())

        result = predict_scores(
            model_input={"entropy": 1.0},
            metadata={"image_bytes": b"123", "mime_type": "image/png"},
            allow_fallback=False,
        )

        assert result.ai_probability == pytest.approx(8.1)
        assert result.raw_scores["provider_confidence"] == pytest.approx(91.9)
        assert result.raw_scores["provider_is_ai"] is False

    def test_uses_fallback_when_model_is_unavailable_and_allowed(self, monkeypatch):
        monkeypatch.setenv("BITMIND_API_KEY", "test-key")

        def raise_unavailable(api_key, metadata=None):
            raise ModelUnavailableError("provider unavailable")

        monkeypatch.setattr("backend.detector.predict._run_bitmind_inference", raise_unavailable)
        monkeypatch.setattr(
            "backend.detector.predict._heuristic_inference",
            lambda model_input, deterministic_seed=None: {"ai_probability": 42.0},
        )

        result = predict_scores(
            model_input={"entropy": 1.0},
            metadata={"image_bytes": b"123", "mime_type": "image/png"},
        )

        assert result.ai_probability == 42.0
        assert result.model_name == "heuristic_fallback"
        assert result.used_fallback is True

    def test_raises_when_model_is_unavailable_and_fallback_is_disabled(self, monkeypatch):
        monkeypatch.setenv("BITMIND_API_KEY", "test-key")

        def raise_unavailable(api_key, metadata=None):
            raise ModelUnavailableError("provider unavailable")

        monkeypatch.setattr("backend.detector.predict._run_bitmind_inference", raise_unavailable)

        with pytest.raises(ModelUnavailableError):
            predict_scores(
                model_input={"entropy": 1.0},
                metadata={"image_bytes": b"123", "mime_type": "image/png"},
                allow_fallback=False,
            )


class TestPostprocessPrediction:
    @pytest.mark.parametrize(
        ("value", "expected_status"),
        [
            (49.99, "fail"),
            (50.0, "warning"),
            (74.99, "warning"),
            (75.0, "pass"),
        ],
    )
    def test_status_mapping(self, value, expected_status):
        assert _status_for_value(value) == expected_status

    @pytest.mark.parametrize(
        ("probability", "threshold", "expected"),
        [
            (59.99, 60.0, False),
            (60.0, 60.0, True),
            (84.62, 60.0, True),
            (40.0, 75.0, False),
        ],
    )
    def test_threshold_mapping(self, probability, threshold, expected):
        prediction = PredictionOutput(
            ai_probability=probability,
            raw_scores={"ai_probability": probability},
            model_name="configured_model",
            used_fallback=False,
        )

        result = postprocess_prediction(prediction=prediction, threshold=threshold)

        assert result.isAIGenerated is expected
        assert result.confidence == round(probability, 2)
        assert len(result.indicators) == 5

        for indicator in result.indicators:
            assert isinstance(indicator["label"], str)
            assert isinstance(indicator["value"], float)
            assert indicator["status"] in {"pass", "warning", "fail"}
            assert 0.0 <= indicator["value"] <= 100.0
