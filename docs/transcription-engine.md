# Transcription Engine Notes

## Current implementation
- Primary runtime path: local `faster-whisper` in worker container.
- Fallback path: OpenAI Audio API when `engine_mode=auto_fallback` and local inference fails.

## Planned transcribe-anything pinning
The codebase uses an adapter-style `run_transcription(...)` service so the backend can be switched to a pinned `transcribe-anything` commit without API changes.

During next integration pass:
1. Select upstream repository + exact commit SHA.
2. Freeze supported options in this document.
3. Map the allowlisted API options to pinned engine flags.
4. Add compatibility tests for that pinned version.
