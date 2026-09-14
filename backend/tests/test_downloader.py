import importlib
import sys
import types
from pathlib import Path

import pytest


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
    sys.modules.pop("app.services.downloader", None)
    return importlib.import_module("app.services.downloader")


def test_direct_url_download_uses_stable_output_name(tmp_path, monkeypatch):
    downloader = load_downloader_module(monkeypatch)
    seen = {}

    def fake_ydl(options):
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
