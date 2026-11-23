# Agent Note: 全站附件与文件安全在线预览（Issue #48 F1）

Status: implemented

## Problem

- 全站 7 处文件上传目前没有任何站内在线预览能力：原始数据集文件只能强制下载（`as_attachment=True`），采购/报销附件、知识库版本、组会附件和成果全文 PDF 只提供新标签页链接，在手机微信浏览器里反复跳出体验较差，也不能快速浏览实验 CSV 波形头或代码片段。
- 直接内联用户上传文件存在两类隐患：一是 `.svg`/`.html`/`.xml` 可能在同源下执行脚本（存储型 XSS）；二是 `infra/nginx.site.inc` 全局设置了 `X-Frame-Options: DENY`，直接把 `/api/...` 塞进 `<iframe>` 预览 PDF 在生产环境会被拦截；三是原始波形 CSV 动辄几十到数百 MB，全量读入内存会拖垮浏览器或 Gunicorn。

## Decision

- **后端安全预览模块（`backend/core/preview.py` + `DataFileViewSet.preview`）**：
  - 显式白名单分类：图片（`.png/.jpg/.jpeg/.gif/.webp`，**严格排除 `.svg`**）、PDF（`.pdf`）、纯文本/波形 CSV/代码（`.csv/.tsv/.txt/.md/.json/.yaml/.yml/.log/.py/.m/.c/.h/.cpp/.ini/.toml`）；其余类型归为 `other`，任何时候都不内联（请求 `?raw=1` 返回 415 `unsupported_preview`）。
  - 新增 `GET /api/files/{id}/preview/`（沿用 `DataFileViewSet` 个人/本组导师权限与外组 404）：
    - 文本/CSV 类：最多读取 256 KB、最多返回前 200 行，自动尝试 `utf-8-sig` → `gb18030`（兼容 Windows 实验室仪器导出的中文 GBK CSV）→ `utf-8` 容错解码，返回 `{kind, format, name, size, truncated, lines, content}` 并带 `Cache-Control: private, no-store`。
    - 图片/PDF 类带 `?raw=1`：内联返回显式 MIME，附带 `Cache-Control: private, no-store`、`X-Content-Type-Options: nosniff` 和 `Content-Security-Policy`（图片加 `sandbox`，PDF 限 `frame-ancestors 'self'`）；底层文件缺失返回 404。
  - `DataFileSerializer` 增加 `preview_url` 和 `preview_kind`；原有 `/download/` 强制下载行为不变。
- **前端共用 `FilePreviewDialog.vue` 与 `utils/preview.ts`**：
  - 图片直接以 `<el-image>` 展示并支持全屏缩放/旋转灯箱；
  - PDF 通过同源 `fetch` 拿字节流转为本地 `blob:` URL 渲染在 `<iframe>` 中（天然不受 Nginx `X-Frame-Options: DENY` 拦截，关闭弹窗与组件卸载时主动 `URL.revokeObjectURL`），设置 20 MB 弹窗预览上限（同时校验 `target.size`、`Content-Length` 与流式累加字节数，超限立即中止流并回退「新窗口打开 / 下载文件」，避免大 PDF 整份读入内存）；所有预览请求绑定 `AbortController` 与流 `reader.cancel()`，关闭弹窗或切换文件立即取消下载；
  - CSV/TSV 使用零依赖单趟 RFC-4180 状态机解析器（支持带引号跨行单元格、转义双引号 `""` 与 CRLF/LF，表格单元格 `white-space: pre-wrap` 保留换行），提供"表格 / 原文"分段切换；非数据集的直链文本文件（知识库、组会）通过 `ReadableStream` 读满 256 KB 即主动 `cancel()` 截断流，避免缓冲大文件。直链附件与数据集使用同一解码顺序；截断落在多字节字符中间时，只显示完整字符。
  - 接入全站入口：`AttachmentList.vue`（同时覆盖采购申请、报销与组会，图片附件显示小缩略图）、`DatasetDetailView.vue`、`KnowledgeView.vue`、`AchievementsView.vue`。

## Alternatives considered

- **把 `infra/nginx.site.inc` 的 `X-Frame-Options` 改成 `SAMEORIGIN` 直接嵌 `/api/...`**：会放宽全站所有页面被同源嵌套的约束，且仍需要区分 PDF 和普通接口。改由前端 `fetch` 转 `blob:` 既零 Nginx 改动，又让 PDF 预览在开发和生产环境行为完全一致。
- **引入 `pdfjs-dist` / `papaparse` 等第三方前端包**：违背最少依赖原则，且会显著增加打包体积与 `package-lock.json` 维护负担；原生浏览器 PDF 预览 + 50 行 RFC-4180 CSV 解析器已足够稳定。
- **在后端把所有文件下载端点都改成 `?inline=1`**：容易与正在并行修复下载/删除竞态的改动冲突；集中新增 `core/preview.py` 和 `DataFileViewSet.preview`，其余模块复用已有直链 + 前端流式截断即可全站生效。

## Consequences

- 采购/报销发票、知识库规程、组会文档、论文 PDF、数据集图片与波形 CSV/代码均可直接在站内弹窗预览，同时保留下载与新窗口打开入口；`.svg` / `.html` 等活跃类型始终禁止内联。
- 手机微信内置浏览器对 `blob:` PDF `<iframe>` 支持不一，右上角提供"新窗口打开"与"下载文件"兜底。
- 验证：
  - `scripts/check_module_deps.py`：0 violation。
  - `scripts/check.sh`：决策笔记校验通过（75 notes）；`makemigrations --check` 无待生成迁移；后端 `pytest` 510 passed, 1 skipped；前端 `vitest` 50 个测试文件 179 passed（含跨行 CSV 解析与渲染、大 PDF 大小/流式上限保护、关闭弹窗中止请求回归测试）；`vue-tsc --noEmit && vite build` 通过。
  - 浏览器（`verify-lab`）：已在隔离实例实测通过（2 条跨行 CSV 记录正确渲染为 2 行表格、关闭弹窗实测中止在途 PDF 请求、24 MB `Content-Length` PDF 触发 20 MB 上限回退不建 `blob:`、正常 PDF 通过 `blob:` `<iframe>` 渲染，`query.sh` 核对 `DataFile`），证据在 `backend/var/verify-evidence/2026-11-23-pr51-file-preview/`。
