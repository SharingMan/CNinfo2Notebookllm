#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CNinfo to NotebookLM - Main Orchestration Script
Downloads and uploads stock reports with high performance.
"""

import sys
import os
import json
import tempfile
import shutil
import datetime

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from download import CnInfoDownloader
from upload import (
    create_notebook,
    upload_all_sources,
    cleanup_temp_files,
    configure_notebook,
    get_notebooklm_cmd
)


def check_auth():
    """Check if NotebookLM is authenticated"""
    notebooklm_cmd = get_notebooklm_cmd()
    import subprocess
    try:
        # 'notebooklm notebooks' is a cheap way to check auth
        result = subprocess.run([notebooklm_cmd, "notebooks", "--limit", "1"], capture_output=True, text=True)
        if "Missing required cookies" in result.stderr or "Run 'notebooklm login'" in result.stderr:
            return False
        return True
    except Exception:
        return False


def main():
    """Main entry point"""
    import argparse
    parser = argparse.ArgumentParser(description="CNinfo to NotebookLM - Financial Report Downloader")
    parser.add_argument("stock", help="Stock code or name (e.g. 600519 or AAPL)")
    parser.add_argument("--upload", action="store_true", help="Upload to NotebookLM (requires login)")
    args = parser.parse_args()

    stock_input = args.stock.strip()

    # Determine if US Stock (Simple heuristic: All letters, 5 chars or less)
    is_us_stock = False
    import re
    if re.match(r"^[A-Za-z]{1,5}$", stock_input):
        is_us_stock = True

    # 2. Setup persistent directory
    date_str = datetime.datetime.now().strftime("%Y%m%d")
    output_dir = os.path.join(os.getcwd(), f"{stock_input}_财务资料_{date_str}")
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    print(f"📁 Saving to: {output_dir}")

    all_files = []
    stock_name = stock_input

    if is_us_stock:
        # US Flow
        print(f"📊 Analyzing US Stock: {stock_input}")
        from us_download import USStockDownloader
        # TODO: Get user email from args or config
        us_downloader = USStockDownloader(email="user@notebooklm.app") 
        try:
            us_files = us_downloader.download_reports(stock_input, output_dir)
            all_files.extend(us_files)
        except Exception as e:
            print(f"❌ Error downloading US reports: {e}")
            sys.exit(1)
    else:
        # CN Flow
        downloader = CnInfoDownloader(max_workers=8)
        stock_code, stock_info, market = downloader.find_stock(stock_input)
        if not stock_code:
            print(f"❌ Stock not found: {stock_input}", file=sys.stderr)
            sys.exit(1)

        stock_name = stock_info.get("zwjc", stock_code)
        market_display = "Hong Kong" if market == "hke" else "A-share"
        print(f"📊 Analyzing: {stock_code} ({stock_name}) [{market_display}]")
        
        # Override output dir name with full name
        new_output_dir = os.path.join(os.getcwd(), f"{stock_name}_财务资料_{date_str}")
        if not os.path.exists(new_output_dir):
            os.rename(output_dir, new_output_dir)
            output_dir = new_output_dir

        current_year = datetime.datetime.now().year
        annual_years = list(range(current_year - 5, current_year))

        # 3. Download reports
        print(f"\n📥 Fetching reports metadata...")
        annual_files = downloader.download_annual_reports(stock_code, annual_years, output_dir, market)
        
        periodic_files = downloader.download_periodic_reports(stock_code, current_year, output_dir, market)
        if not periodic_files:
            periodic_files = downloader.download_periodic_reports(stock_code, current_year - 1, output_dir, market)
        elif len(periodic_files) < 3:
            prev_year_files = downloader.download_periodic_reports(stock_code, current_year - 1, output_dir, market)
            periodic_files.extend(prev_year_files)

        # 3.5 Latest Announcements and News
        print(f"\n📥 Fetching latest announcements and generating news summary...")
        recent_ann, recent_files = downloader.download_recent_announcements(stock_code, output_dir, market)
        summary_file = downloader.generate_news_summary(stock_name, recent_ann, output_dir)

        all_files = list(set(annual_files + periodic_files + recent_files + [summary_file]))

    
    # 3.8 Copy Prompts
    assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
    prompt_src = os.path.join(assets_dir, "financial_analyst_prompt.txt")
    if os.path.exists(prompt_src):
        shutil.copy(prompt_src, os.path.join(output_dir, "00_AI分析指令.txt"))
        print(f"✅ Copied AI analysis instructions.")

    if not all_files:
        print("❌ No reports found for this stock.")
        sys.exit(1)

    print(f"✅ Successfully saved {len(all_files)} items to folder.")

    # 4. Handle NotebookLM Upload (Optional)
    if args.upload:
        if not check_auth():
            print("\n⚠️  NotebookLM Authentication Required! Skipping upload.")
            print(f"💡 Files are available at: {output_dir}")
            sys.exit(0)

        print(f"\n🚀 Creating NotebookLM workspace...")
        notebook_title = f"{stock_name} 财务分析"
        notebook_id = create_notebook(notebook_title)

        if not notebook_id:
            print("❌ Failed to create notebook.")
            sys.exit(1)

        configure_notebook(notebook_id, prompt_src)
        upload_all_sources(notebook_id, all_files, max_workers=4)

        print(f"\n🎉 UPLOAD SUCCESS!")
        print(f"🔗 View: https://notebooklm.google.com/notebook/{notebook_id}")
    else:
        print(f"\n🎉 COMPLETE!")
        print(f"📂 Location: {output_dir}")
        print(f"💡 You can now manually upload these files to any AI tool.")


if __name__ == "__main__":
    main()
