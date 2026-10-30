from __future__ import annotations

import shutil
import tempfile
import warnings
from contextlib import contextmanager
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Iterator

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


MAX_COOKIE_BYTES = 1_048_576


@contextmanager
def _private_cookie_file(cookie_file: str | None) -> Iterator[str | None]:
    if not cookie_file:
        yield None
        return

    try:
        source = Path(cookie_file)
        if not source.is_file():
            raise ValueError("Not a regular file")
        with source.open("rb") as stream:
            content = stream.read(MAX_COOKIE_BYTES + 1)
        if not content or len(content) > MAX_COOKIE_BYTES:
            raise ValueError("Invalid size")
    except (OSError, ValueError):
        raise RuntimeError(
            "YTDLP_COOKIE_FILE must be a readable, nonempty regular cookie file of at most 1 MiB."
        ) from None

    # yt-dlp writes its jar on close: never give it the read-only mounted source.
    # TemporaryDirectory/NamedTemporaryFile create private 0700/0600 paths outside job output.
    with tempfile.TemporaryDirectory(prefix="transcribedocker-cookies-") as directory:
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".txt", delete=False) as stream:
            stream.write(content)
            private_path = stream.name
        try:
            for line in content.decode("utf-8").splitlines():
                if not line.strip() or (line.startswith("#") and not line.startswith("#HttpOnly_")):
                    continue
                fields = line.removeprefix("#HttpOnly_").split("\t")
                if (
                    len(fields) != 7
                    or fields[1] not in {"TRUE", "FALSE"}
                    or fields[3] not in {"TRUE", "FALSE"}
                    or (fields[4] and (not fields[4].isascii() or not fields[4].isdigit()))
                ):
                    raise ValueError("Invalid Netscape cookie fields")
            jar = MozillaCookieJar(private_path)
            # The stdlib parser can include a malformed cookie line in a warning.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                jar.load(ignore_discard=True, ignore_expires=True)
            if not jar:
                raise ValueError("No cookies")
        except (OSError, ValueError):
            raise RuntimeError(
                "YTDLP_COOKIE_FILE must contain a valid Netscape cookie export with at least one cookie. "
                "Export your authorized browser session again."
            ) from None
        yield private_path


def download_from_url(url: str, job_dir: Path, cookie_file: str | None = None) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)

    youtube = "youtube.com" in url or "youtu.be" in url
    ydl_opts = {"outtmpl": str(job_dir / "source.%(ext)s"), "quiet": True}
    if youtube:
        ydl_opts.update({"noplaylist": True, "format": "bestaudio/best"})
    else:
        ydl_opts["no_warnings"] = True

    with _private_cookie_file(cookie_file) as private_cookie_file:
        if private_cookie_file:
            ydl_opts["cookiefile"] = private_cookie_file
        try:
            with YoutubeDL(ydl_opts) as ydl:
                if youtube:
                    info = ydl.extract_info(url, download=True)
                    file_path = Path(ydl.prepare_filename(info))
                    if file_path.exists():
                        return file_path
                    raise RuntimeError("YouTube download failed")
                ydl.download([url])
        except DownloadError as exc:
            message = str(exc).lower()
            if any(hint in message for hint in ("registered users", "--cookies", "login required")):
                raise RuntimeError(
                    "Authentication required. Configure YTDLP_COOKIE_FILE using docker-compose.cookies.yml, "
                    "or refresh the cookie export from a browser session that can play this video. "
                    "Recreate the worker after replacing the export and submit a new job. "
                    "Your session must have permission to access the video."
                ) from None
            raise

    files = [p for p in job_dir.iterdir() if p.is_file()]
    if not files:
        raise RuntimeError("Direct URL download failed")
    return max(files, key=lambda p: p.stat().st_size)


def copy_upload_to_job(upload_path: Path, job_dir: Path) -> Path:
    job_dir.mkdir(parents=True, exist_ok=True)
    dest = job_dir / upload_path.name
    shutil.copy2(upload_path, dest)
    return dest
