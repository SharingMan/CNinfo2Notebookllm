
import os
import sys
import glob
import shutil
import datetime
from sec_edgar_downloader import Downloader
from markdownify import markdownify as md

class USStockDownloader:
    def __init__(self, email="user@example.com", company="Individual"):
        self.email = email
        self.company = company
        self.dl = Downloader(company, email)

    def _fetch_url_robust(self, url):
        """Fetch URL using curl if requests fails (bypass Python SSL issues)"""
        headers = {
            'User-Agent': f'{self.company} {self.email}',
            'Accept-Encoding': 'gzip, deflate'
        }
        try:
            import requests
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.content
        except Exception as e:
            print(f"⚠️ Python requests failed: {e}. Trying curl fallback...")
        
        # Curl fallback
        import subprocess
        try:
            cmd = ['curl', '-s', '-L', '-A', f'{self.company} {self.email}', url]
            result = subprocess.run(cmd, capture_output=True, check=True)
            return result.stdout
        except Exception as e:
            print(f"❌ Curl also failed: {e}")
            return None

    def _curl_get(self, url):
        """Standardized curl request for SEC"""
        import subprocess
        import json
        ua = f"{self.company} {self.email}"
        cmd = ['curl', '-s', '-L', '-A', ua, url]
        try:
            result = subprocess.run(cmd, capture_output=True, check=True, timeout=15)
            return result.stdout
        except Exception as e:
            print(f"❌ Curl failed for {url}: {e}")
            return None

    def download_reports(self, ticker: str, output_dir: str):
        """Download reports using curl for robustness"""
        import json
        import os
        import shutil
        ticker = ticker.upper()
        print(f"📥 Fetching US reports for {ticker} using system curl...")
        
        saved_files = []
        
        # Step 1: Find CIK
        ticker_map_url = "https://www.sec.gov/files/company_tickers.json"
        content = self._curl_get(ticker_map_url)
        if not content:
            return []
            
        try:
            tickers_data = json.loads(content.decode('utf-8'))
            cik = None
            for k, v in tickers_data.items():
                if v['ticker'].upper() == ticker:
                    cik = str(v['cik_str']).zfill(10)
                    break
            
            if not cik:
                print(f"❌ Could not find CIK for ticker {ticker}")
                return []
            
            print(f"✅ Found CIK: {cik}")
            
            # Step 2: Get Submissions
            submissions_url = f"https://data.sec.gov/submissions/CIK{cik}.json"
            content = self._curl_get(submissions_url)
            if not content:
                print("❌ Failed to get submissions JSON")
                return []
                
            subs_data = json.loads(content.decode('utf-8'))
            recent_filings = subs_data.get('filings', {}).get('recent', {})
            forms = recent_filings.get('form', [])
            accessions = recent_filings.get('accessionNumber', [])
            primary_docs = recent_filings.get('primaryDocument', [])
            dates = recent_filings.get('reportDate', [])
            
            # Step 3: Filter 10-K and 10-Q (Last 5 10K, last 3 10Q)
            to_download = []
            for i, form in enumerate(forms):
                if form == '10-K' and len([x for x in to_download if x['form'] == '10-K']) < 5:
                    to_download.append({'form': '10-K', 'acc': accessions[i], 'doc': primary_docs[i], 'date': dates[i]})
                elif form == '10-Q' and len([x for x in to_download if x['form'] == '10-Q']) < 3:
                    to_download.append({'form': '10-Q', 'acc': accessions[i], 'doc': primary_docs[i], 'date': dates[i]})
            
            # Step 4: Download
            import time
            for item in to_download:
                time.sleep(0.5)  # Be respectful to SEC rate limits
                acc_clean = item['acc'].replace("-", "")
                doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_clean}/{item['doc']}"
                
                filename = f"{ticker}_{item['form']}_{item['date']}.html"
                dest_path = os.path.join(output_dir, filename)
                
                print(f"   Downloading {item['form']} ({item['date']})...")
                html_content = self._curl_get(doc_url)
                if not html_content:
                    continue
                    
                with open(dest_path, "wb") as f:
                    f.write(html_content)
                saved_files.append(dest_path)
                
                # Convert to MD
                md_path = dest_path.replace(".html", ".md")
                try:
                    from markdownify import markdownify as md_func
                    markdown_content = md_func(html_content.decode('utf-8', errors='ignore'))
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(markdown_content)
                    saved_files.append(md_path)
                except Exception as e:
                    print(f"   Markdown conversion failed for {filename}: {e}")
                    
        except Exception as e:
            print(f"❌ Download process error: {e}")
            
        return saved_files

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("output")
    args = parser.parse_args()
    
    downloader = USStockDownloader()
    downloader.download_reports(args.ticker, args.output)
