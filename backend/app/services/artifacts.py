from __future__ import annotations

import json
from pathlib import Path


def to_srt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def to_vtt_timestamp(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


def format_timestamped_transcript(segments: list[dict]) -> str:
    lines = []
    for seg in segments:
        lines.append(f"[{to_vtt_timestamp(seg['start'])}] {seg['text'].strip()}")
    return "\n".join(lines)


def write_outputs(base_dir: Path, base_name: str, segments: list[dict], formats: list[str]) -> list[Path]:
    base_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []

    if "txt" in formats:
        txt_path = base_dir / f"{base_name}.txt"
        txt_path.write_text(format_timestamped_transcript(segments), encoding="utf-8")
        files.append(txt_path)

    if "json" in formats:
        json_path = base_dir / f"{base_name}.json"
        json_path.write_text(json.dumps({"segments": segments}, indent=2), encoding="utf-8")
        files.append(json_path)

    if "srt" in formats:
        srt_lines = []
        for idx, seg in enumerate(segments, start=1):
            srt_lines.append(str(idx))
            srt_lines.append(f"{to_srt_timestamp(seg['start'])} --> {to_srt_timestamp(seg['end'])}")
            srt_lines.append(seg["text"].strip())
            srt_lines.append("")
        srt_path = base_dir / f"{base_name}.srt"
        srt_path.write_text("\n".join(srt_lines), encoding="utf-8")
        files.append(srt_path)

    if "vtt" in formats:
        vtt_lines = ["WEBVTT", ""]
        for seg in segments:
            vtt_lines.append(f"{to_vtt_timestamp(seg['start'])} --> {to_vtt_timestamp(seg['end'])}")
            vtt_lines.append(seg["text"].strip())
            vtt_lines.append("")
        vtt_path = base_dir / f"{base_name}.vtt"
        vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")
        files.append(vtt_path)

    return files
