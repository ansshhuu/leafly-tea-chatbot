#!/bin/bash
# Downloads the self-hosted Whisper-WASM model files (Xenova/whisper-tiny.en)
# into frontend/public/models/ - this folder is gitignored (~43MB of binary
# weights have no business in git history), so every fresh clone/install
# needs to pull them once. Runs automatically via `npm install`'s
# postinstall hook (see frontend/package.json); safe to re-run manually.
#
# The two .onnx files here are specifically the ones transformers.js v2
# requests by default (quantized=true, seq2seq encoder + merged decoder) -
# see node_modules/@xenova/transformers/src/models.js. The HF repo also
# hosts ~10 other unused ONNX variants (fp16, int8, bnb4, q4, ...); don't
# add those, they'd just bloat every install.
set -euo pipefail

MODEL_ID="Xenova/whisper-tiny.en"
BASE_URL="https://huggingface.co/${MODEL_ID}/resolve/main"
DEST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/frontend/public/models/${MODEL_ID}"

CONFIG_FILES=(
  config.json
  generation_config.json
  preprocessor_config.json
  tokenizer.json
  tokenizer_config.json
  vocab.json
  merges.txt
  normalizer.json
  added_tokens.json
  special_tokens_map.json
)
ONNX_FILES=(
  onnx/encoder_model_quantized.onnx
  onnx/decoder_model_merged_quantized.onnx
)

mkdir -p "$DEST/onnx"

fetch_file() {
  local rel_path="$1"
  local dest_path="$DEST/$rel_path"
  if [ -s "$dest_path" ]; then
    echo "[fetch-models] already present, skipping: $rel_path"
    return 0
  fi
  echo "[fetch-models] downloading: $rel_path"
  if ! curl -fL --retry 3 -o "$dest_path" "$BASE_URL/$rel_path"; then
    echo "[fetch-models] FAILED to download: $rel_path" >&2
    rm -f "$dest_path"
    return 1
  fi
}

status=0
for f in "${CONFIG_FILES[@]}" "${ONNX_FILES[@]}"; do
  fetch_file "$f" || status=1
done

if [ "$status" -ne 0 ]; then
  echo "[fetch-models] one or more files failed to download - voice input's Whisper fallback will break until this is re-run successfully." >&2
  exit 1
fi

echo "[fetch-models] all model files present under $DEST"
