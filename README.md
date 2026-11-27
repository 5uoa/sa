# sa · xf AI 协作工作台

`sa` 是一个由 FastAPI 后端、Vue 3 管理端和 Nuxt 4 站点组成的 AI 协作工作台。项目覆盖管理后台、专家与工作台、项目/任务协作、总管式多步执行、模型与 MCP 工具管理、配额、审计日志和附件上传。

所有运行密钥、数据库密码、JWT 密钥和测试账号都通过环境变量或本地 `.env` 注入，不进入 Git。

## 核心能力

- **管理后台**：成员、项目、专家、模型、MCP、Skill、配额和操作日志。
- **AI 工作台**：多会话对话、专家/项目上下文、附件、流式输出、工具调用与人工审批。
- **总管模式**：需求拆解、方案生成、任务规划、执行、回归评估和交付物管理。
- **模型接入**：兼容 OpenAI、Anthropic、Google 及 OpenAI-compatible 接口。
- **安全边界**：角色/权限控制、数据库内密钥加密、MCP 敏感配置加密、操作审计。
- **前台站点**：Nuxt 4 + SEO，支持页面预渲染与静态化部署。

## 目录结构

```text
.
├── admin/                  # 框架后台 API（默认 8000）
├── site/                   # 业务前台 API（默认 8100）
│   ├── admin/              # 管理后台、模型与 MCP 管理
│   ├── chief/              # 总管项目和任务编排
│   ├── experts/            # AI 专家运行时
│   ├── llm/                # 模型适配与能力探测
│   └── upload/             # 附件上传与下载
├── framework/              # 通用 Model / Controller / 认证 / 日志 / Agent 框架
├── front-admin/            # Vue 3 + Element Plus 管理端（Vite，默认 3000）
├── front-site/             # Nuxt 4 前台站点（默认 3000，开发时建议 3100）
├── scripts/                # 初始化与运维脚本
├── tests/                  # Python 测试公共环境加载
├── INIT.SQL                # 框架骨架表
├── 6.DB.sql                # 业务数据表
├── .env.example            # 后端环境变量模板
└── README.md
```

## 环境要求

| 组件 | 建议版本 | 说明 |
| --- | --- | --- |
| Python | 3.12+，当前验证 3.14 | 使用 `.venv` 隔离依赖 |
| PostgreSQL | 16+，当前验证 18 | 需要 `pgcrypto` 扩展 |
| Node.js | 22.22.3+ | `front-site` 已在 `package.json` 中约束 |
| pnpm | 9.x | 用于 `front-site` |
| npm | 随 Node.js | 用于 `front-admin` |

Python 依赖没有随仓库提供全局虚拟环境，可在项目根目录按下面方式安装核心依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install \
  "fastapi>=0.116,<1" "uvicorn[standard]>=0.34,<1" \
  asyncpg PyJWT bcrypt PyYAML python-multipart \
  httpx requests qiniu cryptography tenacity aiohttp openpyxl \
  "openai>=1,<4" "anthropic>=0.60,<3" "google-genai>=1,<3" \
  "mcp>=1,<3" "pydantic>=2,<3" "pydantic-ai-slim>=1,<3" tiktoken
```

PDF/文档转换、语音转写、Redis 缓存等可选能力在运行时才导入对应包；启用相关功能时再安装对应依赖。

## 环境变量

### 后端 `.env`

```bash
cp .env.example .env
```

重点配置：

| 变量 | 用途 |
| --- | --- |
| `PG_HOST` / `PG_PORT` / `PG_DBNAME` / `PG_USER` / `PG_PASSWORD` | PostgreSQL 连接 |
| `APP_HOST` / `APP_PORT` | 框架后台 API 监听地址 |
| `SITE_API_HOST` / `SITE_API_PORT` | 业务前台 API 监听地址 |
| `JWT_SECRET` | 框架后台 JWT 签名密钥 |
| `SITE_ADMIN_JWT_SECRET` | Site 管理后台 JWT 签名密钥 |
| `SITE_SECRET_KEY` | 数据库内模型/MCP 密钥的 AES-GCM 加密种子 |
| `FRAMEWORK_ADMIN_USERNAME` / `FRAMEWORK_ADMIN_PASSWORD` | 首次初始化框架后台管理员 |
| `SITE_ADMIN_EMAIL` / `SITE_ADMIN_INITIAL_PASSWORD` | 首次初始化 Site 管理后台拥有者 |
| `SITE_ADMIN_AUTO_LOGIN` / `SITE_ADMIN_AUTH_DISABLED` | 仅限本地开发，生产必须关闭 |
| `DEFAULT_MODEL_API_KEY` / `VISION_MODEL_API_KEY` | 可选，框架默认模型密钥；业务模型密钥通过后台加密入库 |
| `TAVILY_API_KEY` / `GEWE_API_TOKEN` / `QINIU_*` | 可选外部服务凭据 |
| `TEST_ADMIN_*` / `TEST_USER_*` | Python 与 Playwright 测试账号 |

生成随机密钥：

```bash
openssl rand -base64 32
```

注意：

- 项目根 `.env` 是后端配置的唯一推荐入口，`admin/.env` 仅作为旧版本兼容。
- `.env`、`.env.*`、`front-site/.env.development` 和 `.nuxt/` 均已被忽略，不会提交。
- `SITE_SECRET_KEY` 一旦更换，数据库中已有模型/MCP 密文将无法解密；部署后请稳定保管。
- 不要将真实密钥写入 `.env.example`、README、SQL、测试代码或前端公开变量。

### 前台站点环境变量

`front-site` 使用独立的 `front-site/.env.development` / `.env.production`，模板见 `front-site/.env.example`。`NUXT_PUBLIC_*` 会进入浏览器端，严禁放置任何服务端密钥。

## 数据库初始化

创建数据库后，在项目根目录加载 `.env` 并依次执行 SQL：

```bash
set -a
source .env
set +a

