# TranscribeDocker

Self-hosted audio/video transcription with a web interface. Upload a file or paste a YouTube/direct-media URL, then download timestamped **TXT, SRT, VTT, or JSON** transcripts.

- Local Whisper inference on CPU or AMD Vulkan, with optional OpenAI API/fallback modes.
- Background jobs with stage, transcript-position, and ETA updates when available.
- Automatic YouTube downloader updates at worker startup.
- AMD acceleration tested on native Linux with a **Radeon RX 6700 XT (12 GB)**.

## Before you start

Install Git, Docker Engine (or Docker Desktop for CPU use), and the Docker Compose plugin (`docker compose version`). Allow several GB of disk space for images and models. CPU inference can be slow; start with `base` or `small` on modest hardware.

**Use this application on a trusted network.** There is currently no login or per-user access control. The supplied Compose file publishes port **8081 on all host interfaces**. For host-only access, change its gateway port mapping to `127.0.0.1:8081:80`. Do not expose it directly to the public Internet; remote access needs an authenticated access layer and HTTPS.

## 1. Get the project

```bash
git clone https://github.com/PeterWoolery/TranscribeDocker.git
cd TranscribeDocker
cp .env.example .env
```

No API key is required for local transcription. Leave the key/token fields empty unless you need an external service. `.env` is ignored by Git; never commit it or paste it into issue reports.

## 2. Start an instance

### CPU (simplest setup)

```bash
docker compose up -d --build
docker compose logs --tail=100 worker
```

Open **http://localhost:8081** (or `http://YOUR_SERVER_IP:8081` from your trusted LAN). The first build and first model download can take several minutes.

### AMD Vulkan (native Linux, x86-64)

