# API 详细设计（草案）

> 规范：RESTful JSON，所有受保护接口需 Bearer JWT；管理端与访客端使用不同的权限作用域。时间使用 ISO8601，金额/计数用整数，分页采用 `page` + `page_size`。

## 认证与授权
### POST /api/auth/register
- **用途**：注册成为“注册管理员”。
- **权限**：公开。
- **入参**：`{ name, email, password, captcha_token }`
- **返回**：`{ user_id, verify_token_expires_at }`
- **说明**：发送邮箱验证码/魔法链接，状态为 pending。

### POST /api/auth/verify
- **用途**：验证邮箱验证码或魔法链接 token。
- **入参**：`{ email, code | token, device_fingerprint }`
- **返回**：`{ access_token, refresh_token, role }`

### POST /api/auth/login
- **用途**：管理员登录。
- **入参**：`{ email, password }`
- **返回**：`{ access_token, refresh_token, role }`

### POST /api/auth/refresh
- **用途**：刷新 Token。
- **入参**：`{ refresh_token }`
- **返回**：`{ access_token, refresh_token }`

### POST /api/auth/magic-link
- **用途**：浏览模式分享时，为指定收件人生成验证邮件。
- **权限**：管理员。
- **入参**：`{ share_id, recipient_email }`
- **返回**：`{ sent: true }`

## 文档管理
### POST /api/documents/presign
- **用途**：获取上传 PDF 的预签名 URL。
- **权限**：管理员。
- **入参**：`{ filename, content_type, size }`
- **返回**：`{ upload_url, storage_key, expires_at, headers }`

### POST /api/documents
- **用途**：上传回调，写入数据库并解析页数。
- **入参**：`{ storage_key, title, description }`
- **返回**：`{ document_id, page_count }`

### GET /api/documents
- **用途**：分页获取文档列表。
- **入参**：查询参数 `page`, `page_size`, `keyword`。
- **返回**：`{ items:[{id,title,page_count,status,updated_at}], total }`

### GET /api/documents/:id
- **用途**：获取文档详情、缩略图、分享列表。
- **返回**：`{ id,title,description,page_count,created_at,shares:[...] }`

### DELETE /api/documents/:id
- **用途**：删除或下架文档，保留审计记录。

## 分享管理
### POST /api/shares
- **用途**：创建分享链接。
- **权限**：管理员。
- **入参**：
  - 试读模式：`{ document_id, mode:"preview", preview_page_limit, expires_at }`
  - 浏览模式：`{ document_id, mode:"browse", recipient_name, recipient_email, expires_at, watermark_text? }`
- **返回**：`{ share_id, link, expires_at }`

### GET /api/shares
- **用途**：分页查询分享记录。
- **返回**：`{ items:[{id,document_id,mode,recipient_email,expires_at,access_count}], total }`

### GET /api/shares/:id
- **用途**：获取单个分享详情。

### POST /api/shares/:id/revoke
- **用途**：撤销分享。

## 访客访问
### POST /api/shares/:id/access
- **用途**：访客使用验证码/魔法链接换取阅读 Token（浏览模式）。
- **入参**：`{ code | token, device_fingerprint }`
- **返回**：`{ reader_token, watermark_text, allowed_pages }`

### GET /api/reader/:shareId/manifest
- **用途**：获取可访问页范围、总页数、缩略信息。
- **鉴权**：
  - 试读模式：无需鉴权。
  - 浏览模式：`Authorization: Bearer reader_token`。
- **返回**：`{ total_pages, allowed_pages:[1..N], watermark_text }`

### GET /api/reader/:shareId/pages/:page
- **用途**：按页拉取渲染数据。
- **返回**：`{ url | binary_stream, mime, expires_at }`
- **规则**：超出 `allowed_pages` 返回 403。

### POST /api/reader/:shareId/audit
- **用途**：上报打印、下载、截图检测、异常操作。
- **入参**：`{ event, page?, user_agent, ip }`

## 安全与速率限制
- 每个 IP 对验证码、魔法链接、上传均有限流（如 5/minute）。
- 访客端 Token 绑定设备指纹与浏览器 UA，频繁变更需重新认证。
- 管理员操作（删除、撤销分享）需 OTP 二次确认。
- 关键响应头：`Cache-Control: no-store`, `Content-Security-Policy` 禁止内嵌外部脚本、`X-Frame-Options: DENY`（阅读器页面白名单除外）。

## 错误规范
- 统一返回：`{ code, message, trace_id }`；
- 常见错误码：
  - `AUTH_INVALID_CODE`, `AUTH_EXPIRED`, `RATE_LIMITED`
  - `DOC_INVALID_TYPE`, `DOC_TOO_LARGE`, `DOC_NOT_FOUND`
  - `SHARE_EXPIRED`, `SHARE_REVOKED`, `PAGE_FORBIDDEN`
  - `INTERNAL_ERROR`

## 事件与审计
- 事件表 `audit_logs` 记录：
  - 登录、注册、验证码验证；
  - 文档上传/删除、分享创建/撤销；
  - 访客访问、超页访问、打印/下载拦截、异常 UA/IP。
- 提供后台导出 CSV/JSON 与图表接口（未来迭代）。
