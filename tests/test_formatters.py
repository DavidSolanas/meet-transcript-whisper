"""Tests for output formatters."""

import pytest

from src.core.models import TranscriptSegment, Word
from src.utils.formatters import format_json, format_srt, format_text, format_vtt


@pytest.fixture
def sample_segments():
    """Sample transcript segments for testing."""
    return [
        TranscriptSegment(
            speaker="SPEAKER_00",
            start=0.0,
            end=2.5,
            text="Hello, welcome to the meeting.",
            words=[
                Word(text="Hello,", start=0.0, end=0.5, speaker="SPEAKER_00"),
                Word(text="welcome", start=0.5, end=1.0, speaker="SPEAKER_00"),
                Word(text="to", start=1.0, end=1.2, speaker="SPEAKER_00"),
                Word(text="the", start=1.2, end=1.4, speaker="SPEAKER_00"),
                Word(text="meeting.", start=1.4, end=2.5, speaker="SPEAKER_00"),
            ],
        ),
        TranscriptSegment(
            speaker="SPEAKER_01",
            start=3.0,
            end=5.5,
            text="Thanks for having me.",
        ),
    ]


class TestSRTFormatter:
    """Tests for SRT format output."""

    def test_format_srt_basic(self, sample_segments):
        """Generate valid SRT format."""
        result = format_srt(sample_segments)

        lines = result.strip().split("\n")
        # First subtitle
        assert lines[0] == "1"
        assert "-->" in lines[1]
        assert "[SPEAKER_00]" in lines[2]

    def test_format_srt_timestamps(self, sample_segments):
        """SRT timestamps are correctly formatted."""
        result = format_srt(sample_segments)

        # Check timestamp format: HH:MM:SS,mmm --> HH:MM:SS,mmm
        assert "00:00:00,000 --> 00:00:02,500" in result
        assert "00:00:03,000 --> 00:00:05,500" in result

    def test_format_srt_without_speakers(self, sample_segments):
        """SRT without speaker labels."""
        result = format_srt(sample_segments, include_speaker=False)

        assert "[SPEAKER_00]" not in result
        assert "Hello, welcome to the meeting." in result


class TestVTTFormatter:
    """Tests for WebVTT format output."""

    def test_format_vtt_header(self, sample_segments):
        """VTT starts with WEBVTT header."""
        result = format_vtt(sample_segments)

        assert result.startswith("WEBVTT")

    def test_format_vtt_timestamps(self, sample_segments):
        """VTT timestamps use dot separator."""
        result = format_vtt(sample_segments)

        # VTT uses . instead of , for milliseconds
        assert "00:00:00.000 --> 00:00:02.500" in result

    def test_format_vtt_voice_tags(self, sample_segments):
        """VTT uses voice tags for speakers."""
        result = format_vtt(sample_segments)

        assert "<v SPEAKER_00>" in result
        assert "<v SPEAKER_01>" in result


class TestJSONFormatter:
    """Tests for JSON format output."""

    def test_format_json_structure(self, sample_segments):
        """JSON has correct structure."""
        result = format_json(
            segments=sample_segments,
            duration_seconds=10.0,
            language="en",
            speakers=["SPEAKER_00", "SPEAKER_01"],
        )

        assert result["duration_seconds"] == 10.0
        assert result["language"] == "en"
        assert result["speakers"] == ["SPEAKER_00", "SPEAKER_01"]
        assert len(result["segments"]) == 2

    def test_format_json_includes_words(self, sample_segments):
        """JSON includes word-level details when available."""
        result = format_json(
            segments=sample_segments,
            duration_seconds=10.0,
            language="en",
            speakers=["SPEAKER_00", "SPEAKER_01"],
        )

        # First segment has words
        assert result["segments"][0]["words"] is not None
        assert len(result["segments"][0]["words"]) == 5

        # Second segment has no words
        assert result["segments"][1]["words"] is None


class TestTextFormatter:
    """Tests for plain text format output."""

    def test_format_text_basic(self, sample_segments):
        """Generate plain text with speaker labels."""
        result = format_text(sample_segments)

        assert "SPEAKER_00: Hello, welcome to the meeting." in result
        assert "SPEAKER_01: Thanks for having me." in result

    def test_format_text_with_timestamps(self, sample_segments):
        """Plain text with timestamps."""
        result = format_text(sample_segments, include_timestamps=True)

        assert "[00:00]" in result
        assert "[00:03]" in result
