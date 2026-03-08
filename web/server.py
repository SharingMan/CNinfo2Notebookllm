import sys
import os
import json
import tempfile
import shutil
import datetime
import urllib.parse
import uuid
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add the parent directory to sys.path so we can import our scripts
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from scripts.download import CnInfoDownloader

app = FastAPI(title="CNinfo to NotebookLM Web")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Vercel 的函数文件系统只有 /tmp 可写，本地则继续写到项目目录下。
RUNTIME_STORAGE_ROOT = os.environ.get("CNINFO_STORAGE_ROOT") or (
    os.path.join(tempfile.gettempdir(), "cninfo-to-notebooklm")
    if os.environ.get("VERCEL")
    else PROJECT_ROOT
)
os.makedirs(RUNTIME_STORAGE_ROOT, exist_ok=True)

# Static files
static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")


def sanitize_folder_name(value: str) -> str:
    invalid_chars = '<>:"/\\|?*'
    sanitized = "".join("_" if ch in invalid_chars else ch for ch in value).strip()
    return sanitized or "stock"


def build_output_dir(stock_label: str) -> str:
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    run_id = uuid.uuid4().hex[:8]
    folder_name = f"{sanitize_folder_name(stock_label)}_财务资料_{date_str}_{run_id}"
    output_dir = os.path.join(RUNTIME_STORAGE_ROOT, folder_name)
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def resolve_runtime_path(path: str) -> str:
    abs_path = os.path.abspath(os.path.expanduser(path))
    try:
        common_root = os.path.commonpath([abs_path, RUNTIME_STORAGE_ROOT])
    except ValueError as exc:
        raise ValueError("Invalid path") from exc

    if common_root != RUNTIME_STORAGE_ROOT:
        raise ValueError("Invalid path")

    return abs_path

@app.get("/")
async def index():
    return FileResponse(os.path.join(static_path, "index.html"))

async def analyze_task(stock_input: str):
    """
    Generator that performs the analysis and yields SSE events.
    """
    def sse_message(data):
        return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"

    try:
        # 1. Initialize
        yield sse_message({"type": "progress", "percent": 5, "status": "初始化并查询股票..."})
        yield sse_message({"type": "log", "message": f"正在查询: {stock_input}"})
        
        # Determine if US Stock
        import re
        is_us_stock = bool(re.match(r"^[A-Za-z]{1,5}$", stock_input))

        all_files = []
        stock_name = stock_input

        if is_us_stock:
            output_dir = build_output_dir(stock_input.upper())
            # US Flow
            yield sse_message({"type": "log", "message": f"检测为美股代码: {stock_input}"})
            yield sse_message({"type": "progress", "percent": 15, "status": "正在从 SEC EDGAR 获取报告..."})
            from scripts.us_download import USStockDownloader
            us_downloader = USStockDownloader(email="user@notebooklm.app")
            try:
                # Wrap in thread since it's blocking
                us_files = us_downloader.download_reports(stock_input, output_dir)
                all_files.extend(us_files)
                yield sse_message({"type": "log", "message": f"成功下载 {len(us_files)} 个美股报告文件（含 Markdown 转换）。"})
            except Exception as e:
                yield sse_message({"type": "error", "message": f"美股下载失败: {str(e)}"})
                return
        else:
            # CN Flow
            downloader = CnInfoDownloader(max_workers=5)
            stock_code, stock_info, market = downloader.find_stock(stock_input)
            
            if not stock_code:
                yield sse_message({"type": "error", "message": f"未找到股票: {stock_input}"})
                return

            stock_name = stock_info.get("zwjc", stock_code)
            output_dir = build_output_dir(stock_name)
            yield sse_message({"type": "log", "message": f"找到股票: {stock_name} ({stock_code})"})

            current_year = datetime.datetime.now().year
            annual_years = list(range(current_year - 5, current_year))

            yield sse_message({"type": "progress", "percent": 20, "status": "获取财报元数据..."})
            yield sse_message({"type": "log", "message": "正在抓取近 5 年年报信息..."})
            annual_files = downloader.download_annual_reports(stock_code, annual_years, output_dir, market)
            
            yield sse_message({"type": "progress", "percent": 40, "status": "获取定期报告..."})
            periodic_files = downloader.download_periodic_reports(stock_code, current_year, output_dir, market)
            if not periodic_files:
                periodic_files = downloader.download_periodic_reports(stock_code, current_year - 1, output_dir, market)
            
            yield sse_message({"type": "progress", "percent": 60, "status": "获取最新公告..."})
            recent_ann, recent_files = downloader.download_recent_announcements(stock_code, output_dir, market)
            summary_file = downloader.generate_news_summary(stock_name, recent_ann, output_dir)

            all_files.extend(list(set(annual_files + periodic_files + recent_files + [summary_file])))

        # 3.8 Copy Prompts
        assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
        prompt_src = os.path.join(assets_dir, "financial_analyst_prompt.txt")
        if os.path.exists(prompt_src):
            shutil.copy(prompt_src, os.path.join(output_dir, "00_AI分析指令.txt"))
            yield sse_message({"type": "log", "message": "已生成 AI 分析指令文件。"})
            all_files.append(os.path.join(output_dir, "00_AI分析指令.txt"))

        if not all_files:
            yield sse_message({"type": "error", "message": "未找到相关报告"})
            return

        yield sse_message({"type": "log", "message": f"所有资料已准备就绪。"})
        yield sse_message({"type": "progress", "percent": 95, "status": "完成所有任务"})
        
        yield sse_message({
            "type": "complete", 
            "folder_path": output_dir, 
            "stock_name": stock_name,
            "count": len(all_files)
        })

    except Exception as e:
        yield sse_message({"type": "error", "message": str(e)})

