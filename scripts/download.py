#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download A-share and Hong Kong stock reports from cninfo.com.cn
Stores PDFs in temporary directory, outputs file paths for upload
Optimized with parallel downloads and robust error handling.
"""

import sys
import os
import json
import tempfile
import datetime
import time
import random
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

try:
    from tqdm import tqdm
except ImportError:
    # Fallback if tqdm is not installed
    class tqdm:
        def __init__(self, total=None, desc=""): self.total = total
        def update(self, n=1): pass
        def set_description(self, desc): pass
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass

# Stock database location
STOCKS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "stocks.json"
)


def to_chinese_year(year: int) -> str:
    """Convert year to Chinese numerals (e.g., 2023 -> 二零二三)"""
    mapping = {
        "0": "零",
        "1": "一",
        "2": "二",
        "3": "三",
        "4": "四",
        "5": "五",
        "6": "六",
        "7": "七",
        "8": "八",
        "9": "九",
    }
    return "".join(mapping[d] for d in str(year))


class CnInfoDownloader:
    """Downloads reports from cninfo.com.cn - supports A-share and Hong Kong stocks"""

    def __init__(self, max_workers: int = 5):
        self.cookies = {
            "JSESSIONID": "9A110350B0056BE0C4FDD8A627EF2868",
            "insert_cookie": "37836164",
        }
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:110.0) Gecko/20100101 Firefox/110.0",
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "http://www.cninfo.com.cn",
            "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search&lastPage=index",
        }
        self.timeout = httpx.Timeout(60.0)
        self.query_url = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
        self.market_to_stocks = self._load_stocks()
        self.max_workers = max_workers

    def _load_stocks(self) -> dict:
        """Load stock database from JSON file"""
        if os.path.exists(STOCKS_JSON):
            with open(STOCKS_JSON, "r") as f:
                return json.load(f)
        return {}

    def find_stock(self, stock_input: str) -> tuple:
        """
        Find stock by code or name
        Returns: (stock_code, stock_info, market) or (None, None, None)
        """
        # Try as code first
        for market, market_stocks in self.market_to_stocks.items():
            if stock_input in market_stocks:
                return stock_input, market_stocks[stock_input], market

        # Try as name
        for market, market_stocks in self.market_to_stocks.items():
            for code, info in market_stocks.items():
                if info.get("zwjc") == stock_input:
                    return code, info, market

        return None, None, None

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
    )
    def _query_api(self, client: httpx.Client, payload: dict) -> dict:
        """Perform API query with retries"""
        resp = client.post(self.query_url, data=payload)
        resp.raise_for_status()
        return resp.json()

    def _query_announcements(self, filter_params: dict, market: str = "szse") -> list:
        """Query cninfo API for announcements"""
        client = httpx.Client(
            headers=self.headers, cookies=self.cookies, timeout=self.timeout
        )

        stock_code = filter_params["stock"][0]
        stock_info = None
        for market_stocks in self.market_to_stocks.values():
            if stock_code in market_stocks:
                stock_info = market_stocks[stock_code]
                break

        if not stock_info:
            return []

        payload = self._build_payload(stock_code, stock_info, market, filter_params)
        announcements = []
        has_more = True

        while has_more:
            payload["pageNum"] += 1
            try:
                resp_data = self._query_api(client, payload)
                has_more = resp_data.get("hasMore", False)
                if resp_data.get("announcements"):
                    announcements.extend(resp_data["announcements"])
                if not has_more:
                    break
            except Exception as e:
                print(f"Error querying API: {e}", file=sys.stderr)
                break

        return announcements

    def _build_payload(
        self, stock_code: str, stock_info: dict, market: str, filter_params: dict
    ) -> dict:
        """Build API payload with market-aware parameters"""
        if market == "hke":
            category = ""
            searchkey = ""
        else:
            category = ";".join(filter_params.get("category", []))
            searchkey = filter_params.get("searchkey", "")

        return {
            "pageNum": 0,
            "pageSize": 30,
            "column": market,
            "tabName": "fulltext",
            "plate": "",
            "stock": f"{stock_code},{stock_info['orgId']}",
            "searchkey": searchkey,
            "secid": "",
            "category": category,
            "trade": "",
            "seDate": filter_params.get("seDate", ""),
            "sortName": "",
            "sortType": "",
            "isHLtitle": False,
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
    )
    def _download_file(self, client: httpx.Client, url: str) -> bytes:
        """Download file content with retries"""
        resp = client.get(url)
        resp.raise_for_status()
        return resp.content

    def _download_pdf(self, announcement: dict, output_dir: str) -> str:
        """Download a single PDF file, returns file path"""
        headers = self.headers.copy()
        # static.cninfo.com.cn might have different requirements or be more lenient
        client = httpx.Client(headers=headers, cookies=self.cookies, timeout=self.timeout)

        sec_code = announcement["secCode"]
        sec_name = announcement["secName"].replace("*", "s").replace("/", "-")
        title = announcement["announcementTitle"].replace("/", "-").replace("\\", "-")
        adjunct_url = announcement["adjunctUrl"]
        announcement_id = announcement["announcementId"]

        if announcement.get("adjunctType") != "PDF":
            return None

        filename = f"{sec_code}_{sec_name}_{title}_{announcement_id}.pdf"
        filename = "".join(c for c in filename if c.isalnum() or c in "._-")
        filepath = os.path.join(output_dir, filename)

        if not os.path.exists(filepath):
            try:
                content = self._download_file(
                    client, f"http://static.cninfo.com.cn/{adjunct_url}"
                )
                with open(filepath, "wb") as f:
                    f.write(content)
                # Reduced sleep since concurrency is managed
                time.sleep(random.uniform(0.1, 0.3))
            except Exception as e:
                print(f"Download failed for {title}: {e}", file=sys.stderr)
                return None

        return filepath

    def _is_main_annual_report(self, title: str, year: int, market: str = "szse") -> bool:
        """Check if this is the main annual report"""
        chinese_year = to_chinese_year(year)

        if market == "hke":
            has_year = f"{year}" in title or chinese_year in title
            is_annual = (
                "annual report" in title.lower()
                or "年度报告" in title
                or "年报" in title
                or f"{year}财务年度报告" in title
            )
            is_summary = "summary" in title.lower() or "摘要" in title
            is_quarterly = "季度" in title or "半年度" in title or "中期" in title
            is_english_only = "英文" in title
            return (
                has_year
                and is_annual
                and not is_summary
                and not is_quarterly
                and not is_english_only
            )
        else:
            if f"{year}年年度报告" not in title and f"{year}年年报" not in title:
                return False
            if "摘要" in title or "英文" in title or "summary" in title.lower():
                return False
            if "更正" in title or "修订" in title:
                return False
            return True

    def _is_main_periodic_report(self, title: str, report_type: str) -> bool:
        """Check if this is a main periodic report"""
        if "摘要" in title or "英文" in title:
            return False
        if "更正" in title or "修订" in title:
            return False

        if report_type == "semi":
            return "半年度报告" in title or "中期报告" in title
        elif report_type == "q1":
            return "一季度" in title or "第一季度" in title
        elif report_type == "q3":
            return "三季度" in title or "第三季度" in title

        return False

    def download_reports_parallel(self, announcements_to_download: list, output_dir: str) -> list:
        """Download multiple announcements in parallel with a progress bar"""
        downloaded = []
        if not announcements_to_download:
            return downloaded

        with tqdm(total=len(announcements_to_download), desc="📥 Downloading") as pbar:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._download_pdf, ann, output_dir): ann
                    for ann in announcements_to_download
                }
                for future in as_completed(futures):
                    filepath = future.result()
                    if filepath:
                        downloaded.append(filepath)
                    pbar.update(1)
        return downloaded

    def download_annual_reports(
        self, stock_code: str, years: list, output_dir: str, market: str = "szse"
    ) -> list:
        """Identify then download annual reports for specified years"""
        to_download = []
        for year in years:
            search_start = f"{year + 1 if market != 'hke' else year}-01-01"
            search_end = f"{year + 1}-06-30"

            if market == "hke":
                filter_params = {
                    "stock": [stock_code],
                    "category": [],
                    "searchkey": "",
                    "seDate": f"{search_start}~{search_end}",
                }
            else:
                filter_params = {
                    "stock": [stock_code],
                    "category": ["category_ndbg_szsh"],
                    "searchkey": f"{year}年年度报告",
                    "seDate": f"{search_start}~{search_end}",
                }

            announcements = self._query_announcements(filter_params, market)
            for ann in announcements:
                if self._is_main_annual_report(ann["announcementTitle"], year, market):
                    to_download.append(ann)
                    break

        return self.download_reports_parallel(to_download, output_dir)

    def download_periodic_reports(
        self, stock_code: str, year: int, output_dir: str, market: str = "szse"
    ) -> list:
        """Identify then download Q1, semi-annual, Q3 reports for current year"""
        to_download = []
        report_configs = [
            ("q1", "category_yjdbg_szsh", "一季度报告", f"{year}-04-01", f"{year}-05-31"),
            ("semi", "category_bndbg_szsh", "半年度报告", f"{year}-08-01", f"{year}-09-30"),
            ("q3", "category_sjdbg_szsh", "三季度报告", f"{year}-10-01", f"{year}-11-30"),
        ]

        for report_type, category, search_term, start_date, end_date in report_configs:
            if market == "hke":
                filter_params = {
                    "stock": [stock_code],
                    "category": [],
                    "searchkey": "",
                    "seDate": f"{start_date}~{end_date}",
                }
            else:
                filter_params = {
                    "stock": [stock_code],
                    "category": [category],
                    "searchkey": search_term,
                    "seDate": f"{start_date}~{end_date}",
                }

            announcements = self._query_announcements(filter_params, market)
            for ann in announcements:
                if self._is_main_periodic_report(ann["announcementTitle"], report_type):
                    to_download.append(ann)
                    break

        return self.download_reports_parallel(to_download, output_dir)

    def download_recent_announcements(
        self, stock_code: str, output_dir: str, market: str = "szse", limit: int = 15
    ) -> tuple:
        """Fetch latest announcements and download top ones as PDF"""
        six_months_ago = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime("%Y-%m-%d")
        today = datetime.datetime.now().strftime("%Y-%m-%d")

        filter_params = {
            "stock": [stock_code],
            "category": [],  # All categories
            "searchkey": "",
            "seDate": f"{six_months_ago}~{today}",
        }

        all_ann = self._query_announcements(filter_params, market)
        # API might return more, limit to requested
        recent_ann = all_ann[:limit]
        
        # Download top 5 for depth
        to_download = recent_ann[:5]
        downloaded_files = self.download_reports_parallel(to_download, output_dir)
        
        return recent_ann, downloaded_files

    def generate_news_summary(
        self, stock_name: str, announcements: list, output_dir: str
    ) -> str:
        """Create a Markdown summary of recent announcements"""
        filename = f"{stock_name}_最新公告摘要_{datetime.datetime.now().strftime('%Y%m%d')}.md"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {stock_name} 最新公告与资信摘要\n\n")
            f.write(f"生成日期: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("## 最近公告列表\n\n")
            if not announcements:
                f.write("暂无最近六个月的重大公告。\n")
            else:
                for ann in announcements:
                    title = ann.get("announcementTitle", "无标题")
                    date_ms = ann.get("announcementTime")
                    date_str = ""
                    if date_ms:
                        date_str = datetime.datetime.fromtimestamp(date_ms/1000.0).strftime("%Y-%m-%d")
                    
                    url = f"http://static.cninfo.com.cn/{ann.get('adjunctUrl')}"
                    f.write(f"- **[{date_str}]** {title} \n  [链接]({url})\n")
            
            f.write("\n\n---\n*注：本摘要由 CNinfo2NotebookLM 自动生成，用于 AI 辅助分析。*\n")
            
        return filepath


def main():
    """Main entry point - downloads reports and prints file paths"""
    if len(sys.argv) < 2:
        print("Usage: python download.py <stock_code_or_name> [output_dir]")
        sys.exit(1)

    stock_input = sys.argv[1]
    output_dir = (
        sys.argv[2] if len(sys.argv) > 2 else tempfile.mkdtemp(prefix="cninfo_reports_")
    )

    downloader = CnInfoDownloader()
    stock_code, stock_info, market = downloader.find_stock(stock_input)
    if not stock_code:
        print(f"❌ Stock not found: {stock_input}", file=sys.stderr)
        sys.exit(1)

    stock_name = stock_info.get("zwjc", stock_code)
    market_display = "Hong Kong" if market == "hke" else "A-share"
    print(f"📊 Found stock: {stock_code} ({stock_name}) [{market_display}]")
    print(f"📁 Output directory: {output_dir}")

    current_year = datetime.datetime.now().year
    annual_years = list(range(current_year - 5, current_year))

    # 1. Annual Reports
    print(f"\n📥 Fetching metadata for annual reports...")
    annual_files = downloader.download_annual_reports(
        stock_code, annual_years, output_dir, market
    )

    # 2. Periodic Reports
    print(f"\n📥 Fetching metadata for periodic reports...")
    periodic_files = downloader.download_periodic_reports(
        stock_code, current_year, output_dir, market
    )

    if not periodic_files:
        print(f"   No {current_year} reports yet, trying {current_year - 1}...")
        periodic_files = downloader.download_periodic_reports(
            stock_code, current_year - 1, output_dir, market
        )
    elif len(periodic_files) < 3:
        print(f"   Checking {current_year - 1} for additional reports...")
        prev_year_files = downloader.download_periodic_reports(
            stock_code, current_year - 1, output_dir, market
        )
        periodic_files.extend(prev_year_files)

    # 3. Latest Announcements & News
    print(f"\n📥 Fetching latest announcements and generating news summary...")
    recent_ann, recent_files = downloader.download_recent_announcements(
        stock_code, output_dir, market
    )
    summary_file = downloader.generate_news_summary(stock_name, recent_ann, output_dir)

    # Combine everything
    all_files = list(set(annual_files + periodic_files + recent_files + [summary_file]))

    print(f"\n{'=' * 50}")
    print(f"✅ Successfully downloaded {len(all_files)} unique items (Reports + News)")
    print(f"📁 Location: {output_dir}")

    result = {
        "stock_code": stock_code,
        "stock_name": stock_name,
        "market": market,
        "output_dir": output_dir,
        "files": all_files,
    }

    print(f"\n---JSON_OUTPUT---")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
