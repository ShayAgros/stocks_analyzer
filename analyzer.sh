#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

if [ ! -f "$VENV_DIR/bin/portfolio-analyzer" ]; then
    echo "Installing dependencies..."
    "$VENV_DIR/bin/pip" install -e "$SCRIPT_DIR"
fi

exec "$VENV_DIR/bin/portfolio-analyzer" "$@"
