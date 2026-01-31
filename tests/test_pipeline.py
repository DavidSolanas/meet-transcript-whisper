"""Tests for the transcription pipeline."""

from src.core.models import SpeakerSegment, Word
from src.services.pipeline import (
    align_words_with_speakers,
    merge_words_into_segments,
)


class TestWordSpeakerAlignment:
    """Tests for word-to-speaker alignment."""

    def test_align_words_single_speaker(self):
        """All words assigned to single speaker when no diarization."""
        words = [
            Word(text="Hello", start=0.0, end=0.5),
            Word(text="world", start=0.5, end=1.0),
        ]

        result = align_words_with_speakers(words, [])

        assert all(w.speaker == "SPEAKER_00" for w in result)

    def test_align_words_multiple_speakers(self):
        """Words correctly assigned to different speakers."""
        words = [
            Word(text="Hello", start=0.0, end=0.5),
            Word(text="there", start=0.5, end=1.0),
            Word(text="Hi", start=1.5, end=2.0),
            Word(text="back", start=2.0, end=2.5),
        ]
        speakers = [
            SpeakerSegment(speaker="SPEAKER_00", start=0.0, end=1.2),
            SpeakerSegment(speaker="SPEAKER_01", start=1.4, end=3.0),
        ]

        result = align_words_with_speakers(words, speakers)

        assert result[0].speaker == "SPEAKER_00"  # Hello
        assert result[1].speaker == "SPEAKER_00"  # there
        assert result[2].speaker == "SPEAKER_01"  # Hi
        assert result[3].speaker == "SPEAKER_01"  # back

    def test_align_words_gap_becomes_unknown(self):
        """Words in gaps between speakers marked as UNKNOWN."""
        words = [
            Word(text="Hello", start=0.0, end=0.5),
            Word(text="gap", start=1.5, end=2.0),  # In gap
            Word(text="Hi", start=3.0, end=3.5),
        ]
        speakers = [
            SpeakerSegment(speaker="SPEAKER_00", start=0.0, end=1.0),
            SpeakerSegment(speaker="SPEAKER_01", start=2.5, end=4.0),
        ]

        result = align_words_with_speakers(words, speakers)

        assert result[0].speaker == "SPEAKER_00"
        assert result[1].speaker == "UNKNOWN"  # In gap
        assert result[2].speaker == "SPEAKER_01"

    def test_align_uses_word_midpoint(self):
        """Speaker assignment uses word midpoint, not edges."""
        words = [
            # Word spans 0.8-1.2, midpoint 1.0 is in SPEAKER_01's range
            Word(text="boundary", start=0.8, end=1.2),
        ]
        speakers = [
            SpeakerSegment(speaker="SPEAKER_00", start=0.0, end=0.95),
            SpeakerSegment(speaker="SPEAKER_01", start=0.95, end=2.0),
        ]

        result = align_words_with_speakers(words, speakers)

        # Midpoint is 1.0, which falls in SPEAKER_01's range
        assert result[0].speaker == "SPEAKER_01"


class TestSegmentMerging:
    """Tests for merging words into speaker segments."""

    def test_merge_single_speaker(self):
        """All words from same speaker become one segment."""
        words = [
            Word(text="Hello", start=0.0, end=0.5, speaker="SPEAKER_00"),
            Word(text="world", start=0.5, end=1.0, speaker="SPEAKER_00"),
            Word(text="today", start=1.0, end=1.5, speaker="SPEAKER_00"),
        ]

        segments = merge_words_into_segments(words)

        assert len(segments) == 1
        assert segments[0].speaker == "SPEAKER_00"
        assert segments[0].text == "Hello world today"
        assert segments[0].start == 0.0
        assert segments[0].end == 1.5

    def test_merge_alternating_speakers(self):
        """Speaker changes create new segments."""
        words = [
            Word(text="Hello", start=0.0, end=0.5, speaker="SPEAKER_00"),
            Word(text="Hi", start=1.0, end=1.5, speaker="SPEAKER_01"),
            Word(text="Bye", start=2.0, end=2.5, speaker="SPEAKER_00"),
        ]

        segments = merge_words_into_segments(words)

        assert len(segments) == 3
        assert segments[0].speaker == "SPEAKER_00"
        assert segments[0].text == "Hello"
        assert segments[1].speaker == "SPEAKER_01"
        assert segments[1].text == "Hi"
        assert segments[2].speaker == "SPEAKER_00"
        assert segments[2].text == "Bye"

    def test_merge_empty_words(self):
        """Empty word list returns empty segments."""
        segments = merge_words_into_segments([])
        assert segments == []

    def test_merge_preserves_word_details(self):
        """Merged segments include original word objects."""
        words = [
            Word(text="Hello", start=0.0, end=0.5, speaker="SPEAKER_00", confidence=0.95),
            Word(text="world", start=0.5, end=1.0, speaker="SPEAKER_00", confidence=0.98),
        ]

        segments = merge_words_into_segments(words)

        assert segments[0].words is not None
        assert len(segments[0].words) == 2
        assert segments[0].words[0].confidence == 0.95
