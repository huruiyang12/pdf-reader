# 在线 PDF 阅读器架构设计

## 系统目标
为超级管理员、注册管理员与普通访客提供安全的 PDF 上传、分享、浏览体验：
- 兼容桌面与移动端的响应式阅读器。
- 支持试读与浏览两种分享模式。
- 分享访问需水印、防下载、防复制、防打印。
- 管理员具备文档管理、分享记录可视化与权限隔离。

## 总体架构
```
[Web 客户端 (Admin SPA / Reader SPA)]
        ↕ HTTPS + JWT / Magic Link
[API 网关 / BFF (Node.js + NestJS/Express)]
        ↕ gRPC/REST
[服务层]
  • Auth 服务：注册、登录、邮箱验证码、会话/Token、RBAC
  • Document 服务：PDF 上传、元数据、访问控制、转换与分片
  • Share 服务：分享链接生成、试读/浏览策略、水印模板
  • Audit 服务：访问日志、下载/打印拦截事件、风控
  • Notification 服务：邮件发送、Magic Link 验证
        ↕
[对象存储 (S3 兼容/OSS) + 数据库 (PostgreSQL)]
        ↕
[缓存/消息队列 (Redis / SQS)]
```

### 关键技术选型
- **前端**：React + Next.js 或 Vite + React，TailwindCSS/Chakra 实现响应式；PDF.js 渲染；Service Worker 控制缓存；PWA 便于移动端适配。
- **后端**：Node.js (NestJS/Express)；PostgreSQL + Prisma/TypeORM；Redis 缓存验证码、会话；对象存储保存原始 PDF 与渲染切片；Nodemailer/邮件网关发送验证邮件。
- **认证与权限**：邮箱验证码 + Magic Link 登录；JWT + 刷新 Token；RBAC（超级管理员、注册管理员、访客）。
- **部署**：Docker 化；Nginx 反向代理 + HTTPS；CI/CD（GitHub Actions）自动测试与构建。

## 数据模型
- `users`：id, role (super_admin / admin / viewer), name, email, password_hash(仅管理员), status, created_at。
- `documents`：id, owner_id, title, description, storage_key, page_count, checksum, status, created_at。
- `shares`：id, document_id, mode (preview/browse), preview_page_limit, recipient_name, recipient_email, expires_at, watermark_text, created_by, created_at。
- `access_tokens`：share_id, token (一次性/多次), used_at, device_info, ip。
- `audit_logs`：user/share/doc 维度的访问、拦截、打印尝试等事件。

## 业务流程
### 管理员注册/登录
1. 注册管理员提交邮箱、姓名，收到验证码/魔法链接。
2. 超级管理员可在后台升级角色或禁用账户。
3. 登录成功后颁发短期 JWT + 长期刷新 Token，绑定设备指纹（可选）。

### 上传文档
1. 管理员在后台发起上传，前端先调用后端申请 **预签名 URL**。
2. 上传完成后回调 Document 服务：校验文件类型、大小、MD5；调用 PDF 解析获取页数；生成水印模板；将元数据入库。
3. 可选：异步生成页面缩略图与分片（图像/加密 blob）。

### 创建分享
- **试读模式**：设置可试读页数，生成公开短链（含 share_id）。
- **浏览模式**：填写接收者姓名、邮箱；服务端生成一次性或限次 Token，邮件发送魔法链接（含签名 Token）。
- 记录分享创建者、过期时间、访问限制（IP/设备/次数）。

### 访客访问
- **浏览模式**：
  1. 用户点击邮件魔法链接，后端校验 Token、设备、有效期，创建会话 Cookie/JWT（仅阅读权限）。
  2. 前端加载阅读器，使用 **流式接口** 获取单页渲染资源。
  3. 读取水印模板，按姓名 + 提示文字生成全屏半透明水印。
- **试读模式**：无需认证，后端仅返回前 `N` 页的渲染资源，其余页返回 403/已隐藏提示。