@app.get("/api/analyze")
async def analyze(stock: str = Query(...)):
    return StreamingResponse(analyze_task(stock), media_type="text/event-stream")


def calculate_relevance(query: str, code: str, name: str, pinyin: str) -> int:
    """Calculate relevance score for sorting. Higher = better match."""
    query_lower = query.lower()
    score = 0

    # Exact code match (highest priority)
    if code == query:
        return 1000

    # Code starts with query (high priority)
    if code.startswith(query):
        score += 500 - len(code)  # Shorter code = better match

    # Name contains query (medium priority)
    if query_lower in name.lower():
        score += 300
        # Bonus if name starts with query
        if name.lower().startswith(query_lower):
            score += 100

    # Pinyin (首字母) matches query
    if pinyin and query_lower == pinyin.lower():
        score += 400  # Exact pinyin match
    elif pinyin and pinyin.lower().startswith(query_lower):
        score += 200  # Pinyin starts with query

    return score


@app.get("/api/search")
async def search_stocks(query: str = Query(..., min_length=1), limit: int = 10):
    """
    Fuzzy search stocks by code, name, or pinyin initials
    Returns: list of matching stocks sorted by relevance
    """
    try:
        downloader = CnInfoDownloader(max_workers=1)
        matches = []
        query_lower = query.lower()

        # Search in all markets (A股 and 港股)
        for market, market_stocks in downloader.market_to_stocks.items():
            for code, info in market_stocks.items():
                name = info.get("zwjc", "")
                pinyin = info.get("pinyin", "")

                # Check if matches any criteria
                is_match = (
                    code.startswith(query) or  # Code starts with query
                    query_lower in name.lower() or  # Name contains query
                    (pinyin and pinyin.lower().startswith(query_lower))  # Pinyin starts with query
                )

                if is_match:
                    score = calculate_relevance(query, code, name, pinyin)
                    matches.append({
                        "code": code,
                        "name": name,
                        "market": market,
                        "pinyin": pinyin,
                        "score": score
                    })

        # Sort by relevance score (descending)
        matches.sort(key=lambda x: x["score"], reverse=True)

        # Also support US stocks (always check, not just for English queries)
        common_us_stocks = [
            ("AAPL", "苹果公司"),
            ("MSFT", "微软"),
            ("GOOGL", "谷歌A"),
            ("GOOG", "谷歌C"),
            ("AMZN", "亚马逊"),
            ("TSLA", "特斯拉"),
            ("META", "Meta Platforms"),
            ("NVDA", "英伟达"),
            ("NFLX", "奈飞"),
            ("AMD", "超威半导体"),
            ("INTC", "英特尔"),
            ("CRM", "Salesforce"),
            ("ADBE", "Adobe"),
            ("PYPL", "PayPal"),
            ("UBER", "Uber"),
            ("COIN", "Coinbase"),
            ("BABA", "阿里巴巴"),
            ("JD", "京东集团"),
            ("BIDU", "百度"),
            ("NIO", "蔚来"),
            ("PDD", "拼多多"),
            ("TME", "腾讯音乐"),
            ("LI", "理想汽车"),
            ("XPEV", "小鹏汽车"),
            ("BEKE", "贝壳"),
            ("ZH", "知乎"),
            ("WB", "微博"),
            ("YY", "欢聚时代"),
        ]
        us_results = []
        for code, name in common_us_stocks:
            # Match by code (case insensitive) or name contains query
            if code.upper().startswith(query.upper()) or query_lower in name.lower():
                us_results.append({
                    "code": code,
                    "name": name,
                    "market": "US"
                })

        # Combine and re-sort results by relevance
        all_results = matches[:limit] if matches else []

        # Add US stocks if not already in results
        for us_stock in us_results:
            if not any(r["code"] == us_stock["code"] for r in all_results):
                all_results.append(us_stock)

        # Remove score field and limit results
        results = [{"code": r["code"], "name": r["name"], "market": r["market"]} for r in all_results[:limit]]

        return {"results": results}

    except Exception as e:
        return {"results": [], "error": str(e)}


