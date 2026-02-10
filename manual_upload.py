#!/usr/bin/env python3
"""
手动上传财报到 NotebookLM
"""
import sys
import os
import glob
from pathlib import Path

# 使用 notebooklm-py 的 Python API
from notebooklm import NotebookLMClient
from notebooklm.auth import BrowserAuth

def main():
    if len(sys.argv) < 2:
        print("Usage: python3.11 manual_upload.py <reports_directory>")
        sys.exit(1)
    
    reports_dir = sys.argv[1]
    
    # 查找所有 PDF 文件
    pdf_files = glob.glob(os.path.join(reports_dir, "*.pdf"))
    
    if not pdf_files:
        print(f"❌ No PDF files found in {reports_dir}")
        sys.exit(1)
    
    print(f"📁 Found {len(pdf_files)} PDF files")
    for pdf in pdf_files:
        print(f"   - {os.path.basename(pdf)}")
    
    # 使用浏览器认证
    print("\n🔐 Authenticating with NotebookLM...")
    auth = BrowserAuth()
    client = NotebookLMClient(auth=auth)
    
    # 创建笔记本
    notebook_title = "世纪华通 财务报告"
    print(f"\n📚 Creating notebook: {notebook_title}")
    
    try:
        notebook = client.create_notebook(title=notebook_title)
        notebook_id = notebook.id
        print(f"✅ Created notebook: {notebook_id}")
    except Exception as e:
        print(f"❌ Failed to create notebook: {e}")
        sys.exit(1)
    
    # 上传文件
    print(f"\n📤 Uploading {len(pdf_files)} files...")
    uploaded = 0
    failed = 0
    
    for pdf_file in pdf_files:
        filename = os.path.basename(pdf_file)
        print(f"   Uploading: {filename}...")
        
        try:
            with open(pdf_file, 'rb') as f:
                source = client.add_source(
                    notebook_id=notebook_id,
                    file=f,
                    filename=filename
                )
            print(f"   ✅ Uploaded: {filename}")
            uploaded += 1
        except Exception as e:
            print(f"   ❌ Failed: {filename} - {e}")
            failed += 1
    
    # 配置 AI 分析师角色
    print(f"\n⚙️ Configuring AI Financial Analyst...")
    prompt_file = "assets/financial_analyst_prompt.txt"
    
    if os.path.exists(prompt_file):
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt = f.read()
            
            client.configure_notebook(
                notebook_id=notebook_id,
                persona=prompt,
                response_length="longer"
            )
            print("✅ AI Analyst configured")
        except Exception as e:
            print(f"⚠️ Failed to configure: {e}")
    
    # 总结
    print(f"\n{'='*50}")
    print(f"✅ Uploaded: {uploaded} files")
    if failed > 0:
        print(f"❌ Failed: {failed} files")
    print(f"📚 Notebook: {notebook_title}")
    print(f"🆔 ID: {notebook_id}")
    print(f"🔗 URL: https://notebooklm.google.com/notebook/{notebook_id}")
    print(f"{'='*50}")

if __name__ == "__main__":
    main()