## PDF 渲染与防护
- **渲染策略**：
  - 服务端将 PDF 转换为 **按页分片的加密二进制或栅格图像**（如 PNG/WebP）或使用 pdf.js 的 range 请求仅暴露前 N 页；
  - 前端通过授权接口分页拉取，每页附带短时签名 URL/Token；
  - 开启 CORS 白名单、禁止缓存头、Referer 校验。
- **水印**：
  - CSS/Canvas 双水印：重复背景 + Canvas 绘制，随滚动同步；
  - 内容包含用户姓名、邮箱（或“试读”字样）和追踪 ID；
  - 服务端也可在渲染时将水印写入图像，防止 DOM 移除。
- **防下载/防复制/防打印**：
  - 前端禁用右键、键盘打印快捷键、Selection/Ctrl+C 监听；
  - PDF 以分片图像或加密 blob 流式送达，避免直接获取完整源文件；
  - `Content-Disposition: inline` + `X-Frame-Options/SameSite` 等头；
  - Service Worker 拦截打印/下载路由，若检测到 `window.print` 调用则上报并阻断；
  - 后端网关对 `Range`/`Referer`/`User-Agent` 异常进行风控。

## API 设计概览
### Auth & User
- `POST /api/auth/register`：注册管理员（邮箱验证码）。
- `POST /api/auth/login`：管理员登录。
- `POST /api/auth/magic-link`：生成浏览模式邮件链接。
- `POST /api/auth/verify`：验证验证码/Token，颁发会话。

### Document
- `POST /api/documents/presign`：获取上传预签名 URL。
- `POST /api/documents`：上传完成回调，入库 & 解析。
- `GET /api/documents/:id`：获取文档详情与缩略图。
- `DELETE /api/documents/:id`：删除/下架。

### Share
- `POST /api/shares`：创建试读/浏览分享。
- `GET /api/shares/:id`：查询分享状态（后台）。
- `POST /api/shares/:id/access`：访客兑换 Token（浏览模式）。

### Reader
- `GET /api/reader/:shareId/pages/:page`：获取指定页渲染（签名/短时 Token）。
- `GET /api/reader/:shareId/manifest`：获取可读页范围、总页数、水印文本。
- `POST /api/reader/:shareId/audit`：上报拦截事件/打印尝试。

## 后台管理界面（Admin UI）
- 登录/注册/重置密码。
- 文档列表：上传、删除、状态、页数、更新时间。
- 分享管理：模式、过期时间、收件人、访问次数、复制短链。
- 访问审计：打印/下载拦截、异常 IP、设备信息。
- 响应式布局：侧边导航在移动端折叠，主要表格支持横向滚动。

## 阅读器界面（Reader UI）
- 全屏容器，顶部极简工具栏：上一页/下一页、缩放、页码输入、全屏。
- 试读模式：仅展示前 N 页，其余页显示“需要授权”提示。
- 浏览模式：加载水印（姓名 + 提示），禁止打印/下载按钮，右键 & 选中拦截。
- 移动端：手势翻页、双指缩放、底部浮动工具栏。

## 安全与合规
- 所有接口强制 HTTPS，HSTS；CSRF 防护（同站 Cookie + CSRF Token 或 Bearer）。
- 速率限制与 IP 黑名单；验证码/邮件防爆破；
- 所有 Token 具备过期、设备绑定、单次使用配置；
- 审计日志持久化，管理员操作需双重确认；
- 隐私数据（邮箱、姓名）按需脱敏返回；
- 定期轮换预签名密钥与邮件签名秘钥。

## 可观测性与运维
- 日志：结构化（JSON），区分访问日志、审计日志、安全事件。
- Metrics：接口延迟、失败率、验证码发送成功率、打印拦截次数。
- Tracing：OpenTelemetry；
- 灰度/回滚：蓝绿或金丝雀发布。

## 迭代建议
1. MVP：管理员上传、试读分享、浏览模式邮件认证 + 基础水印。
2. 强化安全：服务端水印烙印、打印拦截、风控策略。
3. 体验优化：PWA、离线缓存白名单、深色模式、可视化报表。
4. 企业化：多租户隔离、SAML/LDAP、审计导出、Webhooks。
