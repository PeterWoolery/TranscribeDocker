import hashlib
import importlib
import io
import json
import sys
import types
from pathlib import Path

import pytest

from test_openai_settings import load_transcription_module


@pytest.fixture
def backend(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend("backend")
    monkeypatch.setitem(sys.modules, "app.core.config", types.SimpleNamespace(
        settings=types.SimpleNamespace(whisper_cpp_model_dir=str(tmp_path / "models")),
    ))
    sys.modules.pop("app.services.whisper_cpp", None)
    return importlib.import_module("app.services.whisper_cpp")


@pytest.fixture
def cli(backend, monkeypatch, tmp_path):
    state = types.SimpleNamespace(
        lines="whisper_backend_init_gpu: using Vulkan0 backend\n"
              "whisper_backend_init_gpu: no GPU found\n"
              "[00:00:01.250 --> 00:00:02.500]  hello\n",
        payload={"transcription": [{"offsets": {"from": 1250, "to": 2500}, "text": " hello "}]},
        returncode=0, killed=False, downloads=[], commands=[],
    )
    monkeypatch.setattr(backend.shutil, "which", lambda name: "/usr/local/bin/whisper-cli")

    def download(*args):
        state.downloads.append(args)
        return tmp_path / args[0]

    def convert(command, **kwargs):
        state.commands.append(command)
        return types.SimpleNamespace(returncode=0, stderr="")

    class Process:
        def __init__(self, command, **kwargs):
            state.commands.append(command)
            self.stdout = io.StringIO(state.lines)
            if state.payload is not None:
                Path(command[command.index("--output-file") + 1] + ".json").write_text(json.dumps(state.payload))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stdout.close()

        def wait(self):
            return state.returncode

        def kill(self):
            state.killed = True

    monkeypatch.setattr(backend, "download_model", download)
    monkeypatch.setattr(backend.subprocess, "run", convert)
    monkeypatch.setattr(backend.subprocess, "Popen", Process)
    return state


@pytest.mark.parametrize("task,vad", [("transcribe", False), ("translate", True)])
def test_cli_arguments_timestamps_progress_and_cleanup(backend, cli, tmp_path, task, vad):
    progress = []
    media = tmp_path / "input with spaces.mp4"
    result = backend.transcribe_vulkan(media, task, "auto", "medium", {
        "vad_filter": vad, "beam_size": 3, "best_of": 2, "temperature": 0.2,
    }, progress.append)

    assert result == [{"start": 1.25, "end": 2.5, "text": "hello"}]
    assert progress == [2.5]
    conversion, command = cli.commands
    assert conversion[conversion.index("-i") + 1] == str(media)
    assert conversion[conversion.index("-ar") + 1] == "16000"
    assert conversion[conversion.index("-ac") + 1] == "1"
    assert conversion[conversion.index("-c:a") + 1] == "pcm_s16le"
    assert ("--translate" in command) == (task == "translate")
    assert ("--vad" in command) == vad
    assert command[command.index("--language") + 1] == "auto"
    assert command[command.index("--beam-size") + 1] == "3"
    assert command[command.index("--best-of") + 1] == "2"
    assert command[command.index("--temperature") + 1] == "0.2"
    assert len(cli.downloads) == (2 if vad else 1)
    assert not list(tmp_path.glob("whisper-cpp-*"))
    assert not cli.killed


@pytest.mark.parametrize("lines,returncode,error", [
    ("whisper_backend_init_gpu: no GPU found\n", 0, "Vulkan GPU initialization failed"),
    ("whisper_backend_init_gpu: using Vulkan0 backend\n"
     "whisper_backend_init_gpu: failed to initialize Vulkan0 backend\n", 0, "Vulkan GPU initialization failed"),
    ("some unexpected output\n", 0, "refusing silent CPU fallback"),
    ("out of memory\n", 1, "out of memory"),
])
def test_cli_failure_is_reported(backend, cli, tmp_path, lines, returncode, error):
    cli.lines, cli.returncode = lines, returncode
    with pytest.raises(RuntimeError, match=error):
        backend.transcribe_vulkan(tmp_path / "input.wav", "transcribe", "en", "tiny", {})
    assert cli.killed == ("Vulkan GPU initialization failed" in error)
    assert not list(tmp_path.glob("whisper-cpp-*"))


def test_callback_failure_stops_subprocess(backend, cli, tmp_path):
    def fail(_):
        raise RuntimeError("callback failed")

    with pytest.raises(RuntimeError, match="callback failed"):
        backend.transcribe_vulkan(tmp_path / "input.wav", "transcribe", "en", "tiny", {}, fail)
    assert cli.killed
    assert not list(tmp_path.glob("whisper-cpp-*"))


def test_ffmpeg_failure_is_reported(backend, cli, monkeypatch, tmp_path):
    monkeypatch.setattr(backend.subprocess, "run", lambda *a, **kw: types.SimpleNamespace(
        returncode=1, stderr="invalid media",
    ))
    with pytest.raises(RuntimeError, match="Audio conversion failed: invalid media"):
        backend.transcribe_vulkan(tmp_path / "input.mp4", "transcribe", "auto", "tiny", {})
    assert not cli.commands
    assert not list(tmp_path.glob("whisper-cpp-*"))


def test_missing_binary_explains_required_overlay(backend, monkeypatch, tmp_path):
    monkeypatch.setattr(backend.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="docker-compose.amd.yml"):
        backend.transcribe_vulkan(tmp_path / "input.wav", "transcribe", "en", "tiny", {})


def test_model_path_traversal_rejected_before_download(backend, cli, tmp_path):
    with pytest.raises(ValueError, match="Unsupported whisper.cpp model"):
        backend.transcribe_vulkan(tmp_path / "input.wav", "transcribe", "en", "../../outside", {})
    assert cli.downloads == []


@pytest.mark.parametrize("corrupt", [False, True])
def test_download_checksum_atomic_cache_and_cleanup(backend, monkeypatch, tmp_path, corrupt):
    contents = b"model content"
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield contents

    def get(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr(backend.requests, "get", get)
    checksum = "bad" if corrupt else hashlib.sha256(contents).hexdigest()
    args = ("ggml-tiny.bin", "ggerganov/whisper.cpp", backend.MODEL_REVISION, checksum)
    if corrupt:
        with pytest.raises(RuntimeError, match="Checksum mismatch"):
            backend.download_model(*args)
        assert not (tmp_path / "models" / "ggml-tiny.bin").exists()
    else:
        downloaded = backend.download_model(*args)
        assert downloaded.read_bytes() == contents
        assert backend.download_model(*args) == downloaded
    assert len(calls) == 1
    assert not list((tmp_path / "models").glob("*.part"))


@pytest.mark.parametrize("engine", ["local", "auto_fallback"])
def test_amd_routing_preserves_vad_retry(monkeypatch, engine):
    transcription = load_transcription_module(monkeypatch)
    calls = []

    def vulkan(media, task, language, model, advanced, progress_callback=None):
        calls.append(advanced["vad_filter"])
        return [] if advanced["vad_filter"] else [{"start": 0, "end": 1, "text": "hello"}]

    monkeypatch.setitem(sys.modules, "app.services.whisper_cpp", types.SimpleNamespace(transcribe_vulkan=vulkan))
    result = transcription.run_transcription(None, "transcribe", "auto", engine, "tiny", {
        "compute_device": "amd_vulkan", "vad_filter": True,
    })
    assert result[0]["text"] == "hello"
    assert calls == [True, False]


def test_amd_failure_uses_existing_openai_fallback(monkeypatch):
    transcription = load_transcription_module(monkeypatch)
    fallback = []

    def vulkan(*args):
        raise RuntimeError("GPU unavailable")

    monkeypatch.setitem(sys.modules, "app.services.whisper_cpp", types.SimpleNamespace(transcribe_vulkan=vulkan))
    monkeypatch.setattr(transcription, "transcribe_openai", lambda *a, **kw: [{"text": "cloud"}])
    assert transcription.run_transcription(None, "transcribe", "auto", "auto_fallback", "tiny", {
        "compute_device": "amd_vulkan",
    }, fallback_callback=lambda: fallback.append(True)) == [{"text": "cloud"}]
    assert fallback == [True]


@pytest.mark.parametrize("device,expected", [("cpu", "cpu"), ("nvidia_gpu", "cuda")])
def test_existing_devices_still_use_faster_whisper(monkeypatch, device, expected):
    transcription = load_transcription_module(monkeypatch)
    calls = []

    class Model:
        def __init__(self, **kwargs):
            calls.append(kwargs)

        def transcribe(self, *args, **kwargs):
            return [types.SimpleNamespace(start=0, end=1, text=" hello ")], None

    monkeypatch.setattr(transcription, "WhisperModel", Model)
    assert transcription.transcribe_local(None, "transcribe", "en", "tiny", {"compute_device": device}) == [
        {"start": 0.0, "end": 1.0, "text": "hello"},
    ]
    assert calls[0]["device"] == expected
