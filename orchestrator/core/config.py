import os
from dataclasses import dataclass

from core.schemas import Budgets


@dataclass(frozen=True)
class Config:
    oracle_mode: str
    local_llm_base_url: str
    local_llm_model: str
    remote_llm_base_url: str
    remote_llm_model: str
    fireworks_api_key: str
    hf_token: str
    github_token: str
    gpu_arch: str
    max_iterations: int
    max_attempts_per_group: int
    max_errors_parsed: int
    confidence_threshold: float
    price_h100_hr: float
    price_mi300x_hr: float
    # Umbrales de estancamiento del loop (§6.4). Con default para no romper
    # construcciones existentes de Config (aditivo, INV-8 safe).
    stagnation_force_remote: int = 3   # builds sin mejorar → forzar tier remoto
    stagnation_exit: int = 5           # builds sin mejorar → salida honesta DONE_PARTIAL
    # Precio del tier remoto (USD por millón de tokens) para el costo del
    # reporte/dashboard. F-17: el número se calcula acá, nunca en el frontend.
    remote_price_per_mtok: float = 3.0


def _getenv_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def _getenv_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def _getenv_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return float(raw)


def get_config() -> Config:
    return Config(
        oracle_mode=_getenv_str("ORACLE_MODE", "mock"),
        local_llm_base_url=_getenv_str("LOCAL_LLM_BASE_URL", "http://vllm:8000/v1"),
        local_llm_model=_getenv_str("LOCAL_LLM_MODEL", "google/gemma-3-27b-it"),
        remote_llm_base_url=_getenv_str(
            "REMOTE_LLM_BASE_URL", "https://api.fireworks.ai/inference/v1"
        ),
        remote_llm_model=_getenv_str("REMOTE_LLM_MODEL", ""),
        fireworks_api_key=_getenv_str("FIREWORKS_API_KEY", ""),
        hf_token=_getenv_str("HF_TOKEN", ""),
        github_token=_getenv_str("GITHUB_TOKEN", ""),
        gpu_arch=_getenv_str("GPU_ARCH", "gfx942"),
        max_iterations=_getenv_int("MAX_ITERATIONS", 25),
        max_attempts_per_group=_getenv_int("MAX_ATTEMPTS_PER_GROUP", 3),
        max_errors_parsed=_getenv_int("MAX_ERRORS_PARSED", 30),
        stagnation_force_remote=_getenv_int("STAGNATION_FORCE_REMOTE", 3),
        stagnation_exit=_getenv_int("STAGNATION_EXIT", 5),
        confidence_threshold=_getenv_float("CONFIDENCE_THRESHOLD", 0.6),
        price_h100_hr=_getenv_float("PRICE_H100_HR", 0.0),
        price_mi300x_hr=_getenv_float("PRICE_MI300X_HR", 0.0),
        remote_price_per_mtok=_getenv_float("REMOTE_PRICE_PER_MTOK", 3.0),
    )


def budgets(config: Config | None = None) -> Budgets:
    cfg = config if config is not None else get_config()
    return Budgets(
        max_iterations=cfg.max_iterations,
        max_attempts_per_group=cfg.max_attempts_per_group,
        max_errors_parsed=cfg.max_errors_parsed,
    )
