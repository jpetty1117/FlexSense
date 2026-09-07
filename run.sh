#!/usr/bin/env bash
# ==============================================================================
# Squish Therapy — Top-Level Launch Script
#
# Usage:
#   ./run.sh               # Launch GUI (default)
#   ./run.sh --flash       # Flash firmware to STM32, then launch GUI
#   ./run.sh -f            # Short flag for --flash
#   ./run.sh --build-fw    # Compile firmware only (PlatformIO)
#   ./run.sh -h, --help    # Show help
# ==============================================================================

set -e

# Project root directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIRMWARE_DIR="${SCRIPT_DIR}/firmware"
GUI_DIR="${SCRIPT_DIR}/gui"

# ANSI Colors
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Helper to find PlatformIO binary
find_pio() {
    if command -v pio >/dev/null 2>&1; then
        echo "pio"
    elif [ -x "$HOME/.platformio/penv/bin/pio" ]; then
        echo "$HOME/.platformio/penv/bin/pio"
    elif [ -x "$HOME/.local/bin/pio" ]; then
        echo "$HOME/.local/bin/pio"
    else
        echo ""
    fi
}

# Helper to activate Python virtual environment
activate_venv() {
    if [ -f "$HOME/.virtualenvs/rehab_gui/bin/activate" ]; then
        echo -e "${CYAN}[INFO] Activating virtual environment: $HOME/.virtualenvs/rehab_gui${NC}"
        source "$HOME/.virtualenvs/rehab_gui/bin/activate"
    elif [ -f "${GUI_DIR}/venv/bin/activate" ]; then
        echo -e "${CYAN}[INFO] Activating virtual environment: ${GUI_DIR}/venv${NC}"
        source "${GUI_DIR}/venv/bin/activate"
    else
        echo -e "${YELLOW}[WARN] No virtual environment found. Using system python3.${NC}"
    fi
}

# Flags
FLASH_FIRMWARE=false
BUILD_ONLY=false
REMAINING_ARGS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--flash)
            FLASH_FIRMWARE=true
            shift
            ;;
        -b|--build-fw)
            BUILD_ONLY=true
            shift
            ;;
        -h|--help)
            echo "Squish Therapy Runner"
            echo ""
            echo "Usage: ./run.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -f, --flash       Build and upload firmware to STM32 (ST-Link) before launching GUI"
            echo "  -b, --build-fw    Build firmware only (PlatformIO) without launching GUI"
            echo "  -h, --help        Show this help message"
            echo ""
            echo "Examples:"
            echo "  ./run.sh            # Launch GUI immediately"
            echo "  ./run.sh -f         # Flash Nucleo board & launch GUI"
            echo "  ./run.sh --build-fw # Compile firmware test"
            exit 0
            ;;
        *)
            REMAINING_ARGS+=("$1")
            shift
            ;;
    esac
done

PIO_BIN=$(find_pio)

# Handle firmware flash or build
if [ "$FLASH_FIRMWARE" = true ] || [ "$BUILD_ONLY" = true ]; then
    if [ -z "$PIO_BIN" ]; then
        echo -e "${RED}[ERROR] PlatformIO (pio) not found in PATH, ~/.platformio/penv/bin, or ~/.local/bin.${NC}"
        exit 1
    fi

    if [ "$FLASH_FIRMWARE" = true ]; then
        echo -e "${CYAN}[INFO] Building & flashing STM32 firmware via ${PIO_BIN}...${NC}"
        "$PIO_BIN" run -t upload -d "$FIRMWARE_DIR"
        echo -e "${GREEN}[SUCCESS] Firmware flashed successfully!${NC}"
        echo -e "${CYAN}[INFO] Waiting 1s for USB serial port re-enumeration...${NC}"
        sleep 1
    elif [ "$BUILD_ONLY" = true ]; then
        echo -e "${CYAN}[INFO] Building STM32 firmware via ${PIO_BIN}...${NC}"
        "$PIO_BIN" run -d "$FIRMWARE_DIR"
        echo -e "${GREEN}[SUCCESS] Firmware build successful!${NC}"
        exit 0
    fi
fi

# Launch GUI
activate_venv
echo -e "${GREEN}[INFO] Starting Rehab GUI...${NC}"
cd "$GUI_DIR"
exec python3 main.py "${REMAINING_ARGS[@]}"
