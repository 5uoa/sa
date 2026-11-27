# Tasks

- [x] Task 1: 后端后台管理模块与数据表（site/admin）
  - [x] SubTask 1.1: 编写 `site/admin/admin.sql`，创建 9 张表、索引与幂等种子数据（沿用当前页面演示数据）
  - [x] SubTask 1.2: 编写 `site/admin/admin_model.py`，实现成员、专家、模型/MCP/SKILL、额度、日志的查询与写入（复用 `db.fetch/fetchrow/execute`）
  - [x] SubTask 1.3: 编写 `site/admin/admin_controller.py`，实现字段校验、邮箱唯一、角色/状态枚举、引用保护、404 语义与 `admin_operation_log` 写入
  - [x] SubTask 1.4: 编写 `site/admin/admin_route.py`，按 spec 提供 7 组 POST 接口（`/front/admin/*`）
  - [x] SubTask 1.5: 在 `site/main.py` 注册路由，确认 `/docs` 中出现全部接口
  - [x] SubTask 1.6: 在本地 PostgreSQL 执行 `admin.sql`，确认表与种子数据存在（幂等可重复执行）

- [x] Task 2: 后端接口验证
  - [x] SubTask 2.1: 新增 `site/admin/admin_test.py`，覆盖成员创建/重复邮箱/启停/删除、专家配置读写、注册项被引用时删除拒绝、额度保存、日志列表
  - [x] SubTask 2.2: 执行测试（沿用项目 Python 测试方式），确保全部通过

- [x] Task 3: 前端接入——管理后台成员与日志
  - [x] SubTask 3.1: `app/pages/admin.vue` 成员列表、邀请、启停、移除改为调用 `/front/admin/members/*`，含 loading 与失败提示
  - [x] SubTask 3.2: 额度总览分区改为 `/quota/get-summary`、`/quota/get-project-quotas`
  - [x] SubTask 3.3: 操作日志分区改为 `/logs/list`，按分区切换懒加载

- [x] Task 4: 前端接入——专家 / 模型 / MCP / SKILL
  - [x] SubTask 4.1: `ExpertManager.vue` 挂载时加载当前 `kind` 对应列表（models/mcp/skills/experts）
  - [x] SubTask 4.2: 注册项新增、编辑、删除改调对应 `/models|mcp|skills/*` 接口，删除被引用时展示后端错误
  - [x] SubTask 4.3: 专家新建、配置保存、删除改调 `/experts/*`，MCP/SKILL 勾选结果持久化
  - [x] SubTask 4.4: 保留「保存并测试」的本地模拟行为，不新增后端探测接口

- [x] Task 5: 前端接入——额度管理页
  - [x] SubTask 5.1: `/quota` 模型额度改为 `/quota/get-model-quotas`，保存改为 `/quota/update-model-quotas`
  - [x] SubTask 5.2: 告警设置改为 `/quota/get-alert-settings`、`/quota/update-alert-settings`，保存后保留提示

- [x] Task 6: 联调与回归
  - [x] SubTask 6.1: 启动 site（8100）与 front-site（3000），验证 /admin 与 /quota 首屏接口全部 `code=200`
  - [x] SubTask 6.2: 逐项联调：邀请成员→停用→刷新；专家改配置→刷新；注册项增删；额度保存→刷新；日志出现记录
  - [x] SubTask 6.3: 前端 `npx prettier --check`、`npx eslint`、`npx nuxt typecheck` 通过
  - [x] SubTask 6.4: 运行 `npm run build`（或项目现有构建命令）通过，页面无控制台报错

# Task Dependencies
- Task 2 依赖 Task 1
- Task 3、Task 4、Task 5 依赖 Task 1（可并行）
- Task 6 依赖 Task 2、Task 3、Task 4、Task 5
