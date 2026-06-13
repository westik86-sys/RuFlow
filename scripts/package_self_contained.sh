#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONFIGURATION="${CONFIGURATION:-Release}"
SCHEME="${SCHEME:-RuFlow}"
PROJECT="${PROJECT:-RuFlow.xcodeproj}"
PYTHON="${PYTHON:-asr/.venv/bin/python}"
MODEL_SOURCE="${RUFLOW_MODEL_SOURCE:-$HOME/.cache/huggingface/hub/models--istupakov--gigaam-v3-onnx/snapshots/322c3b29492673eb7d0b434bfa9dfb8653e34d02}"
MODEL_NAME="${RUFLOW_MODEL_NAME:-gigaam-v3-e2e-rnnt}"
STAMP="$(date +%Y%m%d-%H%M%S)"
DIST_DIR="$ROOT_DIR/dist/RuFlow-self-contained-$STAMP"
DIST_APP="$DIST_DIR/RuFlow.app"
PYINSTALLER_CONFIG_DIR="$ROOT_DIR/build/pyinstaller-config"
SIDECAR_DIST="$ROOT_DIR/build/asr-dist/runner"
DERIVED_DATA_PATH="$ROOT_DIR/build/DerivedData"
BUILD_SETTINGS_FILE="$(mktemp)"

cleanup() {
  rm -f "$BUILD_SETTINGS_FILE"
}
trap cleanup EXIT

if [[ ! -x "$PYTHON" ]]; then
  echo "Python runtime not found: $PYTHON" >&2
  exit 1
fi

if [[ ! -d "$MODEL_SOURCE" ]]; then
  echo "Model snapshot not found: $MODEL_SOURCE" >&2
  echo "Set RUFLOW_MODEL_SOURCE=/path/to/model_snapshot and rerun." >&2
  exit 1
fi

echo "Building ASR sidecar..."
env PYINSTALLER_CONFIG_DIR="$PYINSTALLER_CONFIG_DIR" "$PYTHON" -m PyInstaller \
  --clean \
  --noconfirm \
  --name runner \
  --distpath build/asr-dist \
  --workpath build/asr-build \
  --specpath build/asr-spec \
  --copy-metadata onnx-asr \
  --copy-metadata onnxruntime \
  --collect-data onnx_asr \
  asr/runner.py

echo "Building $SCHEME ($CONFIGURATION)..."
xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -derivedDataPath "$DERIVED_DATA_PATH" \
  -destination "platform=macOS" \
  build

xcodebuild \
  -project "$PROJECT" \
  -scheme "$SCHEME" \
  -configuration "$CONFIGURATION" \
  -derivedDataPath "$DERIVED_DATA_PATH" \
  -showBuildSettings > "$BUILD_SETTINGS_FILE"

TARGET_BUILD_DIR="$(awk -F' = ' '/^[[:space:]]*TARGET_BUILD_DIR = / { print $2; exit }' "$BUILD_SETTINGS_FILE")"
FULL_PRODUCT_NAME="$(awk -F' = ' '/^[[:space:]]*FULL_PRODUCT_NAME = / { print $2; exit }' "$BUILD_SETTINGS_FILE")"
SOURCE_APP="$TARGET_BUILD_DIR/$FULL_PRODUCT_NAME"

if [[ ! -d "$SOURCE_APP" ]]; then
  echo "Built app not found: $SOURCE_APP" >&2
  exit 1
fi

echo "Creating self-contained bundle..."
mkdir -p "$DIST_DIR"
ditto --noqtn "$SOURCE_APP" "$DIST_APP"

ASR_RESOURCES="$DIST_APP/Contents/Resources/asr"
mkdir -p "$ASR_RESOURCES/sidecar" "$ASR_RESOURCES/models/$MODEL_NAME"
ditto --noqtn "$SIDECAR_DIST" "$ASR_RESOURCES/sidecar"

# Hugging Face snapshots are usually symlink forests. Dereference them so the
# app can be moved to another Mac without the original cache directory.
cp -RL "$MODEL_SOURCE"/. "$ASR_RESOURCES/models/$MODEL_NAME"/
chmod +x "$ASR_RESOURCES/sidecar/runner"

echo "Signing bundle..."
codesign --force --deep --sign - "$DIST_APP"

ZIP_PATH="$DIST_DIR/RuFlow-self-contained.zip"
ditto -c -k --sequesterRsrc --keepParent "$DIST_APP" "$ZIP_PATH"

echo "Done:"
echo "  App: $DIST_APP"
echo "  Zip: $ZIP_PATH"
du -sh "$DIST_APP" "$ZIP_PATH"
