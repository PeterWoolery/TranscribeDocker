import importlib
import sys
import types
from pathlib import Path

import pytest


class FakeDownloadError(Exception):
    pass


class FakeYoutubeDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def download(self, urls):
        output = Path(self.options["outtmpl"].replace("%(ext)s", "mp4"))
        output.write_bytes(b"media")


def load_downloader_module(monkeypatch):
    monkeypatch.syspath_prepend("backend")
    monkeypatch.setitem(sys.modules, "yt_dlp", types.SimpleNamespace(YoutubeDL=FakeYoutubeDL))
    monkeypatch.setitem(sys.modules, "yt_dlp.utils", types.SimpleNamespace(DownloadError=FakeDownloadError))
    sys.modules.pop("app.services.downloader", None)
    return importlib.import_module("app.services.downloader")


def test_direct_url_download_uses_stable_output_name(tmp_path, monkeypatch):
    downloader = load_downloader_module(monkeypatch)
    seen = {}

    def fake_ydl(options):
        assert "cookiefile" not in options
        seen["outtmpl"] = options["outtmpl"]
        return FakeYoutubeDL(options)

    monkeypatch.setattr(downloader, "YoutubeDL", fake_ydl)

    url = (
        "https://example.com/"
        "cccv-245639-15810-textbook-chapter-16.mp4"
        "?expires=1774049914&signature="
        + ("a" * 600)
    )

    result = downloader.download_from_url(url, tmp_path)

    assert seen["outtmpl"] == str(tmp_path / "source.%(ext)s")
    assert result == tmp_path / "source.mp4"


@pytest.mark.parametrize("extension", ["m4a", "webm"])
def test_youtube_download_selects_audio_and_returns_selected_file(tmp_path, monkeypatch, extension):
    downloader = load_downloader_module(monkeypatch)
    url = "https://www.youtube.com/watch?v=ESr5vu4W1iA"

    class AudioYoutubeDL(FakeYoutubeDL):
        def extract_info(self, source_url, download):
            assert source_url == url
            assert download is True
            assert self.options["format"] == "bestaudio/best"
            assert self.options["noplaylist"] is True
            assert not self.options.get("no_warnings", False)
            assert "merge_output_format" not in self.options
            info = {"ext": extension}
            Path(self.prepare_filename(info)).write_bytes(b"audio")
            return info

        def prepare_filename(self, info):
            return self.options["outtmpl"].replace("%(ext)s", info["ext"])

    monkeypatch.setattr(downloader, "YoutubeDL", AudioYoutubeDL)

    result = downloader.download_from_url(url, tmp_path)

    assert result == tmp_path / f"source.{extension}"
    assert result.read_bytes() == b"audio"


def test_youtube_extraction_error_is_preserved(tmp_path, monkeypatch):
    downloader = load_downloader_module(monkeypatch)

    class FailingYoutubeDL(FakeYoutubeDL):
        def extract_info(self, source_url, download):
            raise RuntimeError("The page needs to be reloaded.")

    monkeypatch.setattr(downloader, "YoutubeDL", FailingYoutubeDL)

    with pytest.raises(RuntimeError, match="The page needs to be reloaded"):
        downloader.download_from_url("https://youtu.be/ESr5vu4W1iA", tmp_path)


COOKIE_EXPORT = (
    "# Netscape HTTP Cookie File\n"
    "#HttpOnly_lectures.example.edu\tFALSE\t/\tTRUE\t0\tsession\tprivate-test-value\n"
)


@pytest.mark.parametrize("youtube", [False, True])
def test_cookie_copy_is_private_writable_and_removed(tmp_path, monkeypatch, youtube):
    downloader = load_downloader_module(monkeypatch)
    source = tmp_path / "session.txt"
    source.write_text(COOKIE_EXPORT)
    source.chmod(0o400)
    job_dir = tmp_path / "job"
    seen = []

    class CookieYoutubeDL(FakeYoutubeDL):
        def __enter__(self):
            cookie = Path(self.options["cookiefile"])
            seen.append(cookie)
            assert cookie != source
            assert not cookie.is_relative_to(job_dir)
            assert cookie.stat().st_mode & 0o777 == 0o600
            assert cookie.parent.stat().st_mode & 0o777 == 0o700
            assert cookie.read_text() == COOKIE_EXPORT
            return self

        def __exit__(self, *args):
            # Real yt-dlp saves its cookie jar when the context exits.
            seen[-1].write_text("updated session")
            return False

        def extract_info(self, url, download):
            self.download([url])
            return {}

        def prepare_filename(self, info):
            return self.options["outtmpl"].replace("%(ext)s", "mp4")

    monkeypatch.setattr(downloader, "YoutubeDL", CookieYoutubeDL)
    url = "https://youtu.be/example" if youtube else "https://lectures.example.edu/Panopto/Pages/Viewer.aspx?id=example"
    result = downloader.download_from_url(url, job_dir, cookie_file=str(source))

    assert result == job_dir / "source.mp4"
    assert sorted(p.name for p in job_dir.iterdir()) == ["source.mp4"]
    assert source.read_text() == COOKIE_EXPORT
    assert not seen[0].parent.exists()


