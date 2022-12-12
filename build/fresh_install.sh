#!/bin/bash

# Setup key environment variables.
THIS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${THIS_DIR}/setup_env.sh"

echo "Perform first-time installation..."

# Setup external apt repos.
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update

# Install debian packages.
echo "Install debian packages..."
grep -vE "^#" "${BUILD_DIR}/apt_1804.manifest" | xargs sudo apt-get install -y

# Create & activate python virtual environment.
mkdir -p "${VENV_DIR}"
python3.9 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"

##################################
### INSIDE VIRTUAL ENVIRONMENT ###
##################################

# Install python packages.
echo "Install python modules..."
python -m ensurepip --upgrade
pip install -r "${BUILD_DIR}/requirements.txt"

# Deactivate python virtual environment.
deactivate

##################################
### INSIDE VIRTUAL ENVIRONMENT ###
##################################

echo -n "${VERSION}" > "${DOT_VERSION}"
echo "DONE."
