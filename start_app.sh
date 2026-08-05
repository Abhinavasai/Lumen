#!/bin/bash

# Job Hunter Dashboard — macOS / Linux launcher
# Double-click or run: ./start_app.sh

cd "$(dirname "$0")"

echo "============================================"
echo "  Job Hunter Dashboard"
echo "============================================"
echo ""

# Create or activate virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "[!] No .venv found. Creating virtual environment..."
    python3 -m venv .venv
    source .venv/bin/activate
fi

# Install dependencies only if requirements changed or never installed
MARKER=".deps_installed"
NEEDS_INSTALL=0

if [ ! -f "$MARKER" ]; then
    NEEDS_INSTALL=1
else
    CURRENT_HASH=$(md5 -q requirements.txt 2>/dev/null || md5sum requirements.txt | awk '{print $1}')
    SAVED_HASH=$(cat "$MARKER" 2>/dev/null)
    if [ "$CURRENT_HASH" != "$SAVED_HASH" ]; then
        NEEDS_INSTALL=1
    fi
fi

if [ "$NEEDS_INSTALL" -eq 1 ]; then
    echo "[1/2] Installing dependencies from requirements.txt..."
    pip install -r requirements.txt --quiet
    if [ $? -ne 0 ]; then
        echo "[!] pip install failed. Check requirements.txt."
        exit 1
    fi
    # Store hash of requirements.txt
    md5 -q requirements.txt 2>/dev/null || md5sum requirements.txt | awk '{print $1}' > "$MARKER"
    # Handle both macOS (md5 -q) and Linux (md5sum)
    if command -v md5 &>/dev/null; then
        md5 -q requirements.txt > "$MARKER"
    else
        md5sum requirements.txt | awk '{print $1}' > "$MARKER"
    fi
    echo "     Done."
    echo ""
else
    echo "[ok] Dependencies already installed. Skipping pip install."
    echo ""
fi

echo "[2/2] Launching Streamlit on http://localhost:8501"
echo ""
python -m streamlit run app.py
