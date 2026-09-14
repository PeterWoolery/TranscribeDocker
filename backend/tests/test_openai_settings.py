import importlib
import sys
import types


def load_transcription_module(monkeypatch):
    monkeypatch.syspath_prepend("backend")
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=object))
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=object))
    monkeypatch.setitem(
        sys.modules,
        "app.core.config",
        types.SimpleNamespace(
            settings=types.SimpleNamespace(
                default_compute_device="cpu",
                openai_api_key=None,
                openai_transcribe_model="gpt-4o-transcribe",
                openai_translate_model="gpt-4o-mini-transcribe",
            )
        ),
    )
    sys.modules.pop("app.services.transcription", None)
    return importlib.import_module("app.services.transcription")


def test_resolve_openai_api_key_prefers_per_job_value(monkeypatch):
    transcription = load_transcription_module(monkeypatch)
    monkeypatch.setattr(transcription.settings, "openai_api_key", "server-key")

    resolved = transcription.resolve_openai_api_key({"openai_api_key": " job-key "})

    assert resolved == "job-key"


def test_resolve_openai_api_key_falls_back_to_server_setting(monkeypatch):
    transcription = load_transcription_module(monkeypatch)
    monkeypatch.setattr(transcription.settings, "openai_api_key", "server-key")

    resolved = transcription.resolve_openai_api_key({"openai_api_key": "   "})

    assert resolved == "server-key"


def test_run_transcription_retries_local_with_vad_disabled(monkeypatch):
    transcription = load_transcription_module(monkeypatch)
    calls = []

    def fake_local(media_path, task, language, model_size, advanced, progress_callback=None):
        calls.append(dict(advanced))
        return [] if advanced.get("vad_filter", True) else [{"start": 0.0, "end": 1.0, "text": "hello"}]

    monkeypatch.setattr(transcription, "transcribe_local", fake_local)

    resolved = transcription.run_transcription(
        media_path=None,
        task="transcribe",
        language="auto",
        engine_mode="local",
        model="medium",
        advanced={"vad_filter": True},
    )

    assert resolved == [{"start": 0.0, "end": 1.0, "text": "hello"}]
    assert calls == [{"vad_filter": True}, {"vad_filter": False}]


def test_run_transcription_falls_back_to_openai_after_empty_local_result(monkeypatch):
    transcription = load_transcription_module(monkeypatch)

    def fake_local(media_path, task, language, model_size, advanced, progress_callback=None):
        return []

    def fake_openai(media_path, task, language, advanced=None):
        return [{"start": 0.0, "end": 1.0, "text": "fallback"}]

    monkeypatch.setattr(transcription, "transcribe_local", fake_local)
    monkeypatch.setattr(transcription, "transcribe_openai", fake_openai)

    resolved = transcription.run_transcription(
        media_path=None,
        task="transcribe",
        language="auto",
        engine_mode="auto_fallback",
        model="medium",
        advanced={"vad_filter": True},
    )

    assert resolved == [{"start": 0.0, "end": 1.0, "text": "fallback"}]


def test_run_transcription_raises_on_empty_openai_result(monkeypatch):
    transcription = load_transcription_module(monkeypatch)
    monkeypatch.setattr(transcription, "transcribe_openai", lambda *args, **kwargs: [])

    try:
        transcription.run_transcription(
            media_path=None,
            task="transcribe",
            language="auto",
            engine_mode="openai_api",
            model="medium",
            advanced={},
        )
    except transcription.EmptyTranscriptionError as exc:
        assert "OpenAI transcription produced no speech segments" in str(exc)
    else:
        raise AssertionError("Expected EmptyTranscriptionError")
