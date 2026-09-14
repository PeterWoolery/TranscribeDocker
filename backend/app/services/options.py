from app.schemas.options import OptionItem, OptionResponse
from app.core.config import settings

CORE_OPTIONS = [
    OptionItem(
        key="task",
        label="Task",
        type="select",
        default="transcribe",
        choices=["transcribe", "translate"],
        help="Transcribe in original language or translate to English.",
    ),
    OptionItem(
        key="language",
        label="Language",
        type="text",
        default="auto",
        help="Use auto or an ISO language code like en/es/fr.",
    ),
    OptionItem(
        key="model",
        label="Model",
        type="select",
        default="medium",
        choices=["tiny", "base", "small", "medium", "large-v3"],
        help="Whisper model for local inference.",
    ),
    OptionItem(
        key="engine_mode",
        label="Engine Mode",
        type="select",
        default="auto_fallback",
        choices=["local", "openai_api", "auto_fallback"],
        help="Use local inference, OpenAI API, or automatic fallback.",
    ),
    OptionItem(
        key="compute_device",
        label="Compute Device",
        type="select",
        default=settings.default_compute_device,
        choices=["cpu", "nvidia_gpu", "amd_vulkan"],
        help="CPU, NVIDIA CUDA, or AMD Vulkan. GPU devices require their matching Compose overlay.",
    ),
]

ADVANCED_OPTIONS = [
    OptionItem(
        key="openai_api_key",
        label="OpenAI API Key",
        type="password",
        default=None,
        help="Optional per-job key for OpenAI mode or fallback when no server key is configured.",
    ),
    OptionItem(key="beam_size", label="Beam Size", type="number", default=5, min=1, max=12, help="Decoder beam size."),
    OptionItem(key="best_of", label="Best Of", type="number", default=5, min=1, max=12, help="Number of candidates sampled."),
    OptionItem(key="temperature", label="Temperature", type="number", default=0, min=0, max=1, help="Sampling temperature."),
    OptionItem(key="vad_filter", label="VAD Filter", type="boolean", default=True, help="Enable voice activity detection."),
    OptionItem(key="compute_type", label="Compute Type", type="select", default="int8", choices=["int8", "float16", "float32"], help="CPU/NVIDIA inference precision. AMD Vulkan uses GGML model precision instead."),
    OptionItem(key="diarization", label="Speaker Diarization", type="boolean", default=False, help="Identify speaker turns with pyannote pipeline."),
    OptionItem(key="diarization_min_speakers", label="Min Speakers", type="number", default=None, min=1, max=20, help="Lower bound for speaker count."),
    OptionItem(key="diarization_max_speakers", label="Max Speakers", type="number", default=None, min=1, max=20, help="Upper bound for speaker count."),
]


def get_options() -> OptionResponse:
    return OptionResponse(core=CORE_OPTIONS, advanced=ADVANCED_OPTIONS)
