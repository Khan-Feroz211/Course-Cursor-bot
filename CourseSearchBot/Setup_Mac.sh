#!/bin/bash
set -e

echo ""
echo "============================================"
echo "  Course Search Bot — First Time Setup (Mac)"
echo "============================================"
echo ""

# Check Python 3
if ! command -v python3 &>/dev/null; then
    echo "ERROR: Python 3 is not installed."
    echo "Download it from https://www.python.org/downloads/"
    exit 1
fi

echo "[1/3] Creating virtual environment..."
python3 -m venv venv

echo "[2/3] Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo "[3/3] Creating folders..."
mkdir -p course_docs data

echo ""
echo "============================================"
echo " Setup complete!"
echo " Run:  bash Launch_Mac.sh   to start."
echo "============================================"
echo ""
