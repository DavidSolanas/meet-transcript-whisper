"""Main processing pipeline combining transcription and diarization with alignment."""

from dataclasses import dataclass
from pathlib import Path

import structlog

from src.core.models import SpeakerSegment, TranscriptSegment, Word
from src.services.diarization import DiarizationService
from src.services.transcription import TranscriptionService

logger = structlog.get_logger(__name__)


@dataclass
class PipelineResult:
    """Result from the transcription pipeline."""

    text: str
    language: str | None
    duration_seconds: float
    speakers: list[str]
    segments: list[TranscriptSegment]
    words: list[Word]


def align_words_with_speakers(
    words: list[Word],
    speaker_segments: list[SpeakerSegment],
) -> list[Word]:
    """
    Assign speaker labels to each word based on timestamp overlap.

    Uses the midpoint of each word to determine which speaker segment it belongs to.
    Words that don't fall within any speaker segment are labeled as "UNKNOWN".
    """
    if not speaker_segments:
        # No diarization, mark all as single speaker
        for word in words:
            word.speaker = "SPEAKER_00"
        return words

    for word in words:
        word_mid = (word.start + word.end) / 2

        # Find the speaker segment that contains this word's midpoint
        speaker = next(
            (seg.speaker for seg in speaker_segments if seg.start <= word_mid <= seg.end),
            "UNKNOWN",
        )
        word.speaker = speaker

    return words


def merge_words_into_segments(words: list[Word]) -> list[TranscriptSegment]:
    """
    Merge consecutive words from the same speaker into transcript segments.

    Creates natural segments by grouping words by speaker, with segment boundaries
    where the speaker changes.
    """
    if not words:
        return []

    segments: list[TranscriptSegment] = []
    current_speaker: str | None = None
    current_words: list[Word] = []

    for word in words:
        if word.speaker != current_speaker:
            # Speaker changed, save current segment
            if current_words:
                segments.append(_create_segment(current_words, current_speaker or "UNKNOWN"))
            current_speaker = word.speaker
            current_words = [word]
        else:
            current_words.append(word)

    # Don't forget the last segment
    if current_words:
        segments.append(_create_segment(current_words, current_speaker or "UNKNOWN"))

    return segments


def _create_segment(words: list[Word], speaker: str) -> TranscriptSegment:
    """Create a transcript segment from a list of words."""
    text = " ".join(w.text for w in words)
    return TranscriptSegment(
        speaker=speaker,
        start=words[0].start,
        end=words[-1].end,
        text=text,
        words=words,
    )


def get_audio_duration(audio_path: str | Path) -> float:
    """Get the duration of an audio file in seconds."""
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(audio_path))
        return len(audio) / 1000.0  # Convert ms to seconds
    except Exception as e:
        logger.warning("Could not determine audio duration", error=str(e))
        return 0.0


class TranscriptionPipeline:
    """Main pipeline that orchestrates transcription and diarization."""

    @classmethod
    def process(
        cls,
        audio_path: str | Path,
        language: str | None = None,
        enable_diarization: bool = True,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        word_timestamps: bool = True,
    ) -> PipelineResult:
        """
        Process an audio file through the full transcription pipeline.

        Args:
            audio_path: Path to the audio file
            language: Language code for transcription (auto-detect if None)
            enable_diarization: Whether to perform speaker diarization
            min_speakers: Minimum number of speakers hint
            max_speakers: Maximum number of speakers hint
            word_timestamps: Whether to include word-level timestamps

        Returns:
            PipelineResult with transcription, speaker labels, and timing
        """
        audio_path = Path(audio_path)
        logger.info("Starting pipeline", audio_path=str(audio_path))

        # Get audio duration
        duration = get_audio_duration(audio_path)

        # Step 1: Diarization (if enabled)
        speaker_segments: list[SpeakerSegment] = []
        if enable_diarization:
            try:
                speaker_segments = DiarizationService.diarize(
                    audio_path=audio_path,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                )
            except Exception as e:
                # Graceful degradation: continue without diarization
                logger.warning(
                    "Diarization failed, continuing without speaker labels",
                    error=str(e),
                )

        # Step 2: Transcription
        transcription_result = TranscriptionService.transcribe(
            audio_path=audio_path,
            language=language,
            word_timestamps=word_timestamps,
        )

        words: list[Word] = transcription_result["words"]

        # Step 3: Align words with speakers
        aligned_words = align_words_with_speakers(words, speaker_segments)

        # Step 4: Merge into speaker segments
        segments = merge_words_into_segments(aligned_words)

        # Get unique speakers
        speakers = sorted(set(seg.speaker for seg in segments))

        logger.info(
            "Pipeline completed",
            audio_path=str(audio_path),
            duration_seconds=duration,
            speaker_count=len(speakers),
            segment_count=len(segments),
            word_count=len(words),
        )

        return PipelineResult(
            text=transcription_result["text"],
            language=transcription_result.get("language"),
            duration_seconds=duration,
            speakers=speakers,
            segments=segments,
            words=aligned_words,
        )


def process_audio(
    audio_path: str | Path,
    language: str | None = None,
    enable_diarization: bool = True,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    word_timestamps: bool = True,
) -> PipelineResult:
    """Convenience function for the pipeline."""
    return TranscriptionPipeline.process(
        audio_path=audio_path,
        language=language,
        enable_diarization=enable_diarization,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
        word_timestamps=word_timestamps,
    )
