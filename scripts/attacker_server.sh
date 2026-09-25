#!/usr/bin/env bash
# Serve the shared attacker model with llama.cpp's llama-server (OpenAI-compatible, port 8093).
#   ATTACKER_GGUF=/path/to/model.gguf scripts/attacker_server.sh
#
# Why not plain Ollama: the benchmark's attacker (an abliterated Qwen3.6-35B-A3B, a hybrid
# attention/recurrent MoE) crashed Ollama's runner with "CUDA error: an illegal memory access" each
# time a context checkpoint was created on NVIDIA Thor. The same weights under llama-server with
# context checkpoints disabled ran thousands of requests without a crash.
#
#   LLAMA_SERVER      llama-server binary built with CUDA for your GPU (Ollama bundles one)
#   GGML_BACKEND_PATH its CUDA backend library, when it lives outside the binary's directory
set -euo pipefail
: "${ATTACKER_GGUF:?path to the attacker model GGUF}"
LLAMA_SERVER="${LLAMA_SERVER:-/usr/local/lib/ollama/llama-server}"
export GGML_BACKEND_PATH="${GGML_BACKEND_PATH:-/usr/local/lib/ollama/cuda_v13/libggml-cuda.so}"
export LD_LIBRARY_PATH="$(dirname "$GGML_BACKEND_PATH"):$(dirname "$LLAMA_SERVER"):${LD_LIBRARY_PATH:-}"
exec "$LLAMA_SERVER" -m "$ATTACKER_GGUF" --host 127.0.0.1 --port "${ATTACKER_PORT:-8093}" \
  -ngl 99 -c 65536 -np 4 --ctx-checkpoints 0 --reasoning off -fa on --alias attacker --no-webui
