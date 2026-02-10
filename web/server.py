import sys
import os
import asyncio
import json
import logging
import tempfile
import shutil
import datetime
from fastapi import FastAPI, Request, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Add the parent directory to sys.path so we can import our scripts
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'scripts'))

from scripts.download import CnInfoDownloader
from scripts.upload import (
    create_notebook,
    upload_all_sources,
    cleanup_temp_files,
    configure_notebook,
    get_notebooklm_cmd
)

app = FastAPI(title="CNinfo to NotebookLM Web")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
static_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

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

        # 2. Setup environment (Persistent)
        date_str = datetime.datetime.now().strftime("%Y%m%d")
        output_dir = os.path.join(os.getcwd(), f"{stock_input}_财务资料_{date_str}")
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        all_files = []
        stock_name = stock_input

        if is_us_stock:
            # US Flow
            yield sse_message({"type": "log", "message": f"检测为美股代码: {stock_input}"})
            yield sse_message({"type": "progress", "percent": 15, "status": "正在从 SEC EDGAR 获取报告..."})
            from us_download import USStockDownloader
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
            yield sse_message({"type": "log", "message": f"找到股票: {stock_name} ({stock_code})"})
            
            # Update folder name to include zwjc
            new_output_dir = os.path.join(os.getcwd(), f"{stock_name}_财务资料_{date_str}")
            if not os.path.exists(new_output_dir):
                os.rename(output_dir, new_output_dir)
                output_dir = new_output_dir

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
    Open a folder in the system file manager
    Security: Only allows opening folders within the project directory
    """
    import subprocess
    import platform

    try:
        # Normalize and validate path
        abs_path = os.path.abspath(os.path.expanduser(path))
        cwd = os.getcwd()

        # Security check: must be within project directory
        if not abs_path.startswith(cwd):
            return {"success": False, "error": "Invalid path: outside project directory"}

        # Check if path exists
        if not os.path.exists(abs_path):
            return {"success": False, "error": f"Path does not exist: {path}"}

        # Open folder based on OS
        system = platform.system()
        if system == "Darwin":  # macOS
            subprocess.Popen(["open", abs_path])
        elif system == "Windows":
            subprocess.Popen(["explorer", abs_path])
        else:  # Linux
            subprocess.Popen(["xdg-open", abs_path])

        return {"success": True, "path": abs_path}

    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    # Support cloud deployment (Railway, etc.)
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run(app, host=host, port=port)
