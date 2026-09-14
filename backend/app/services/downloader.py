from __future__ import annotations

import shutil
from pathlib import Path
from yt_dlp import YoutubeDL


def download_from_url(url: str, job_dir: Path) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)

    if "youtube.com" in url or "youtu.be" in url:
        outtmpl = str(job_dir / "source.%(ext)s")
        ydl_opts = {
            "outtmpl": outtmpl,
            "quiet": True,
            "noplaylist": True,
            "format": "bestaudio/best",
        }
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = Path(ydl.prepare_filename(info))
            if file_path.exists():
                return file_path
            raise RuntimeError("YouTube download failed")

    output = job_dir / "source.%(ext)s"
    with YoutubeDL({"outtmpl": str(output), "quiet": True, "no_warnings": True}) as ydl:
        ydl.download([url])

    files = [p for p in job_dir.iterdir() if p.is_file()]
    if not files:
        raise RuntimeError("Direct URL download failed")
    return max(files, key=lambda p: p.stat().st_size)


def copy_upload_to_job(upload_path: Path, job_dir: Path) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / upload_path.name
    shutil.copy2(upload_path, dest)
    return dest
