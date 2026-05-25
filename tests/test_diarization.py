"""Tests for the diarization service."""

from unittest.mock import MagicMock, patch

from src.services.diarization import DiarizationService


def test_get_pipeline_uses_token_parameter():
    """Diarization pipeline loading should use the current Hugging Face token argument."""
    settings = MagicMock()
    settings.diarization_model = "pyannote/test-model"
    settings.huggingface_access_token = "hf_test_token"
    pipeline = MagicMock()

    DiarizationService._pipeline = None
    try:
        with (
            patch("src.services.diarization.get_settings", return_value=settings),
            patch(
                "src.services.diarization.Pipeline.from_pretrained",
                return_value=pipeline,
            ) as from_pretrained,
            patch.object(DiarizationService, "_get_device", return_value="cpu"),
        ):
            assert DiarizationService.get_pipeline() is pipeline

        from_pretrained.assert_called_once_with(
            "pyannote/test-model",
            token="hf_test_token",
        )
        pipeline.to.assert_called_once_with("cpu")
    finally:
        DiarizationService._pipeline = None
