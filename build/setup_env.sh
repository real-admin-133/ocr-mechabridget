#!/bin/bash
set -e

export VERSION="1.0.0"

export ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export BUILD_DIR="${ROOT_DIR}/build"
export VENV_DIR="${ROOT_DIR}/venv"
export SRC_DIR="${ROOT_DIR}/src"
export DATA_DIR="${ROOT_DIR}/data"
export TEMPLATES_DIR="${DATA_DIR}/templates"
export SAMPLES_DIR="${DATA_DIR}/samples"

export DOT_VERSION="${ROOT_DIR}/.version"

export PYTHONDONTWRITEBYTECODE=1
