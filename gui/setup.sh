#!/bin/bash
# Quick setup script for Rehab Test GUI (WSL/G-Drive Optimized)
# Run from the rehab_gui directory: ./setup.sh

set -e

echo "=== Rehab Test GUI — Environment Setup ==="

# Define the local environment path
VENV_PATH="$HOME/.virtualenvs/rehab_gui"

# Create venv locally
echo "[1/3] Creating Python virtual environment at $VENV_PATH..."
mkdir -p "$HOME/.virtualenvs"
python3 -m venv "$VENV_PATH"

# Activate
echo "[2/3] Installing dependencies..."
source "$VENV_PATH/bin/activate"
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/3] Done!"
echo ""
echo "To run the app:"
echo "  source $VENV_PATH/bin/activate"
echo "  python3 main.py"
echo ""
echo "Or just run:  ./run.sh"