from app.services.artifacts import to_srt_timestamp, to_vtt_timestamp


def test_srt_timestamp_format():
    assert to_srt_timestamp(65.432) == "00:01:05,432"


def test_vtt_timestamp_format():
    assert to_vtt_timestamp(65.432) == "00:01:05.432"
