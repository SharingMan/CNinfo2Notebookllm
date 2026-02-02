# � CNinfo to NotebookLM

自动下载中国 A 股上市公司年报/季报，并上传至 Google NotebookLM 进行 AI 驱动的深度财务分析。

> 💡 **注**：本工具会自动为 NotebookLM 配置基于《手把手教你读财报》方法论的专业“财务分析师”角色，帮助你进行财务排雷和估值分析。

## ✨ 核心功能

- 📥 **智能下载**: 自动抓取近 5 年年报 + 当年所有定期报告（一季报/中报/三季报）。
- 🤖 **AI 分析师角色**: 自动植入专业 System Prompt，进行排雷、估值和击球区判断。
- 📦 **全自动工作流**: 一键完成下载、笔记本创建、角色配置和文件上传。
- 🧹 **自动清理**: 上传后自动清理临时 PDF 文件，保持磁盘整洁。
- 🔐 **稳定鉴权**: 使用 `notebooklm-py` 配合浏览器自动化登录，解决 Cookie 过期问题。

## 🎯 作为 Claude Skill 使用 (推荐)

### 安装

```bash
# 1. 进入你的 skills 目录 (例如 ~/.gemini/antigravity/skills)
cd ~/.gemini/antigravity/skills

# 2. 克隆仓库
git clone https://github.com/jarodise/CNinfo2Notebookllm.git cninfo-to-notebooklm

# 3. 安装依赖
cd cninfo-to-notebooklm
pip install -r requirements.txt
playwright install chromium

# 4. 完成初始登录 (仅需一次)
notebooklm login
```

### 使用方法

直接告诉 Claude Code：

```text
使用 cninfo-to-notebooklm 技能分析 600519
```

或者

```text
运行 cninfo-to-notebooklm 分析平安银行
```

Claude 将会自动：

1. 查找股票代码（如果提供的是名称）
2. 下载相关历史财报
3. 创建并配置 NotebookLM 笔记本
4. 上传所有 PDF 文件
5. 返回笔记本链接

---

## 🛠️ 手动使用

你也可以直接在终端运行脚本：

```bash
# 按股票代码分析
python3 scripts/run.py 000519

# 按股票名称分析
python3 scripts/run.py "贵州茅台"
```

## 📂 项目结构

```
cninfo-to-notebooklm/
├── skill.yaml          # Skill 定义文件
├── package.json        # 项目元数据
├── SKILL.md            # LLM 指令文档
├── scripts/
│   ├── run.py          # 主流程控制
│   ├── download.py     # 巨潮资讯下载逻辑
│   └── upload.py       # NotebookLM 交互逻辑
└── assets/
    ├── financial_analyst_prompt.txt  # AI 分析师 Prompt
    └── stocks.json                   # A股股票数据库
```

## 🔧 配置

“财务分析师”的角色定义在 `assets/financial_analyst_prompt.txt` 文件中。你可以修改此文件来定制 AI 分析财报的逻辑和关注点。

## ⚠️ 免责声明

本工具仅供教育和研究使用。请确保遵守巨潮资讯网 (cninfo.com.cn) 和 Google NotebookLM 的服务条款。AI 角色提供的财务分析仅供参考，不构成专业投资建议。
