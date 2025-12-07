# Secure PDF Reader (Demo)

一个简单的 FastAPI + 前端示例，覆盖管理员上传、分享（试读/浏览模式）与受控阅读界面。

## 快速开始
1. 安装依赖
   ```bash
   pip install -r requirements.txt
   ```
2. 启动服务
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```
3. 打开浏览器访问 [http://localhost:8000](http://localhost:8000) 进入管理员界面。

> 默认使用本地 `app.db` 和 `uploads/` 目录，可通过环境变量 `DATABASE_URL`、`UPLOAD_DIR` 自定义。

## 功能概览
- **管理员后台**：上传 PDF、生成分享链接（试读/浏览）、查看分享记录。
- **试读模式**：无需验证，前 N 页可读，前端限制渲染页数并附带水印。
- **浏览模式**：需验证码验证后才能打开，页面全屏水印、禁用复制/打印快捷键。

## 目录
- `app/main.py`：FastAPI 入口，提供上传/分享/验证/阅读接口。
- `app/db.py`：SQLite 数据模型与初始化。
- `templates/`：管理员、验证、阅读页模板，阅读页使用 pdf.js CDN 渲染。
- `uploads/`：上传的 PDF 存储路径（启动前自动创建）。

## 安全与局限
本示例用于演示核心流程，未包含真正的邮件发送、DRM 或强力防复制能力，生产环境需配合后端签名 URL、审计日志、前端强水印/加密与反调试手段加强。
