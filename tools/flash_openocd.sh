#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly ZEPHYR_ROOT="${ZEPHYR_ROOT:-/home/ulrich/Dokumente/zephyrproject/zephyr}"
readonly OPENOCD_ROOT="${OPENOCD_ROOT:-/home/ulrich/.arduino15/packages/rp2040/tools/pqt-openocd/4.1.0-1aec55e}"
readonly OPENOCD="${OPENOCD_ROOT}/bin/openocd"
readonly OPENOCD_SCRIPTS="${OPENOCD_ROOT}/share/openocd/scripts"
readonly PICO2_SUPPORT="${ZEPHYR_ROOT}/boards/raspberrypi/rpi_pico2/support"
readonly FIRMWARE_HEX="${PROJECT_DIR}/build/zephyr/zephyr.hex"

if [[ ! -x "${OPENOCD}" ]]; then
    echo "Fehler: RP2350-OpenOCD nicht gefunden: ${OPENOCD}" >&2
    exit 1
fi

if [[ ! -f "${OPENOCD_SCRIPTS}/target/rp2350.cfg" ]]; then
    echo "Fehler: target/rp2350.cfg fehlt unter ${OPENOCD_SCRIPTS}" >&2
    exit 1
fi

if [[ ! -f "${FIRMWARE_HEX}" ]]; then
    echo "Fehler: Firmware nicht gefunden: ${FIRMWARE_HEX}" >&2
    echo "Zuerst das Projekt mit west build bauen." >&2
    exit 1
fi

echo "Flashe: ${FIRMWARE_HEX}"

exec "${OPENOCD}" \
    -s "${OPENOCD_SCRIPTS}" \
    -s "${PICO2_SUPPORT}" \
    -f "${PICO2_SUPPORT}/openocd.cfg" \
    -c "source [find interface/cmsis-dap.cfg]" \
    -c "source [find target/rp2350.cfg]" \
    -c "adapter speed 1000" \
    -c init \
    -c targets \
    -c "reset init" \
    -c "flash write_image erase ${FIRMWARE_HEX}" \
    -c "reset run" \
    -c shutdown
