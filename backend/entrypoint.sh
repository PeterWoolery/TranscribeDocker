#!/bin/sh
set -eu

case "${UPDATE_YTDLP_ON_START:-false}" in
    true|1)
        printf '%s\n' 'Checking for yt-dlp, EJS, and Deno updates (up to 120 seconds)...'
        # Keep package-index/proxy credentials out of container logs.
        if timeout 120s python -m pip install --disable-pip-version-check --no-input \
            --no-cache-dir --upgrade --upgrade-strategy only-if-needed \
            --retries 1 --timeout 15 'yt-dlp[default,deno]' >/dev/null 2>&1; then
            printf '%s\n' 'yt-dlp update check completed.'
        else
            printf '%s\n' 'WARNING: yt-dlp update failed or timed out; continuing with installed packages.' >&2
        fi
        python -m yt_dlp --version
        ;;
    false|0) ;;
    *)
        printf '%s\n' 'UPDATE_YTDLP_ON_START must be true, false, 1, or 0.' >&2
        exit 2
        ;;
esac

exec "$@"
