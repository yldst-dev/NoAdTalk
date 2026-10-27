#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
exec /usr/bin/python3 -B Scripts/manage.py "$@"
