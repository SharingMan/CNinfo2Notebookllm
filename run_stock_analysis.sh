#!/bin/bash

# CNinfo to NotebookLM - Stock Analysis Runner
# This script ensures we use Python 3.11 for compatibility

PYTHON_CMD="/opt/homebrew/bin/python3.11"

if [ ! -f "$PYTHON_CMD" ]; then
    echo "❌ Python 3.11 not found at $PYTHON_CMD"
    echo "Please install Python 3.11 using: brew install python@3.11"
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Run the stock analysis script
$PYTHON_CMD "$SCRIPT_DIR/scripts/run.py" "$@"
