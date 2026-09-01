#!/bin/bash
# Quick run script — activates local venv and launches the app

# Move to the directory where the script is located (your G Drive folder)
cd "$(dirname "${BASH_SOURCE[0]:-$0}")"

# Activate the local environment
source "$HOME/.virtualenvs/rehab_gui/bin/activate"

# Run the app
python3 main.py