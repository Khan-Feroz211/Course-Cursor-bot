#!/bin/bash
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Please run Setup_Mac.sh first!"
    exit 1
fi

source venv/bin/activate
python main.py
