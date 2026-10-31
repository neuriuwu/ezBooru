#!/bin/bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PROJECT_ROOT}/.venv/bin/python"
ICONSET="${PROJECT_ROOT}/build/ezBooru.iconset"
SOURCE_ICON="${PROJECT_ROOT}/assets/ezBooru.png"

if [[ ! -x "${PYTHON}" ]]; then
    echo "Project virtual environment not found. Create it with: python3 -m venv .venv" >&2
    exit 1
fi

if ! command -v sips >/dev/null || ! command -v iconutil >/dev/null; then
    echo "macOS sips and iconutil are required to create the app icon." >&2
    exit 1
fi

cd "${PROJECT_ROOT}"
"${PYTHON}" -m pip install -e ".[build]"
mkdir -p "${ICONSET}"

for size in 16 32 64 128 256 512; do
    sips -z "${size}" "${size}" "${SOURCE_ICON}" \
        --out "${ICONSET}/icon_${size}x${size}.png" >/dev/null
done
for size in 16 32 64 128 256; do
    doubled=$((size * 2))
    sips -z "${doubled}" "${doubled}" "${SOURCE_ICON}" \
        --out "${ICONSET}/icon_${size}x${size}@2x.png" >/dev/null
done
sips -z 1024 1024 "${SOURCE_ICON}" \
    --out "${ICONSET}/icon_512x512@2x.png" >/dev/null
iconutil -c icns "${ICONSET}" -o "${PROJECT_ROOT}/assets/ezBooru.icns"

"${PYTHON}" -m PyInstaller \
    --clean \
    --noconfirm \
    --windowed \
    --name ezBooru \
    --icon "${PROJECT_ROOT}/assets/ezBooru.icns" \
    --add-data "${SOURCE_ICON}:assets" \
    --collect-all qasync \
    "${PROJECT_ROOT}/ezbooru/main.py"

echo "macOS app bundle created: ${PROJECT_ROOT}/dist/ezBooru.app"
