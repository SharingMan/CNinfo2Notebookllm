#!/bin/bash
echo "🚀 正在启动 CNinfo to NotebookLM Web 服务..."
echo "📍 访问地址: http://127.0.0.1:8000"
echo "------------------------------------------------"
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 web/server.py
