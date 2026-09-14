from app.services.artifacts import format_timestamped_transcript, to_srt_timestamp, to_vtt_timestamp, write_outputs


def test_srt_timestamp_format():
    assert to_srt_timestamp(65.432) == "00:01:05,432"


def test_vtt_timestamp_format():
    assert to_vtt_timestamp(65.432) == "00:01:05.432"


def test_timestamped_transcript_format():
    segments = [
        {"start": 0.0, "end": 1.2, "text": " Hello world "},
        {"start": 65.432, "end": 70.0, "text": "Second line"},
    ]

    assert format_timestamped_transcript(segments) == (
        "[00:00:00.000] Hello world\n"
        "[00:01:05.432] Second line"
    )


def test_write_outputs_txt_includes_timestamps(tmp_path):
    segments = [
        {"start": 5.25, "end": 8.0, "text": " Example line "},
    ]

    paths = write_outputs(tmp_path, "sample", segments, ["txt"])

    assert len(paths) == 1
    assert paths[0].read_text(encoding="utf-8") == "[00:00:05.250] Example line"
