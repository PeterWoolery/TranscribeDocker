from __future__ import annotations

import shutil
from pathlib import Path

from slugify import slugify
from yt_dlp import YoutubeDL


def download_from_url(url: str, job_dir: Path) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)

    if "youtube.com" in url or "youtu.be" in url:
        outtmpl = str(job_dir / "source.%(ext)s")
        ydl_opts = {
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = Path(ydl.prepare_filename(info))
            if file_path.exists():
                return file_path
            if (job_dir / "source.mp4").exists():
                return job_dir / "source.mp4"
            raise RuntimeError("YouTube download failed")

    safe_name = slugify(Path(url).name) or "source"
    output = job_dir / safe_name
    with YoutubeDL({"outtmpl": str(output), "quiet": True, "no_warnings": True}) as ydl:
        ydl.download([url])

    if output.exists():
        return output

    files = [p for p in job_dir.iterdir() if p.is_file()]
    if not files:
        raise RuntimeError("Direct URL download failed")
    return max(files, key=lambda p: p.stat().st_size)


def copy_upload_to_job(upload_path: Path, job_dir: Path) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / upload_path.name
    shutil.copy2(upload_path, dest)
    return dest
