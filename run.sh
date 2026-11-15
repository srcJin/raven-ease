#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec "${RAVEN_PYTHON:-.venv/bin/python}" main.py "$@"
