#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
rm -rf addons/occasioniq/app
cp -R app addons/occasioniq/app
cp requirements.txt addons/occasioniq/requirements.txt
find addons/occasioniq/app -name __pycache__ -type d -prune -exec rm -rf {} +
echo "Home Assistant app source synced"
