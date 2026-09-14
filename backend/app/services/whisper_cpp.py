from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Callable

import requests

from app.core.config import settings


logger = logging.getLogger(__name__)
MODEL_REVISION = "5359861c739e955e79d9a303bcbc70fb988958b1"
MODEL_HASHES = {
    "tiny": "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
    "base": "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
    "small": "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b",
    "medium": "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208",
    "large-v3": "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2",
}
VAD_REVISION = "9ffd54a1e1ee413ddf265af9913beaf518d1639b"
VAD_FILE = "ggml-silero-v6.2.0.bin"
VAD_HASH = "2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987"


def download_model(filename: str, repository: str, revision: str, expected_hash: str) -> Path:
    directory = Path(settings.whisper_cpp_model_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / filename
    if destination.is_file():
        return destination

    logger.info("Downloading whisper.cpp model %s (cached after first use)", filename)
    temporary = None
    try:
        with NamedTemporaryFile(dir=directory, suffix=".part", delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            url = f"https://huggingface.co/{repository}/resolve/{revision}/{filename}"
            with requests.get(url, stream=True, timeout=(15, 120)) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    output.write(chunk)
                    digest.update(chunk)
        if digest.hexdigest() != expected_hash:
            raise RuntimeError(f"Checksum mismatch downloading whisper.cpp model {filename}")
        # Never expose a partial download to another job or a restarted worker.
        temporary.replace(destination)
        return destination
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def transcribe_vulkan(
    media_path: Path,
    task: str,
    language: str,
    model_size: str,
    advanced: dict,
    progress_callback: Callable[[float], None] | None = None,
) -> list[dict]:
    binary = shutil.which("whisper-cli")
    if binary is None:
        raise RuntimeError("amd_vulkan requires the docker-compose.amd.yml worker image (whisper-cli missing)")
    if model_size not in MODEL_HASHES:
        raise ValueError(f"Unsupported whisper.cpp model: {model_size}")
    if task not in {"transcribe", "translate"}:
        raise ValueError(f"Unsupported whisper.cpp task: {task}")

    model = download_model(f"ggml-{model_size}.bin", "ggerganov/whisper.cpp", MODEL_REVISION, MODEL_HASHES[model_size])
    vad_model = None
    if bool(advanced.get("vad_filter", True)):
        vad_model = download_model(VAD_FILE, "ggml-org/whisper-vad", VAD_REVISION, VAD_HASH)

    with TemporaryDirectory(prefix="whisper-cpp-", dir=media_path.parent) as temporary:
        directory = Path(temporary)
        audio = directory / "audio.wav"
        converted = subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(media_path),
             "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(audio)],
            capture_output=True, text=True,
        )
        if converted.returncode:
            raise RuntimeError(f"Audio conversion failed: {converted.stderr[-2000:]}")

        command = [
            binary, "--model", str(model), "--file", str(audio),
            "--language", language, "--output-json", "--output-file", str(directory / "transcript"),
            "--beam-size", str(int(advanced.get("beam_size", 5))),
            "--best-of", str(int(advanced.get("best_of", 5))),
            "--temperature", str(float(advanced.get("temperature", 0.0))),
        ]
        if task == "translate":
            command.append("--translate")
        if vad_model is not None:
            command.extend(["--vad", "--vad-model", str(vad_model)])

        recent_output: deque[str] = deque(maxlen=20)
        gpu_selected = False
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1) as process:
            try:
                for line in process.stdout:
                    recent_output.append(line.rstrip()[-500:])
                    if "whisper_backend_init_gpu: using Vulkan" in line:
                        gpu_selected = True
                        logger.info("%s", line.strip())
                    # Silero VAD intentionally initializes a separate CPU backend after Whisper.
                    if ("whisper_backend_init_gpu: no GPU found" in line and not gpu_selected) or (
                        "whisper_backend_init_gpu: failed to initialize" in line
                    ):
                        raise RuntimeError("Vulkan GPU initialization failed; check /dev/dri access and the Mesa RADV driver")
                    match = re.match(r"^\[\d+:\d+:\d+\.\d+ --> (\d+):(\d+):(\d+\.\d+)\]", line)
                    if match and progress_callback:
                        hours, minutes, seconds = map(float, match.groups())
                        progress_callback(hours * 3600 + minutes * 60 + seconds)
                returncode = process.wait()
            except BaseException:
                process.kill()
                process.wait()
                raise
        if returncode:
            raise RuntimeError(f"whisper.cpp exited with code {returncode}: " + "\n".join(recent_output))
        if not gpu_selected:
            raise RuntimeError("whisper.cpp did not confirm a Vulkan GPU backend; refusing silent CPU fallback")

        payload = json.loads((directory / "transcript.json").read_text(encoding="utf-8"))
        return [
            {"start": float(segment["offsets"]["from"]) / 1000,
             "end": float(segment["offsets"]["to"]) / 1000,
             "text": segment["text"].strip()}
            for segment in payload["transcription"]
        ]
