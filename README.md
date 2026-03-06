# TranscribeDocker

Transcribe audio/video from file uploads or URLs (YouTube + direct links) with a Dockerized web app built on FastAPI, Celery, and Whisper-compatible transcription.

## Highlights
- Upload files or submit URLs.
- Queue-based asynchronous processing.
- Timestamped outputs: `TXT`, `SRT`, `VTT`, `JSON`.
- Detailed live progress:
  - stage-based statuses (`downloading`, `transcribing`, `finalizing`)
  - in-media position (`00:12 / 03:45`) when available
  - ETA estimate for local transcription jobs
- CPU/NVIDIA GPU compute device selection from the UI.
- Optional OpenAI fallback mode.
- Auto cleanup of source media + retention policy for artifacts.

## Architecture
- `frontend`: React + Vite SPA
- `gateway`: Nginx reverse proxy
- `api`: FastAPI REST API
- `worker`: Celery worker for transcription pipeline
- `beat`: Celery beat for scheduled cleanup
- `redis`: broker/result backend
- `postgres`: metadata store

## Repository Layout
- `backend/`: FastAPI app, worker logic, transcription services
- `frontend/`: React app
- `infra/nginx/`: gateway config
- `docs/`: implementation notes
- `docker-compose.yml`: default stack (CPU-first)
- `docker-compose.gpu.yml`: NVIDIA GPU overlay

## Requirements
- Docker + Docker Compose
- For GPU mode: NVIDIA driver + NVIDIA Container Toolkit

## Quick Start (CPU)
1. Copy environment template:
   ```bash
   cp .env.example .env
   ```
2. Start stack:
   ```bash
   docker compose up --build
   ```
3. Open:
   - App: `http://localhost:8081`
   - API docs: `http://localhost:8081/docs`

## Quick Start (NVIDIA GPU)
1. Ensure host GPU stack is ready (`nvidia-smi` works on host).
2. Launch with GPU override:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
   ```
3. In the app, set `Compute Device` to `nvidia_gpu` for jobs you want on GPU.

## Environment Variables
Configured in `.env` and Compose:
- `OPENAI_API_KEY`: required for `openai_api` mode and fallback-to-OpenAI
- `HF_TOKEN`: optional; reserved for diarization integrations
- `DEFAULT_COMPUTE_DEVICE`: `cpu` or `nvidia_gpu` (default: `cpu`)
- `DEFAULT_ENGINE_MODE`: `local`, `openai_api`, or `auto_fallback`
- `MAX_UPLOAD_BYTES`: max upload size in bytes (default `2147483648`)
- `JOB_RETENTION_DAYS`: transcript metadata/artifact retention window

## API Overview
Base path: `/api/v1`
- `POST /jobs` - create transcription job (multipart)
- `GET /jobs/{job_id}` - job status + progress + artifacts
- `GET /jobs/{job_id}/artifacts` - artifact list
- `GET /jobs/{job_id}/artifacts/{artifact_id}/download` - download artifact
- `DELETE /jobs/{job_id}` - delete job and artifacts
- `GET /options` - UI option catalog
- `GET /health` - service health

### Job Progress Fields
`GET /jobs/{job_id}` includes:
- `status`: coarse lifecycle status
- `stage`: detailed pipeline stage
- `status_detail`: user-facing status message
- `progress_percent`: normalized 0-100 progress
- `current_time_sec`: current transcription media position (local mode)
- `duration_sec`: total media duration when detected
- `eta_seconds`: estimated time remaining (local mode when calculable)

## CPU / GPU Toggle Behavior
- The UI exposes `Compute Device` with:
  - `cpu`
  - `nvidia_gpu`
- Device selection is sent per job and applied by the worker at runtime.
- If GPU is selected but not available in container runtime, local transcription may fail and fallback may be used based on engine mode.

## Progress & ETA Notes
- URL/download and output generation use stage-based progress.
- Precise `time/duration` + ETA are available for local transcription when:
  - media duration can be probed
  - segment callbacks are emitted
- OpenAI mode provides descriptive stage progress but no stream-level in-media cursor.

## Running Updates
When changing backend schema fields, restart services so startup idempotent `ALTER TABLE` patches run:
```bash
docker compose up --build
```

## Troubleshooting
- Worker fails importing libraries:
  - rebuild image: `docker compose build --no-cache api worker beat`
- Slow local transcription:
  - use smaller model or GPU mode
- No ETA displayed:
  - duration probe failed or engine mode does not provide incremental segment progress
- OpenAI mode errors:
  - verify `OPENAI_API_KEY`

## Development Notes
- Startup currently uses `Base.metadata.create_all` plus idempotent SQL `ALTER TABLE` patches.
- For production hardening, migrate to Alembic-managed schema migrations.

## License
Add your preferred license file before publishing publicly.
