import os
from pathlib import Path
import subprocess

import pytest


ENTRYPOINT = Path(__file__).resolve().parents[1] / "entrypoint.sh"


def run_entrypoint(tmp_path, update=None, update_exit=0):
    # Stub the network operation while exercising the real shell entrypoint.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    timeout = bin_dir / "timeout"
    timeout.write_text(
        '#!/bin/sh\n'
        'printf "%s\\n" "$@" > "$CALL_LOG"\n'
        'printf "%s\\n" "private-index-credential" >&2\n'
        'exit "$UPDATE_EXIT"\n'
    )
    timeout.chmod(0o755)
    python = bin_dir / "python"
    python.write_text('#!/bin/sh\nprintf "%s\\n" "test-yt-dlp-version"\n')
    python.chmod(0o755)
    env = dict(os.environ)
    env.pop("UPDATE_YTDLP_ON_START", None)
    env.update(
        PATH=f"{bin_dir}:{env['PATH']}",
        CALL_LOG=str(tmp_path / "calls"),
        UPDATE_EXIT=str(update_exit),
    )
    if update is not None:
        env["UPDATE_YTDLP_ON_START"] = update
    result = subprocess.run(
        ["sh", str(ENTRYPOINT), "sh", "-c", 'printf "worker started: %s\\n" "$1"; exit 7', "sh", "argument with spaces"],
        env=env, capture_output=True, text=True, timeout=5,
    )
    return result, tmp_path / "calls"


@pytest.mark.parametrize("update", [None, "false", "0"])
def test_update_disabled_executes_original_command(tmp_path, update):
    result, calls = run_entrypoint(tmp_path, update)
    assert not calls.exists()
    assert result.returncode == 7
    assert result.stdout == "worker started: argument with spaces\n"


@pytest.mark.parametrize("update", ["true", "1"])
def test_update_uses_extras_and_bounded_network_before_worker(tmp_path, update):
    result, calls = run_entrypoint(tmp_path, update)
    args = calls.read_text().splitlines()
    assert args[:5] == ["120s", "python", "-m", "pip", "install"]
    assert args[-5:] == ["--retries", "1", "--timeout", "15", "yt-dlp[default,deno]"]
    assert "--upgrade" in args
    assert result.returncode == 7
    assert "test-yt-dlp-version\nworker started" in result.stdout
    assert "private-index-credential" not in result.stdout + result.stderr


@pytest.mark.parametrize("update_exit", [1, 124])
def test_update_failure_or_timeout_warns_and_starts_worker(tmp_path, update_exit):
    result, _ = run_entrypoint(tmp_path, "true", update_exit)
    assert result.returncode == 7
    assert "WARNING: yt-dlp update failed or timed out" in result.stderr
    assert "worker started" in result.stdout
    assert "private-index-credential" not in result.stdout + result.stderr


def test_invalid_update_setting_fails_clearly(tmp_path):
    result, calls = run_entrypoint(tmp_path, "typo")
    assert result.returncode == 2
    assert not calls.exists()
    assert "must be true, false, 1, or 0" in result.stderr
    assert "worker started" not in result.stdout
