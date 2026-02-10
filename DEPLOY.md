# 财报AI助手 - 云端部署指南

## 🚀 部署方式

### 方式一：Railway（推荐）

Railway 提供免费额度，适合个人使用。

#### 步骤：

1. **Fork/推送代码到 GitHub**
   ```bash
   git add .
   git commit -m "添加云端部署配置"
   git push origin master
   ```

2. **在 Railway 部署**
   - 访问 [railway.app](https://railway.app)
   - 点击 "New Project" → "Deploy from GitHub repo"
   - 选择你的仓库
   - Railway 会自动读取 `railway.json` 和 `Dockerfile`

3. **获取域名**
   - 部署完成后，Railway 会自动分配域名
   - 例如：`https://cninfo2notebooklm-production.up.railway.app`

#### 环境变量（可选）

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PORT` | 8000 | 服务端口 |
| `HOST` | 127.0.0.1 | 绑定地址（Railway 不需要修改）|

---

### 方式二：Render

Render 也提供免费部署。

1. 访问 [render.com](https://render.com)
2. New Web Service → 连接 GitHub 仓库
3. 选择 Docker 环境
4. 自动部署

---

### 方式三：Vercel（仅静态页面）

⚠️ Vercel 不支持 Python 后端长时间运行，不推荐。

---

## 🔧 本地测试 Docker

```bash
# 构建镜像
docker build -t 财报ai助手 .

# 运行容器
docker run -p 8000:8000 财报ai助手

# 访问 http://localhost:8000
```

---

## ⚠️ 云端部署注意事项

### 文件存储
- 云端环境是临时的，下载的财报文件会随容器重启而丢失
- 建议配合云存储使用（如 AWS S3、阿里云 OSS）

### NotebookLM 登录
- 云端部署后，NotebookLM 登录需要浏览器支持
- 可能需要手动上传功能替代自动上传

### 搜索功能
- A 股搜索功能需要 `assets/stocks.json` 文件
- 已包含在仓库中，无需额外配置

---

## 📝 更新日志

- 2026-02-10: 添加 Railway 部署配置
