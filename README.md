# CNinfo to NotebookLM

Download A-share stock reports from cninfo.com.cn and upload to NotebookLM for AI-powered analysis.

## Quick Start

```bash
# Setup
cd ~/Documents/GitHub/CNinfo2Notebookllm
source .venv/bin/activate
pip install -r requirements.txt

# Authenticate NotebookLM (one-time)
nlm login

# Run for any stock
python scripts/run.py 600519     # 贵州茅台
python scripts/run.py 山东高速    # By name
```

## What Gets Downloaded

| Type | Reports |
|------|---------|
| Annual (年度报告) | Last 5 years |
| Q1 (一季度) | Latest available year |
| Semi-Annual (半年度) | Latest available year |
| Q3 (三季度) | Latest available year |

## Files

```
scripts/
├── run.py       # Main script (download + upload)
├── download.py  # Download from cninfo
└── upload.py    # Upload to NotebookLM

data/
└── stocks.json  # Stock database (~10MB)
```

## Manual Usage

```bash
# Download only
python scripts/download.py 600519

# Upload existing files
python scripts/upload.py "股票报告" file1.pdf file2.pdf
```
