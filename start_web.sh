#!/bin/bash
echo "🚀 正在启动 CNinfo to NotebookLM Web 服务..."
echo "📍 访问地址: http://127.0.0.1:8000"
echo "------------------------------------------------"
PYTHON_CMD="/opt/homebrew/bin/python3.11"
if [ ! -f "$PYTHON_CMD" ]; then
    PYTHON_CMD="python3"
fi

export PYTHONPATH=$PYTHONPATH:$(pwd)
$PYTHON_CMD web/server.py
