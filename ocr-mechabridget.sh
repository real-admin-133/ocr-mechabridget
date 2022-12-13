#!/bin/bash
set -e

# Setup key environment variables.
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${THIS_DIR}/build/setup_env.sh"

if [[ ! -f "${DOT_VERSION}" ]]; then
   # Perform first-time packages installation.
   "${BUILD_DIR}/fresh_install.sh"
fi

CURRENT_VERSION="$(cat "${DOT_VERSION}")"

source "${VENV_DIR}/bin/activate"
python "${SRC_DIR}/main.py"