createdb -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" "$PG_DBNAME"

PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DBNAME" -f INIT.SQL
PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DBNAME" -f 6.DB.sql
PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DBNAME" -f site/admin/admin.sql
PGPASSWORD="$PG_PASSWORD" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DBNAME" -f site/chief/chief.sql
```

初始化框架后台与 Site 管理后台管理员密码：

```bash
.venv/bin/python scripts/bootstrap_site_admin.py
```

脚本从 `FRAMEWORK_ADMIN_*` 和 `SITE_ADMIN_*` 环境变量读取凭据，只初始化空密码账号；需要重置时追加 `--force`。Site 管理后台首次登录后会要求修改密码。

SQL 种子包含演示业务数据，生产环境请按实际需要裁剪 `site/admin/admin.sql` 和 `site/chief/chief.sql` 中的演示记录。

## 启动服务

后端均从项目根目录启动，以便正确解析 `site`、`admin` 和 `framework` 包。

### 框架后台 API

```bash
source .venv/bin/activate
python -m uvicorn main:app --app-dir admin --host 127.0.0.1 --port 8000
```

接口文档：<http://127.0.0.1:8000/docs>

### 业务前台 API

```bash
source .venv/bin/activate
python -m uvicorn main:app --app-dir site --host 127.0.0.1 --port 8100
```

健康检查：<http://127.0.0.1:8100/health>

### 管理端

```bash
cd front-admin
npm install
npm run dev
```

默认地址：<http://localhost:3000>

### 前台站点

```bash
cd front-site
pnpm install
PORT=3100 pnpm dev
```

开发地址：<http://localhost:3100>

管理端和站点默认端口均为 3000。需要同时运行时，务必给 `front-site` 指定其他端口。

## 测试

Python 测试会自动读取项目根 `.env`。先准备数据库、测试账号和对应服务：

```bash
source .venv/bin/activate
python -m pytest site/admin/admin_test.py -q
python -m pytest admin/auth/auth_test.py -q
```

部分旧测试通过 HTTP 访问 `TEST_API_URL`，运行前需启动对应后端。

管理端 Playwright 测试：

```bash
cd front-admin
npm test
```

前台站点测试：

```bash
cd front-site
pnpm test
```

管理端 E2E 会从 `.env` 读取 `TEST_ADMIN_PASSWORD`；涉及普通用户的用例还需要 `TEST_USER_PASSWORD`。

## 开发约定

### 新增后台模块

复制 `admin/demo/` 下四个文件，并保持目录名、文件名和导入名一致：

```text
demo.sql
demo_model.py
demo_controller.py
demo_route.py
```

约定：

- 后台接口统一使用 POST 与 kebab-case 路径，例如 `get-demo-list`。
- 权限通过 `Depends(require_permission("demo:list"))` 声明。
- 删除默认使用软删除，`destroy-*` 才执行物理删除。
- 表结构使用项目统一的 `id`、`data_id`、时间戳和删除字段。

### 修改管理端

- 复制 `front-admin/src/views/demo/Demo.vue` 创建页面，并在 `src/router/index.js` 注册路由。
- API 统一走 `@/utils/request`，自动处理 camelCase 与 snake_case。
- 按钮权限使用 `v-permission="'demo:create'"`。

### 修改前台站点

- 页面放在 `front-site/app/pages/`。
- 接口请求使用 `front-site/app/composables/useApi.ts`。
- 遵守 `Nuxt4 官网开发 SEO 规范.md`。

## 安全清单

- 仓库不提交 `.env`、私钥、证书、数据库导出和真实附件。
- 生产环境关闭 `SITE_ADMIN_AUTO_LOGIN` 与 `SITE_ADMIN_AUTH_DISABLED`。
- 使用长随机值配置所有 JWT 与加密密钥，并限制 `.env` 文件权限。
- 模型 API Key 通过管理后台录入，数据库仅保存密文，接口只返回掩码。
- 导入用户必须提供密码，不再使用统一的默认密码。
- 若密钥曾进入 Git 历史，应立即轮换；仅删除当前文件不足以消除泄漏。

## 常见问题

**接口返回 500 或数据库连接失败**

检查 `.env` 的 `PG_*`、数据库是否启动，以及 SQL 是否按顺序执行。

**管理后台提示账号尚未初始化**

确认已执行 `site/admin/admin.sql`，然后运行 `python scripts/bootstrap_site_admin.py`。

**前台构建提示缺少 `SITE_URL`**

生产构建必须提供 `front-site/.env.production` 或由部署平台注入 `SITE_URL`。

**模型健康检查失败或密钥解密为空**

确认 `SITE_SECRET_KEY` 与加密数据写入时保持一致；密钥变化后需要重新录入模型/MCP 密钥。

## 相关文档

- `1.TODO.md`：待办与阶段任务
- `2.PRD.md`：产品需求
- `3.WBS.md`：工作分解
- `5.DB.md` / `6.DB.sql`：数据库设计
- `Nuxt4 官网开发 SEO 规范.md`：前台 SEO 与路由规范
- `front-site/README.md`：前台站点专项说明
