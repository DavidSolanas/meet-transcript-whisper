"""Output formatters for SRT, VTT, and other formats."""

from src.core.models import TranscriptSegment


def _format_timestamp_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_timestamp_vtt(seconds: float) -> str:
    """Format seconds as VTT timestamp (HH:MM:SS.mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def format_srt(segments: list[TranscriptSegment], include_speaker: bool = True) -> str:
    """
    Format transcript segments as SRT subtitle format.

    Args:
        segments: List of transcript segments
        include_speaker: Whether to prefix text with speaker label

    Returns:
        SRT formatted string
    """
    lines: list[str] = []

    for i, segment in enumerate(segments, start=1):
        # Sequence number
        lines.append(str(i))

        # Timestamps
        start_ts = _format_timestamp_srt(segment.start)
        end_ts = _format_timestamp_srt(segment.end)
        lines.append(f"{start_ts} --> {end_ts}")

        # Text with optional speaker label
        if include_speaker:
            lines.append(f"[{segment.speaker}] {segment.text}")
        else:
            lines.append(segment.text)

        # Blank line between entries
        lines.append("")

    return "\n".join(lines)


def format_vtt(segments: list[TranscriptSegment], include_speaker: bool = True) -> str:
    """
    Format transcript segments as WebVTT subtitle format.

    Args:
        segments: List of transcript segments
        include_speaker: Whether to prefix text with speaker label

    Returns:
        VTT formatted string
    """
    lines: list[str] = ["WEBVTT", ""]

    for segment in segments:
        # Timestamps
        start_ts = _format_timestamp_vtt(segment.start)
        end_ts = _format_timestamp_vtt(segment.end)
        lines.append(f"{start_ts} --> {end_ts}")

        # Text with optional speaker label using VTT voice tag
        if include_speaker:
            lines.append(f"<v {segment.speaker}>{segment.text}")
        else:
            lines.append(segment.text)

        # Blank line between entries
        lines.append("")

    return "\n".join(lines)


def format_json(
    segments: list[TranscriptSegment],
    duration_seconds: float,
    language: str | None,
    speakers: list[str],
) -> dict:
    """
    Format transcript as a JSON-serializable dictionary.

    Args:
        segments: List of transcript segments
        duration_seconds: Total audio duration
        language: Detected/specified language
        speakers: List of unique speakers

    Returns:
        Dictionary ready for JSON serialization
    """
    return {
        "duration_seconds": duration_seconds,
        "language": language,
        "speakers": speakers,
        "segments": [
            {
                "speaker": seg.speaker,
                "start": seg.start,
                "end": seg.end,
                "text": seg.text,
                "words": (
                    [
                        {
                            "text": w.text,
                            "start": w.start,
                            "end": w.end,
                            "confidence": w.confidence,
                        }
                        for w in seg.words
                    ]
                    if seg.words
                    else None
                ),
            }
            for seg in segments
        ],
    }


def format_text(segments: list[TranscriptSegment], include_timestamps: bool = False) -> str:
    """
    Format transcript as plain text.

    Args:
        segments: List of transcript segments
        include_timestamps: Whether to include timestamps

    Returns:
        Plain text transcript
    """
    lines: list[str] = []

    for segment in segments:
        if include_timestamps:
            # Format: [00:00:00] SPEAKER: text
            minutes = int(segment.start // 60)
            seconds = int(segment.start % 60)
            lines.append(f"[{minutes:02d}:{seconds:02d}] {segment.speaker}: {segment.text}")
        else:
            lines.append(f"{segment.speaker}: {segment.text}")

    return "\n".join(lines)
