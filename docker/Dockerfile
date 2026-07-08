# Dockerfile — imagen del perfil `gpu` (droplet MI300X). Blueprint §1/§2.
# Base ROCm oficial; los builds del repo objetivo corren por subprocess DENTRO de
# este contenedor (hipcc/make), sin docker-in-docker. NO se compila vLLM acá (F-01):
# vLLM corre en su propio contenedor con la imagen oficial rocm/vllm.
#
# NOTA (M0): esta imagen requiere una máquina con ROCm (el droplet). No se valida en
# la máquina de desarrollo sin GPU — se prueba en el smoke test M0 (humano).
FROM rocm/dev-ubuntu-22.04:6.4

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    GPU_ARCH=gfx942

# Toolchain de porteo + utilidades. hipify-perl viene con ROCm; hipify-clang NO se
# instala (F-02: requiere headers CUDA inexistentes en AMD).
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.11 python3-pip git jq curl gh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY orchestrator/pyproject.toml /app/orchestrator/pyproject.toml
RUN pip3 install --no-cache-dir \
    "fastapi>=0.110" "uvicorn[standard]>=0.29" "pydantic>=2.6" \
    "httpx>=0.27" "jinja2>=3.1" "pyyaml>=6.0" "gitpython>=3.1"

COPY orchestrator /app/orchestrator
COPY dashboard /app/dashboard
COPY fixtures /app/fixtures

WORKDIR /app/orchestrator
EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