This worker uses [whisper.cpp](https://github.com/ggml-org/whisper.cpp) release `b4938`, pinned to its source commit, and Mesa RADV. It requires a working host AMD driver and `/dev/dri` render nodes. ROCm is not required. This deployment has been tested on the RX 6700 XT; other cards need their own verification.

1. Install your distribution's Vulkan tools and check that `vulkaninfo --summary` lists your Radeon rather than only a software renderer.
2. Build and start with the AMD overlay:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.amd.yml up -d --build
   ```

3. Check GPU access inside the worker:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.amd.yml exec worker vulkaninfo --summary
   ```

   Headless `DISPLAY`/`XDG_RUNTIME_DIR` warnings are harmless if the device section lists the Radeon through RADV.

4. Submit a short clip using **AMD Vulkan**, **local**, and **medium**, then check logs:

   ```bash
   docker compose -f docker-compose.yml -f docker-compose.amd.yml logs --tail=100 worker
   ```

   Look for `whisper_backend_init_gpu: using Vulkan0 backend` (the device number may differ). Missing GPU initialization fails local inference rather than silently running Whisper on CPU.

The overlay defaults new pages to `amd_vulkan` and runs one job at a time to limit VRAM contention. It passes `/dev/dri` through and selects the Radeon Vulkan driver. If you run the container as a non-root user, grant that user access to the host render nodes.

Models are downloaded from pinned Hugging Face revisions, SHA-256 checked, and cached in the `whisper_models` volume: **medium is about 1.5 GB**, **large-v3 about 3.1 GB**. Start with medium on a 12 GB card; test large-v3 if you need higher accuracy. The small Silero VAD model runs on CPU by design. The **Compute Type** option applies only to the faster-whisper CPU/NVIDIA backend; AMD uses the standard GGML model precision.

**Keep both `-f` arguments in AMD lifecycle commands.** Using only the base Compose file can recreate a CPU worker. To deliberately switch back, run `docker compose up -d --build` and select CPU for new jobs.

### NVIDIA status

The UI and `docker-compose.gpu.yml` provide NVIDIA device selection/passthrough, but the supplied Python image does **not** include all CUDA/cuDNN libraries required by faster-whisper. This is not a turnkey NVIDIA deployment. You must supply a compatible CUDA runtime image plus the host NVIDIA driver and Container Toolkit before using that overlay.

## 3. Transcribe your first file

1. Upload a short audio/video file, or submit a YouTube/direct-media URL.
2. Select **local** engine mode and the compute device matching your deployment.
3. Choose a model (`base`/`small` for an initial CPU test, `medium` for the tested AMD setup).
4. Leave language as `auto`, choose output formats, and submit.
5. Follow progress and download the completed artifacts.

YouTube jobs prefer audio-only downloads. First-time model downloads can make a job appear idle. URL downloads show stage progress; local transcription shows media position and ETA when available. OpenAI requests do not provide incremental segment progress.

## Configuration and secrets

The following `.env` variables are wired into Compose:

| Variable | Default / purpose |
| --- | --- |
| `DEFAULT_COMPUTE_DEVICE` | `cpu`; the AMD overlay overrides this with `amd_vulkan` |
| `UPDATE_YTDLP_ON_START` | `true`; check for downloader updates before the worker starts |
| `OPENAI_API_KEY` | Empty; worker key for OpenAI mode or automatic fallback |
| `HF_TOKEN` | Empty; reserved for optional diarization integration |

Other settings such as `MAX_UPLOAD_BYTES` (2 GiB), `JOB_RETENTION_DAYS` (30 days), and `DEFAULT_ENGINE_MODE` are currently set directly in `docker-compose.yml`; edit the relevant services there. Merely adding those names to `.env` does not override the hardcoded Compose values. The UI's initial engine choice is `auto_fallback`; choose `local` to ensure processing stays local.

- `auto_fallback` sends media to OpenAI if local inference fails and a key is available. API usage may incur charges. OpenAI has its own file-size/model/response-format limits; the app does not automatically split large uploads for it.
- Per-job API keys entered in the UI are masked in job responses but are stored in the database. Protect database backups and prefer the worker's environment key for a shared instance.
- Failed jobs may retain a downloadable copy of their source media for debugging. Treat artifact volumes and backups as private.
- Speaker-diarization controls are present, but the default image does not include a complete diarization setup.
- Docker environment inspection and rendered Compose configuration can expose configured secrets. Share only redacted diagnostic output.

## Updating yt-dlp (YouTube downloader)

YouTube changes frequently. The image includes a tested, pinned `yt-dlp` release plus its **EJS scripts and Deno JavaScript runtime**. By default, each worker container start checks the configured Python package index for a newer stable release using `python -m pip install --upgrade 'yt-dlp[default,deno]'` before starting Celery. Already-current packages are reused.

The check is limited to two minutes. If the package command fails or times out, a warning is logged and startup continues with installed packages. An unreachable index can also leave already-installed packages unchanged without an error exit, so a completed check does not guarantee you reached the index. The check runs only at startup, not during transcription. Updated packages live in that container's writable layer; recreating it starts from the image again and repeats the check. New releases are not necessarily tested with this app.

To trigger a check on an existing instance, wait for active jobs to finish, then restart the worker:

```bash
# CPU
docker compose restart worker

# AMD
docker compose -f docker-compose.yml -f docker-compose.amd.yml restart worker
```

Check the installed version with `docker compose exec worker python -m yt_dlp --version` (include the AMD `-f` arguments when applicable). The startup log also prints the version after its update attempt.

For reproducible or offline operation, set `UPDATE_YTDLP_ON_START=false` in `.env`, then **recreate** the worker with your usual `up -d --build` command. `restart` alone does not apply changed environment variables. To return to the image's pinned packages after a bad update, disable updates and use `up -d --build --force-recreate worker` with the appropriate Compose files.

To permanently update the image's baseline, change the `yt-dlp[default,deno]==...` version in `backend/requirements.txt` to a tested release and rebuild. Keep the extras: updating only the extractor without its JavaScript support can leave YouTube downloads broken. Retry failed downloads as **new jobs**; they are not automatically resubmitted.

## Updating and stopping the application

Wait for active jobs to finish before restarting workers. Pull the latest code, then rebuild/recreate:

```bash
git pull --ff-only

# CPU
docker compose up -d --build

# OR AMD
docker compose -f docker-compose.yml -f docker-compose.amd.yml up -d --build
```

Use `docker compose ps` to inspect services, `docker compose logs --tail=100 worker` for job errors, and `docker compose down` to stop the stack. Include both Compose files for AMD deployments.

Named volumes hold PostgreSQL metadata, artifacts, temporary uploads, and (on AMD) cached models. Normal container recreation and `down` preserve them. **`down -v` deletes those volumes and their data.** Back up the database and artifact volume together when jobs are idle; keep backups private. Redis queue state is not persisted in the supplied configuration, so stopping Redis can lose queued jobs. Startup applies the project's existing idempotent database schema patches.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| YouTube says “The page needs to be reloaded” | Restart the worker to check for updates, inspect its logs, and submit a new job. Restricted videos, bot checks, or network blocking may still prevent extraction. |
| Slow first job | Model download/initialization; later jobs reuse the AMD model cache. Try a smaller model for CPU. |
| AMD job fails | Check host/container `vulkaninfo`, render-node permissions, and the Vulkan initialization log. Use `local` during diagnosis so OpenAI fallback cannot hide the failure. |
| OpenAI errors | Check the key and provider model/file-format limits. Local mode does not need an API key. |
| No ETA | Duration probing or incremental segment progress may be unavailable for this job. |
| Cannot open the app | Run `docker compose ps` and check gateway/API logs, host firewall, and port 8081 availability. |

## Development and API

The stack consists of React/Vite (`frontend`), Nginx (`gateway`), FastAPI (`api`), Celery (`worker`/`beat`), Redis, and PostgreSQL. Source lives in `frontend/`, `backend/`, and `infra/nginx/`.

Interactive API documentation: **http://localhost:8081/docs**. API base: `/api/v1`.

- `POST /jobs`: submit multipart upload/URL and options
- `GET /jobs/{job_id}`: status, progress, and artifacts
- `GET /jobs/{job_id}/artifacts`: list artifacts
- `GET /jobs/{job_id}/artifacts/{artifact_id}/download`: download an artifact
- `DELETE /jobs/{job_id}`: delete a job and artifacts
- `GET /options`, `GET /health`: option catalog and health

Run backend unit tests with Python and pytest installed:

```bash
PYTHONPATH=backend python -m pytest backend/tests -q
```

## License

MIT. See [LICENSE](./LICENSE).
