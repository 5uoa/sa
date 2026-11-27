# 前台管理后台（/admin）API 开发与联调 Spec

## Why

<http://localhost:3000/admin> 的管理页面（用户与角色、专家、模型、MCP、SKILL、额度总览、操作日志）以及 /quota 页面当前全部使用页面内写死的演示数据，任何新增、启停、删除、保存操作都只改内存，刷新即丢失。需要为这些页面提供真实 API，并完成前后端联调。

## What Changes

* 在 `site` 服务新增后台管理 API 模块 `site/admin/`（统一响应 `{code,message,data}`，本期不做登录鉴权），提供成员、专家、模型、MCP、SKILL、额度、操作日志 7 组 POST 接口。
* 新增 9 张业务表与种子数据（沿用 site 库无前缀表名约定）：`admin_member`、`ai_expert`、`ai_model`、`ai_mcp`、`ai_skill`、`quota_model`、`quota_project`、`quota_setting`、`admin_operation_log`。
* 在 `site/main.py` 注册新路由。
* front-site 页面接入 API，删除页面内 mock 数据：
  * `app/pages/admin.vue`：成员列表、邀请、启停、移除、额度总览、操作日志
  * `app/components/ExpertManager.vue`：专家 / 模型 / MCP / SKILL 的列表与增删改
  * `app/pages/quota.vue`：模型额度、告警设置、保存
* 统一通过现有 `useApi`（`NUXT_PUBLIC_API_BASE=http://127.0.0.1:8100`、camel/snake 自动转换）调用。

不在本次范围：登录与 Token 鉴权、个人设置页、工作台页面、front-admin、admin（8000）服务。

## Impact

* 受影响能力：前台管理后台全部数据读写、额度管理。
* 受影响代码：
  * 新增 `site/admin/{__init__.py,admin.sql,admin_model.py,admin_controller.py,admin_route.py,admin_test.py}`
  * `site/main.py`（注册路由）
  * `front-site/app/pages/admin.vue`
  * `front-site/app/components/ExpertManager.vue`
  * `front-site/app/pages/quota.vue`

## ADDED Requirements

### Requirement: 后台管理 API

系统 SHALL 在 site 服务提供以下 POST 接口（前缀 `/front/admin`），统一返回 `{code,message,data}`，请求体字段为 snake\_case（`useApi` 已做 camelCase → snake\_case 转换）：

| 分组    | 接口                                                                                                      | 说明                                                                                              |
| ----- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| 成员    | `/members/list`、`/members/create`、`/members/update`、`/members/delete`                                   | 字段 `id,name,email,role,enabled,lastActive`；角色仅 `拥有者/管理员/成员/访客`                                  |
| 专家    | `/experts/list`、`/experts/create`、`/experts/update`、`/experts/delete`                                   | 字段 `id,name,role,model,temperature,prompt,enabled,mcpIds,skillIds`                              |
| 模型    | `/models/list`、`/models/create`、`/models/update`、`/models/delete`                                       | 注册项字段 `id,name,description,meta,status,endpoint`                                                |
| MCP   | `/mcp/list`、`/mcp/create`、`/mcp/update`、`/mcp/delete`                                                   | 同上                                                                                              |
| SKILL | `/skills/list`、`/skills/create`、`/skills/update`、`/skills/delete`                                       | 同上（无 endpoint）                                                                                  |
| 额度    | `/quota/get-summary`、`/quota/get-project-quotas`、`/quota/get-model-quotas`、`/quota/update-model-quotas` | 摘要 `label,value,note` + `used,limit`；项目额度 `id,name,used,limit`；模型额度 `id,model,price,used,limit` |
| 额度    | `/quota/get-alert-settings`、`/quota/update-alert-settings`                                              | `threshold,channel,notifyAdmin,stopOnExceed`                                                    |
| 日志    | `/logs/list`                                                                                            | 字段 `id,time,user,action,target`，按时间倒序                                                           |

约束：

* 列表接口返回 `data.items`；创建返回 `data.id`（UUID 字符串），更新/删除返回 `data: null`。
* 成员邮箱必填且格式合法；重复邮箱返回 400；专家名称必填；注册项名称必填。
* 更新/删除不存在的 id 返回 404（`code=404`）。
* 专家保存时 `model`、`mcpIds`、`skillIds` 原样落库（JSONB），读取时保持数组。
* 本期不做鉴权；CORS 已包含 `http://localhost:3000`。

#### Scenario: 成员邀请与启停

* **WHEN** 在 /admin「用户与角色」邀请 `new@example.com`，随后停用该成员并刷新页面
* **THEN** 列表出现该成员且状态为停用，刷新后状态仍为停用

#### Scenario: 专家配置持久化

* **WHEN** 在「专家」中修改某专家的模型、勾选 2 个 MCP 与 1 个 SKILL 并保存
* **THEN** 刷新后配置保持不变；重新打开配置弹窗显示相同勾选

#### Scenario: 注册项引用保护

* **WHEN** 删除已被专家引用的 MCP
* **THEN** 接口返回 `code=400` 并提示被引用的专家，列表不变

#### Scenario: 额度保存

* **WHEN** 在 /quota 修改某模型额度上限与告警阈值并保存，刷新页面
* **THEN** 展示修改后的上限与阈值

#### Scenario: 操作日志

* **WHEN** 完成一次成员角色修改
* **THEN** `/logs/list` 返回包含该操作的记录，/admin「操作日志」分区可见

### Requirement: 后台管理数据表

系统 SHALL 新增以下表（`CREATE TABLE IF NOT EXISTS`，含 `id BIGSERIAL`、`data_id UUID DEFAULT gen_random_uuid()` 作为接口 id、`create_time/update_time`、`is_deleted` 软删除），并提供幂等种子数据：

* `admin_member`：`name`、`email`（唯一索引，未删除）、`role`、`enabled`、`last_active`
* `ai_model` / `ai_mcp` / `ai_skill`：`name`、`description`、`meta`、`status`（`可用/异常/未测试`）、`endpoint`（SKILL 可为空）
* `ai_expert`：`name`、`role`、`model`、`temperature`、`prompt`、`enabled`、`mcp_ids JSONB`、`skill_ids JSONB`
* `quota_model`：`model`、`price`、`used`、`quota_limit`
* `quota_project`：`name`、`used`、`quota_limit`
* `quota_setting`：单行配置 `threshold`、`channel`、`notify_admin`、`stop_on_exceed`
* `admin_operation_log`：`user_name`、`action`、`target`、`occurred_at`

DDL 与种子数据位于 `site/admin/admin.sql`，可在本地 PostgreSQL 重复执行。

## MODIFIED Requirements

### Requirement: 前台管理页面数据来源

`app/pages/admin.vue`、`app/components/ExpertManager.vue`、`app/pages/quota.vue` SHALL 以 site API 为唯一数据源，不再保留写死的成员/专家/注册项/额度/日志数组；页面保留现有布局与交互，补充加载态（`loading`）与失败提示（`UAlert`），写操作成功后以接口返回刷新列表或本地状态。

#### Scenario: 首屏加载

* **WHEN** 打开 /admin 或 /quota
* **THEN** 各分区数据来自接口，Network 中对应 `/front/admin/*` 请求均返回 `code=200`，无控制台报错
