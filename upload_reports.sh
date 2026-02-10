#!/bin/bash

# 世纪华通财报上传脚本

REPORTS_DIR="/var/folders/kw/hrp2jwq55r7bz4tr0sx5yq1m0000gn/T/cninfo_reports_29o5ty4x"
NOTEBOOK_TITLE="世纪华通 财务报告"
NOTEBOOKLM="/opt/homebrew/bin/notebooklm"

echo "📚 Creating notebook: $NOTEBOOK_TITLE"

# 创建笔记本并获取 ID
NOTEBOOK_ID=$($NOTEBOOKLM create "$NOTEBOOK_TITLE" 2>&1 | grep -oE '[a-f0-9-]{36}' | head -1)

if [ -z "$NOTEBOOK_ID" ]; then
    echo "❌ Failed to create notebook"
    exit 1
fi

echo "✅ Created notebook: $NOTEBOOK_ID"
echo ""

# 设置当前笔记本
$NOTEBOOKLM use "$NOTEBOOK_ID"

# 上传所有 PDF 文件
echo "📤 Uploading PDF files..."
UPLOADED=0
FAILED=0

for pdf in "$REPORTS_DIR"/*.pdf; do
    filename=$(basename "$pdf")
    echo "   Uploading: $filename"
    
    if $NOTEBOOKLM source add "$pdf" 2>&1 | grep -q "success\|Added\|uploaded"; then
        echo "   ✅ Uploaded: $filename"
        ((UPLOADED++))
    else
        echo "   ❌ Failed: $filename"
        ((FAILED++))
    fi
done

echo ""
echo "=================================================="
echo "✅ Uploaded: $UPLOADED files"
if [ $FAILED -gt 0 ]; then
    echo "❌ Failed: $FAILED files"
fi
echo "📚 Notebook: $NOTEBOOK_TITLE"
echo "🆔 ID: $NOTEBOOK_ID"
echo "🔗 URL: https://notebooklm.google.com/notebook/$NOTEBOOK_ID"
echo "=================================================="
