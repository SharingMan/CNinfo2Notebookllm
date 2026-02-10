#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload PDF files to NotebookLM using notebooklm-py CLI
Stores PDFs in temporary directory, outputs file paths for upload
Optimized for speed and reliability.
"""

import sys
import os
import subprocess
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from tenacity import retry, stop_after_attempt, wait_exponential

try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, total=None, desc=""): self.total = total
        def update(self, n=1): pass
        def set_description(self, desc): pass
        def close(self): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass


def get_notebooklm_cmd() -> str:
    """Find the notebooklm CLI command"""
    cmd = shutil.which("notebooklm")
    if cmd:
        return cmd
    
    # Common fallback paths
    fallbacks = [
        "/opt/homebrew/bin/notebooklm",
        "/usr/local/bin/notebooklm",
        os.path.expanduser("~/.local/bin/notebooklm")
    ]
    for p in fallbacks:
        if os.path.exists(p):
            return p
    return "notebooklm"


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=2, min=4, max=20)
)
def run_notebooklm_command(args: list) -> tuple:
    """Run notebooklm command and return (success, output) with retries"""
    notebooklm_cmd = get_notebooklm_cmd()
    try:
        result = subprocess.run(
            [notebooklm_cmd] + args, capture_output=True, text=True, timeout=180
        )
        return result.returncode == 0, result.stdout + result.stderr
    except Exception as e:
        return False, str(e)


def create_notebook(title: str) -> str:
    """Create a new NotebookLM notebook, returns notebook ID or None"""
    print(f"📚 Creating notebook: {title}")
    success, output = run_notebooklm_command(["create", title])

    if not success:
        print(f"❌ Failed to create notebook: {output}", file=sys.stderr)
        return None

    # Parse output to find notebook ID
    import re
    match = re.search(r"([a-f0-9-]{36})", output)
    if match:
        notebook_id = match.group(1)
        print(f"✅ Created notebook ID: {notebook_id}")
        return notebook_id

    # Fallback parsing
    lines = output.split("\n")
    for line in lines:
        if "ID:" in line or "id:" in line:
            parts = line.split(":")
            if len(parts) > 1:
                return parts[1].strip()
    
    return None


def upload_source_worker(notebook_id: str, file_path: str) -> bool:
    """Worker function for parallel upload"""
    # Use --notebook to avoid 'use' context switching in parallel
    success, output = run_notebooklm_command(["source", "add", file_path, "--notebook", notebook_id])
    return success


def upload_all_sources(notebook_id: str, files: list, max_workers: int = 3) -> dict:
    """Upload multiple files to a notebook in parallel"""
    results = {"success": [], "failed": []}
    
    print(f"📤 Uploading {len(files)} sources to NotebookLM...")
    
    with tqdm(total=len(files), desc="📤 Uploading") as pbar:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(upload_source_worker, notebook_id, f): f 
                for f in files
            }
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    if future.result():
                        results["success"].append(file_path)
                    else:
                        results["failed"].append(file_path)
                except Exception:
                    results["failed"].append(file_path)
                pbar.update(1)

    return results


def cleanup_temp_files(files: list, temp_dir: str = None):
    """Remove temporary files after upload"""
    for f in files:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass

    if temp_dir and os.path.exists(temp_dir):
        # Only cleanup if it looks like a temporary directory
        if any(x in temp_dir for x in ["/tmp/", "/var/folders/", "cninfo_reports_"]):
            try:
                shutil.rmtree(temp_dir)
                print(f"🧹 Cleaned up temp directory: {temp_dir}")
            except Exception:
                pass


def configure_notebook(notebook_id: str, prompt_file: str) -> bool:
    """Configure notebook with custom prompt"""
    if not os.path.exists(prompt_file):
        print(f"⚠️ Prompt file not found: {prompt_file}")
        return False

    try:
        with open(prompt_file, "r", encoding="utf-8") as f:
            prompt = f.read()
    except Exception as e:
        print(f"❌ Error reading prompt file: {e}")
        return False

    print(f"⚙️ Configuring notebook persona...")
    success, output = run_notebooklm_command(
        [
            "configure",
            "--notebook",
            notebook_id,
            "--persona",
            prompt,
            "--response-length",
            "longer",
        ]
    )

    if success:
        print(f"   ✅ Configuration successful")
        return True
    else:
        print(f"   ❌ Configuration failed: {output}", file=sys.stderr)
        return False


def main():
    """Main entry point"""
    if len(sys.argv) < 3:
        print("Usage: python upload.py <notebook_title> <pdf_file1> [pdf_file2] ...")
        print("       python upload.py <notebook_title> --json <json_file>")
        sys.exit(1)

    notebook_title = sys.argv[1]
    files = []
    temp_dir = None

    if sys.argv[2] == "--json":
        json_file = sys.argv[3]
        with open(json_file, "r") as f:
            data = json.load(f)
        files = data.get("files", [])
        temp_dir = data.get("output_dir")
        stock_name = data.get('stock_name', notebook_title)
        notebook_title = f"{stock_name} 财务报告"
    else:
        files = sys.argv[2:]

    if not files:
        print("❌ No files to upload")
        sys.exit(1)

    notebook_id = create_notebook(notebook_title)
    if not notebook_id:
        sys.exit(1)

    results = upload_all_sources(notebook_id, files)

    print(f"\n{'=' * 50}")
    print(f"✅ Uploaded: {len(results['success'])} files")
    if results["failed"]:
        print(f"❌ Failed: {len(results['failed'])} files")
    print(f"📚 Notebook: {notebook_title}")
    print(f"🆔 ID: {notebook_id}")

    if temp_dir:
        cleanup_temp_files(files, temp_dir)

    result_json = {
        "notebook_id": notebook_id,
        "notebook_title": notebook_title,
        "uploaded": len(results["success"]),
        "failed": len(results["failed"]),
    }
    print("\n---JSON_OUTPUT---")
    print(json.dumps(result_json, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
