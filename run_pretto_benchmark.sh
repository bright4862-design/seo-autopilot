#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/scanner-api"
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest
python benchmark.py pretto
