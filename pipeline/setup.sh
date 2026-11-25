#!/usr/bin/env bash
# One-time setup for a fresh session (each scheduled run starts in a new cloud sandbox).
# Installs the Python packages and downloads the open Kokoro TTS model (~120 MB) from GitHub releases.
set -euo pipefail
pip install --break-system-packages -q kokoro-onnx soundfile num2words 2>&1 | grep -v -i warning || true
K="${KOKORO_DIR:-$HOME/.cache/kokoro}"
mkdir -p "$K"
BASE=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
for f in kokoro-v1.0.int8.onnx voices-v1.0.bin; do
  [ -s "$K/$f" ] || curl -sSL --retry 3 --max-time 600 -o "$K/$f" "$BASE/$f"
done
ls -la "$K"
for t in ffmpeg ffprobe; do command -v $t >/dev/null || { echo "missing $t"; exit 1; }; done
python3 -c "import PIL, numpy, kokoro_onnx, num2words; print('setup ok')"