@pytest.mark.parametrize("invalid", ["missing", "directory", "empty", "header", "columns", "expiry", "boolean", "domain", "comments", "oversize"])
def test_invalid_cookie_file_fails_without_leaking_contents(tmp_path, monkeypatch, capsys, invalid):
    downloader = load_downloader_module(monkeypatch)
    source = tmp_path / "session.txt"
    if invalid == "directory":
        source.mkdir()
    elif invalid != "missing":
        contents = {
            "empty": "",
            "header": "private-test-value\n",
            "columns": "# Netscape HTTP Cookie File\nprivate-test-value\n",
            "expiry": COOKIE_EXPORT.replace("\t0\t", "\tprivate-test-value\t"),
            "boolean": COOKIE_EXPORT.replace("\tFALSE\t", "\tprivate-test-value\t"),
            "domain": COOKIE_EXPORT.replace("#HttpOnly_lectures", "#HttpOnly_.lectures"),
            "comments": "# Netscape HTTP Cookie File\n# private-test-value\n",
            "oversize": "# Netscape HTTP Cookie File\n#" + "private-test-value" * 70_000,
        }
        source.write_text(contents[invalid])

    def unexpected_download(options):
        pytest.fail("Invalid cookies must fail before constructing YoutubeDL")

    monkeypatch.setattr(downloader, "YoutubeDL", unexpected_download)
    with pytest.raises(RuntimeError, match="YTDLP_COOKIE_FILE") as error:
        downloader.download_from_url("https://lectures.example.edu/video", tmp_path / "job", cookie_file=str(source))
    assert "private-test-value" not in str(error.value)
    assert error.value.__suppress_context__
    captured = capsys.readouterr()
    assert "private-test-value" not in captured.out + captured.err


def test_unreadable_cookie_file_fails_closed(tmp_path, monkeypatch):
    downloader = load_downloader_module(monkeypatch)
    source = tmp_path / "session.txt"
    source.write_text(COOKIE_EXPORT)
    original_open = Path.open

    def denied(path, *args, **kwargs):
        if path == source:
            raise PermissionError("private-test-value")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", denied)
    with pytest.raises(RuntimeError, match="YTDLP_COOKIE_FILE") as error:
        downloader.download_from_url("https://example.com/video", tmp_path / "job", cookie_file=str(source))
    assert "private-test-value" not in str(error.value)


@pytest.mark.parametrize("message", ["only available for registered users. Use --cookies-from-browser or --cookies", "network unavailable", "save failed"])
def test_cookie_copy_cleanup_on_download_error(tmp_path, monkeypatch, message):
    downloader = load_downloader_module(monkeypatch)
    source = tmp_path / "session.txt"
    source.write_text(COOKIE_EXPORT)
    seen = []

    class FailingYoutubeDL(FakeYoutubeDL):
        def download(self, urls):
            seen.append(Path(self.options["cookiefile"]))
            if message == "save failed":
                return super().download(urls)
            raise FakeDownloadError(message)

        def __exit__(self, *args):
            if message == "save failed":
                raise FakeDownloadError(message)
            return False

    monkeypatch.setattr(downloader, "YoutubeDL", FailingYoutubeDL)
    expected = RuntimeError if "registered users" in message else FakeDownloadError
    with pytest.raises(expected) as error:
        downloader.download_from_url("https://lectures.example.edu/video", tmp_path / "job", cookie_file=str(source))
    if expected is RuntimeError:
        assert "refresh" in str(error.value).lower()
        assert "YTDLP_COOKIE_FILE" in str(error.value)
    else:
        assert str(error.value) == message
    assert not seen[0].parent.exists()
    assert source.read_text() == COOKIE_EXPORT


def test_overlapping_downloads_use_separate_cookie_copies(tmp_path, monkeypatch):
    downloader = load_downloader_module(monkeypatch)
    source = tmp_path / "session.txt"
    source.write_text(COOKIE_EXPORT)
    seen = []

    class OverlappingYoutubeDL(FakeYoutubeDL):
        def download(self, urls):
            cookie = Path(self.options["cookiefile"])
            seen.append(cookie)
            if len(seen) == 1:
                downloader.download_from_url("https://example.com/second", tmp_path / "second", cookie_file=str(source))
                assert cookie.exists()
                assert not seen[1].exists()
            super().download(urls)

    monkeypatch.setattr(downloader, "YoutubeDL", OverlappingYoutubeDL)
    downloader.download_from_url("https://example.com/first", tmp_path / "first", cookie_file=str(source))
    assert seen[0] != seen[1]
    assert all(not cookie.parent.exists() for cookie in seen)


def test_authentication_failure_without_cookie_configuration_is_actionable(tmp_path, monkeypatch):
    downloader = load_downloader_module(monkeypatch)

    class LoginRequiredYoutubeDL(FakeYoutubeDL):
        def download(self, urls):
            raise FakeDownloadError("only available for registered users. Use --cookies-from-browser or --cookies")

    monkeypatch.setattr(downloader, "YoutubeDL", LoginRequiredYoutubeDL)
    with pytest.raises(RuntimeError, match="YTDLP_COOKIE_FILE.*docker-compose.cookies.yml"):
        downloader.download_from_url("https://lectures.example.edu/video", tmp_path)