@app.get("/api/open-folder")
async def open_folder(path: str = Query(...)):
    """
    Open a folder in the system file manager (local only)
    """
    return {"success": False, "error": "云端版本不支持打开本地文件夹，请使用下载功能"}


@app.get("/api/download-zip")
async def download_zip(path: str = Query(...)):
    """
    Create and download a ZIP archive of the folder
    After download, the folder will be marked for cleanup
    """
    import zipfile
    import io

    try:
        abs_path = resolve_runtime_path(path)

        if not os.path.exists(abs_path):
            return {"success": False, "error": "Path does not exist"}

        # Create ZIP in memory with UTF-8 support for Chinese filenames
        zip_buffer = io.BytesIO()
        folder_name = os.path.basename(abs_path)

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Enable UTF-8 filenames for ZIP
            for root, dirs, files in os.walk(abs_path):
                for file in files:
                    file_path = os.path.join(root, file)
                    arc_name = os.path.join(folder_name, os.path.relpath(file_path, abs_path))
                    # Write with UTF-8 flag
                    zip_info = zipfile.ZipInfo(filename=arc_name)
                    zip_info.compress_type = zipfile.ZIP_DEFLATED
                    # Set UTF-8 flag
                    zip_info.flag_bits |= 0x800
                    # Read file content
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    zip_file.writestr(zip_info, content)

        zip_buffer.seek(0)

        # We removed the immediate cleanup here because it was too aggressive
        # and could delete folders from other active users.
        # Cleanup is now mainly handled by the client-side call to /api/cleanup
        # or the periodic global cleanup with a sane timeout.

        # Encode filename for Content-Disposition header (RFC 5987)
        # Use safe ASCII filename for legacy clients, UTF-8 for modern clients
        safe_filename = folder_name.encode('ascii', 'ignore').decode() or "financial_reports"
        encoded_filename = urllib.parse.quote(folder_name, safe='')
        content_disposition = f"attachment; filename=\"{safe_filename}.zip\"; filename*=UTF-8''{encoded_filename}.zip"

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={
                "Content-Disposition": content_disposition
            }
        )

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


def cleanup_old_folders(max_age_hours=1):
    """
    Clean up old financial report folders to save disk space
    Default: remove folders older than 1 hour
    """
    import shutil
    import time

    try:
        current_time = time.time()

        for item in os.listdir(RUNTIME_STORAGE_ROOT):
            # Check if it's a financial report folder
            if '_财务资料_' in item and os.path.isdir(os.path.join(RUNTIME_STORAGE_ROOT, item)):
                folder_path = os.path.join(RUNTIME_STORAGE_ROOT, item)
                # Get folder modification time
                mtime = os.path.getmtime(folder_path)
                age_hours = (current_time - mtime) / 3600

                if age_hours > max_age_hours:
                    shutil.rmtree(folder_path)
                    print(f"Cleaned up old folder: {item}")

    except Exception as e:
        print(f"Cleanup error: {e}")


# 只在临时存储目录下自动清理，避免本地仓库示例数据被误删。
if RUNTIME_STORAGE_ROOT != PROJECT_ROOT:
    cleanup_old_folders(max_age_hours=1)


@app.get("/api/cleanup")
async def cleanup_endpoint(path: str = Query(...)):
    """
    Clean up a specific folder after download
    """
    import shutil

    try:
        abs_path = resolve_runtime_path(path)

        if os.path.exists(abs_path) and '_财务资料_' in abs_path:
            shutil.rmtree(abs_path)
            return {"success": True, "message": f"Cleaned up: {os.path.basename(abs_path)}"}

        return {"success": False, "error": "Folder not found or invalid"}

    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    # Support cloud deployment (Railway, etc.)
    port = int(os.environ.get("PORT", 8000))
    # Use 0.0.0.0 for cloud, 127.0.0.1 for local
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)
