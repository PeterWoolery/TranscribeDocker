from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from faster_whisper import WhisperModel
from openai import OpenAI

from app.core.config import settings


class EmptyTranscriptionError(RuntimeError):
    """Raised when a transcription engine returns no usable segments."""


def resolve_openai_api_key(advanced: dict | None) -> str | None:
    candidate = None if advanced is None else advanced.get("openai_api_key")
    if isinstance(candidate, str):
        candidate = candidate.strip()
    return candidate or settings.openai_api_key


def probe_duration_seconds(media_path: Path) -> float | None:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(media_path),
    ]
    try:
        proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
        payload = json.loads(proc.stdout)
        raw = payload.get("format", {}).get("duration")
        if raw is None:
            return None
        value = float(raw)
        return value if value > 0 else None
    except Exception:
        return None


def has_transcript_content(segments: list[dict]) -> bool:
    return any(str(seg.get("text", "")).strip() for seg in segments)


def transcribe_local(
    media_path: Path,
    task: str,
    language: str,
    model_size: str,
    advanced: dict,
    progress_callback: Callable[[float], None] | None = None,
) -> list[dict]:
    requested_device = str(advanced.get("compute_device", settings.default_compute_device)).lower()
    if requested_device == "amd_vulkan":
        from app.services.whisper_cpp import transcribe_vulkan

        return transcribe_vulkan(media_path, task, language, model_size, advanced, progress_callback)
    model_device = "cuda" if requested_device in {"cuda", "gpu", "nvidia_gpu"} else "cpu"

    model = WhisperModel(
        model_size_or_path=model_size,
        device=model_device,
        compute_type=str(advanced.get("compute_type", "int8")),
    )

    segments, _ = model.transcribe(
        str(media_path),
        task=task,
        language=None if language == "auto" else language,
        beam_size=int(advanced.get("beam_size", 5)),
        best_of=int(advanced.get("best_of", 5)),
        temperature=float(advanced.get("temperature", 0.0)),
        vad_filter=bool(advanced.get("vad_filter", True)),
    )

    output: list[dict] = []
    for seg in segments:
        end_sec = float(seg.end)
        output.append({"start": float(seg.start), "end": end_sec, "text": seg.text.strip()})
        if progress_callback:
            progress_callback(end_sec)
    return output


def transcribe_openai(media_path: Path, task: str, language: str, advanced: dict | None = None) -> list[dict]:
    api_key = resolve_openai_api_key(advanced)
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for openai_api engine mode")

    client = OpenAI(api_key=api_key)
    model_name = settings.openai_translate_model if task == "translate" else settings.openai_transcribe_model
    with media_path.open("rb") as media_file:
        transcript = client.audio.transcriptions.create(
            model=model_name,
            file=media_file,
            language=None if language == "auto" else language,
            response_format="verbose_json",
        )

    output = []
    for seg in transcript.segments or []:
        if isinstance(seg, dict):
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            text = seg.get("text", "")
        else:
            start = getattr(seg, "start", 0)
            end = getattr(seg, "end", 0)
            text = getattr(seg, "text", "")
        output.append({"start": float(start), "end": float(end), "text": str(text).strip()})
    if not output and getattr(transcript, "text", None):
        output.append({"start": 0.0, "end": 0.0, "text": transcript.text.strip()})
    return output


def transcribe_local_with_retry(
    media_path: Path,
    task: str,
    language: str,
    model_size: str,
    advanced: dict,
    progress_callback: Callable[[float], None] | None = None,
) -> list[dict]:
    segments = transcribe_local(media_path, task, language, model_size, advanced, progress_callback=progress_callback)
    if has_transcript_content(segments):
        return segments

    if not bool(advanced.get("vad_filter", True)):
        raise EmptyTranscriptionError("Local transcription produced no speech segments")

    retry_advanced = dict(advanced)
    retry_advanced["vad_filter"] = False
    retry_segments = transcribe_local(
        media_path,
        task,
        language,
        model_size,
        retry_advanced,
        progress_callback=progress_callback,
    )
    if has_transcript_content(retry_segments):
        return retry_segments
    raise EmptyTranscriptionError("Local transcription produced no speech segments, even with VAD disabled")


def run_transcription(
    media_path: Path,
    task: str,
    language: str,
    engine_mode: str,
    model: str | None,
    advanced: dict,
    progress_callback: Callable[[float], None] | None = None,
    fallback_callback: Callable[[], None] | None = None,
) -> list[dict]:
    local_model = model or "medium"

    if engine_mode == "local":
        return transcribe_local_with_retry(
            media_path,
            task,
            language,
            local_model,
            advanced,
            progress_callback=progress_callback,
        )

    if engine_mode == "openai_api":
        segments = transcribe_openai(media_path, task, language, advanced=advanced)
        if not has_transcript_content(segments):
            raise EmptyTranscriptionError("OpenAI transcription produced no speech segments")
        return segments

    if engine_mode == "auto_fallback":
        try:
            return transcribe_local_with_retry(
                media_path,
                task,
                language,
                local_model,
                advanced,
                progress_callback=progress_callback,
            )
        except Exception:
            if fallback_callback:
                fallback_callback()
            segments = transcribe_openai(media_path, task, language, advanced=advanced)
            if not has_transcript_content(segments):
                raise EmptyTranscriptionError("OpenAI fallback produced no speech segments")
            return segments

    raise RuntimeError(f"Unsupported engine_mode: {engine_mode}")
