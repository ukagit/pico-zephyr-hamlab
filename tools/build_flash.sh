#!/usr/bin/env bash

set -euo pipefail

readonly PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${PROJECT_DIR}/tools/build.sh" "$@"
exec "${PROJECT_DIR}/tools/flash_openocd.sh"
