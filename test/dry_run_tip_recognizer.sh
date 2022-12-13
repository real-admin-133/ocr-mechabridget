#!/bin/bash
set -e

# Setup key environment variables.
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${THIS_DIR}/../build/setup_env.sh"

source "${VENV_DIR}/bin/activate"
python "${THIS_DIR}/dry_run_tip_recognizer.py" "$@"
