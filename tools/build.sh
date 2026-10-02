#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly WORKSPACE_DIR="$(cd "${PROJECT_DIR}/../.." && pwd)"
readonly BUILD_DIR="${PROJECT_DIR}/build"
readonly BOARD="${BOARD:-rpi_pico2/rp2350a/m33/w}"
readonly SNIPPET="${SNIPPET:-cdc-acm-console}"

pristine="auto"
si5351_hardware="no"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --pristine)
            pristine="always"
            shift
            ;;
        --si5351-hardware)
            si5351_hardware="yes"
            shift
            ;;
        -h|--help)
            echo "Usage: tools/build.sh [--pristine] [--si5351-hardware]"
            echo "Default: incremental build with SI5351 mock backend."
            echo "--pristine forces a complete rebuild."
            echo "--si5351-hardware enables the real software-I2C driver."
            exit 0
            ;;
        *)
            break
            ;;
    esac
done

if command -v west >/dev/null 2>&1; then
    WEST="$(command -v west)"
elif [[ -x "${WORKSPACE_DIR}/.venv/bin/west" ]]; then
    WEST="${WORKSPACE_DIR}/.venv/bin/west"
else
    echo "Fehler: west nicht gefunden. Aktiviere ${WORKSPACE_DIR}/.venv." >&2
    exit 1
fi

echo "Project:  ${PROJECT_DIR}"
echo "Build:    ${BUILD_DIR}"
echo "Mode:     $([[ "${pristine}" == "always" ]] && echo pristine || echo incremental)"

extra_cmake=()
if [[ "${si5351_hardware}" == "yes" ]]; then
    extra_cmake=(-- "-DEXTRA_CONF_FILE=conf/network.conf;conf/http-support.conf;conf/http.conf;conf/wifi.conf;conf/si5351-hardware.conf")
    echo "SI5351:   hardware"
else
    echo "SI5351:   mock"
fi

exec "${WEST}" build \
    -p "${pristine}" \
    -d "${BUILD_DIR}" \
    -b "${BOARD}" \
    "${PROJECT_DIR}" \
    --snippet "${SNIPPET}" \
    "${extra_cmake[@]}" \
    "$@"
