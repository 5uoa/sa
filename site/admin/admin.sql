-- 管理后台建表与演示数据（幂等，可重复执行）
-- 表名无前缀；对外 id 一律使用 data_id（UUID）

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS admin_member (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL DEFAULT '',
    email VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT '成员',
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_active VARCHAR(40) NOT NULL DEFAULT '待激活',
    password_hash TEXT NOT NULL DEFAULT '',
    must_change_password BOOLEAN NOT NULL DEFAULT true,
    invitation_token_hash VARCHAR(64),
    invitation_expires_at TIMESTAMPTZ,
    accepted_at TIMESTAMPTZ,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_member_email
    ON admin_member (lower(email)) WHERE is_deleted = false;
CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_member_data_id ON admin_member (data_id);
ALTER TABLE admin_member ADD COLUMN IF NOT EXISTS password_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE admin_member ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE admin_member ADD COLUMN IF NOT EXISTS invitation_token_hash VARCHAR(64);
ALTER TABLE admin_member ADD COLUMN IF NOT EXISTS invitation_expires_at TIMESTAMPTZ;
ALTER TABLE admin_member ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS ai_expert (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    role VARCHAR(120) NOT NULL DEFAULT '',
    model VARCHAR(120) NOT NULL DEFAULT '',
    model_id UUID,
    temperature VARCHAR(40) NOT NULL DEFAULT '均衡 · 0.7',
    prompt TEXT NOT NULL DEFAULT '',
    enabled BOOLEAN NOT NULL DEFAULT true,
    mcp_ids JSONB NOT NULL DEFAULT '[]',
    skill_ids JSONB NOT NULL DEFAULT '[]',
    settings JSONB NOT NULL DEFAULT '{}',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_expert_data_id ON ai_expert (data_id);
ALTER TABLE ai_expert ADD COLUMN IF NOT EXISTS model_id UUID;
ALTER TABLE ai_expert ADD COLUMN IF NOT EXISTS settings JSONB NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS ai_expert_session (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    expert_id UUID NOT NULL,
    project_id UUID,
    task_id UUID,
    title VARCHAR(200) NOT NULL DEFAULT '新会话',
    create_by UUID,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_archived BOOLEAN NOT NULL DEFAULT false,
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_expert_session_data_id
    ON ai_expert_session (data_id);
CREATE INDEX IF NOT EXISTS idx_ai_expert_session_owner
    ON ai_expert_session (create_by, expert_id, update_time DESC)
    WHERE is_deleted = false AND is_archived = false;
ALTER TABLE ai_expert_session ADD COLUMN IF NOT EXISTS project_id UUID;
ALTER TABLE ai_expert_session ADD COLUMN IF NOT EXISTS task_id UUID;
CREATE INDEX IF NOT EXISTS idx_ai_expert_session_project
    ON ai_expert_session (project_id, update_time DESC)
    WHERE is_deleted = false AND project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_expert_session_task
    ON ai_expert_session (task_id, update_time DESC)
    WHERE is_deleted = false AND task_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS ai_expert_message (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    run_id UUID,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    attachments JSONB NOT NULL DEFAULT '[]',
    meta JSONB NOT NULL DEFAULT '{}',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_expert_message_data_id
    ON ai_expert_message (data_id);
CREATE INDEX IF NOT EXISTS idx_ai_expert_message_session
    ON ai_expert_message (session_id, id)
    WHERE is_deleted = false;

CREATE TABLE IF NOT EXISTS ai_expert_run (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    expert_id UUID NOT NULL,
    model_name VARCHAR(160) NOT NULL DEFAULT '',
    question TEXT NOT NULL DEFAULT '',
    answer TEXT NOT NULL DEFAULT '',
    status VARCHAR(20) NOT NULL DEFAULT 'completed',
    tool_trace JSONB NOT NULL DEFAULT '[]',
    warnings JSONB NOT NULL DEFAULT '[]',
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    cost NUMERIC(12, 6) NOT NULL DEFAULT 0,
    model_attempts JSONB NOT NULL DEFAULT '[]',
    state_enc TEXT NOT NULL DEFAULT '',
    pending_approval JSONB NOT NULL DEFAULT '{}',
    create_by UUID,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_expert_run_data_id ON ai_expert_run (data_id);
CREATE INDEX IF NOT EXISTS idx_ai_expert_run_expert
    ON ai_expert_run (expert_id, create_time DESC);
ALTER TABLE ai_expert_run ADD COLUMN IF NOT EXISTS state_enc TEXT NOT NULL DEFAULT '';
ALTER TABLE ai_expert_run
    ADD COLUMN IF NOT EXISTS pending_approval JSONB NOT NULL DEFAULT '{}';
ALTER TABLE ai_expert_run ADD COLUMN IF NOT EXISTS cost NUMERIC(12, 6) NOT NULL DEFAULT 0;
ALTER TABLE ai_expert_run
    ADD COLUMN IF NOT EXISTS model_attempts JSONB NOT NULL DEFAULT '[]';
ALTER TABLE ai_expert_run ADD COLUMN IF NOT EXISTS session_id UUID;
CREATE INDEX IF NOT EXISTS idx_ai_expert_run_session
    ON ai_expert_run (session_id, create_time DESC)
    WHERE session_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS ai_model (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    meta VARCHAR(200) NOT NULL DEFAULT '',
    status VARCHAR(10) NOT NULL DEFAULT '未测试',
    endpoint TEXT NOT NULL DEFAULT '',
    model_key VARCHAR(160) NOT NULL DEFAULT '',
    api_key_enc TEXT NOT NULL DEFAULT '',
    provider VARCHAR(40) NOT NULL DEFAULT 'openai_compatible',
    capabilities JSONB NOT NULL DEFAULT '{}',
    config JSONB NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT true,
    priority INTEGER NOT NULL DEFAULT 100,
    health_status VARCHAR(20) NOT NULL DEFAULT 'unknown',
    last_checked_at TIMESTAMPTZ,
    last_error TEXT NOT NULL DEFAULT '',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_data_id ON ai_model (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_model_name
    ON ai_model (lower(name)) WHERE is_deleted = false;

-- 已有数据库补列（幂等）：模型 API Key 仅存密文
ALTER TABLE ai_model ADD COLUMN IF NOT EXISTS api_key_enc TEXT NOT NULL DEFAULT '';
ALTER TABLE ai_model ADD COLUMN IF NOT EXISTS model_key VARCHAR(160) NOT NULL DEFAULT '';
ALTER TABLE ai_model
    ADD COLUMN IF NOT EXISTS provider VARCHAR(40) NOT NULL DEFAULT 'openai_compatible';
ALTER TABLE ai_model
    ADD COLUMN IF NOT EXISTS capabilities JSONB NOT NULL DEFAULT '{}';
ALTER TABLE ai_model
    ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}';
ALTER TABLE ai_model ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE ai_model ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100;
ALTER TABLE ai_model
    ADD COLUMN IF NOT EXISTS health_status VARCHAR(20) NOT NULL DEFAULT 'unknown';
ALTER TABLE ai_model ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ;
ALTER TABLE ai_model ADD COLUMN IF NOT EXISTS last_error TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS ai_mcp (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    meta VARCHAR(200) NOT NULL DEFAULT '',
    status VARCHAR(10) NOT NULL DEFAULT '未测试',
    endpoint TEXT NOT NULL DEFAULT '',
    config JSONB NOT NULL DEFAULT '{}',
    secret_config_enc TEXT NOT NULL DEFAULT '',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_mcp_data_id ON ai_mcp (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_mcp_name
    ON ai_mcp (lower(name)) WHERE is_deleted = false;
ALTER TABLE ai_mcp ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}';
ALTER TABLE ai_mcp
    ADD COLUMN IF NOT EXISTS secret_config_enc TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS ai_skill (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    meta VARCHAR(200) NOT NULL DEFAULT '',
    status VARCHAR(10) NOT NULL DEFAULT '未测试',
    endpoint TEXT NOT NULL DEFAULT '',
    config JSONB NOT NULL DEFAULT '{}',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_skill_data_id ON ai_skill (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_skill_name
    ON ai_skill (lower(name)) WHERE is_deleted = false;
ALTER TABLE ai_skill ADD COLUMN IF NOT EXISTS config JSONB NOT NULL DEFAULT '{}';

CREATE TABLE IF NOT EXISTS quota_model (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    model VARCHAR(120) NOT NULL,
    price VARCHAR(60) NOT NULL DEFAULT '',
    used NUMERIC(12, 2) NOT NULL DEFAULT 0,
    quota_limit NUMERIC(12, 2) NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS quota_project (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    used NUMERIC(12, 2) NOT NULL DEFAULT 0,
    quota_limit NUMERIC(12, 2) NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_quota_project_data_id ON quota_project (data_id);

CREATE TABLE IF NOT EXISTS quota_setting (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    threshold VARCHAR(10) NOT NULL DEFAULT '80%',
    channel VARCHAR(40) NOT NULL DEFAULT '站内 + 邮件',
    notify_admin BOOLEAN NOT NULL DEFAULT true,
    stop_on_exceed BOOLEAN NOT NULL DEFAULT false,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_quota_setting_data_id ON quota_setting (data_id);

CREATE TABLE IF NOT EXISTS admin_operation_log (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    user_id UUID,
    user_name VARCHAR(60) NOT NULL DEFAULT '',
    action VARCHAR(120) NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_admin_operation_log_data_id ON admin_operation_log (data_id);
CREATE INDEX IF NOT EXISTS idx_admin_operation_log_time ON admin_operation_log (create_time DESC);
CREATE INDEX IF NOT EXISTS idx_admin_operation_log_user ON admin_operation_log (user_name);
ALTER TABLE admin_operation_log ADD COLUMN IF NOT EXISTS user_id UUID;

-- 将历史专家配置迁移到稳定的模型 UUID。
UPDATE ai_expert e
   SET model_id = m.data_id
  FROM ai_model m
 WHERE e.model_id IS NULL
   AND e.is_deleted = false
   AND m.is_deleted = false
   AND m.name = e.model;

-- 已有 DeepSeek 配置使用供应商真实模型标识。
UPDATE ai_model
   SET model_key = 'deepseek-v4-pro',
       update_time = now()
 WHERE name = 'DeepSeek-V3'
   AND model_key = ''
   AND is_deleted = false;

-- ==================== 演示数据 ====================

INSERT INTO admin_member (name, email, role, enabled, last_active)
SELECT v.name, v.email, v.role, v.enabled, v.last_active
FROM (VALUES
    (1, '拥有者', 'owner@example.com', '拥有者', true, '刚刚'),
    (2, '管理员一', 'admin1@example.com', '管理员', true, '12 分钟前'),
    (3, '成员一', 'member1@example.com', '成员', true, '2 小时前'),
    (4, '成员二', 'member2@example.com', '成员', false, '3 天前'),
    (5, '访客', 'guest@example.com', '访客', true, '昨天 18:40'),
    (6, '成员三', 'member3@example.com', '成员', true, '5 小时前')
) AS v(ord, name, email, role, enabled, last_active)
WHERE NOT EXISTS (
    SELECT 1 FROM admin_member m WHERE lower(m.email) = lower(v.email) AND m.is_deleted = false
)
ORDER BY v.ord;

INSERT INTO ai_mcp (name, description, meta, status, endpoint)
SELECT v.name, v.description, v.meta, v.status, v.endpoint
FROM (VALUES
    (1, '文件系统', '读取工作区文件与附件内容', '', '未测试', 'stdio: ${PYTHON} ${PROJECT_ROOT}/site/admin/filesystem_mcp.py'),
    (2, '数据库查询', '查询项目、任务与交付数据', '', '未测试', 'stdio: ${PYTHON} ${PROJECT_ROOT}/site/admin/postgres_mcp.py'),
    (3, '浏览器自动化', '打开页面、截图并校验交互；首次使用需在 Safari 开发者设置中允许远程自动化', '', '未测试', 'stdio: ${SAFARIDRIVER} --mcp'),
    (4, '代码仓库', '检索代码、提交记录与差异', '', '未测试', 'stdio: ${PYTHON} ${PROJECT_ROOT}/site/admin/repository_mcp.py')
) AS v(ord, name, description, meta, status, endpoint)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_mcp t WHERE t.name = v.name AND t.is_deleted = false
)
ORDER BY v.ord;

-- 修复旧版种子中不可执行或未启动的 MCP 端点；仅覆盖已知旧值。
UPDATE ai_mcp
   SET endpoint = 'stdio: ${PYTHON} ${PROJECT_ROOT}/site/admin/filesystem_mcp.py',
       config = '{}'::jsonb,
       status = '未测试',
       update_time = now()
 WHERE name = '文件系统'
   AND endpoint = 'npx @modelcontextprotocol/server-filesystem'
   AND is_deleted = false;

UPDATE ai_mcp
   SET endpoint = 'stdio: ${PYTHON} ${PROJECT_ROOT}/site/admin/postgres_mcp.py',
       config = '{}'::jsonb,
       status = '未测试',
       update_time = now()
 WHERE name = '数据库查询'
   AND endpoint = 'postgres://readonly@localhost:5432/sa'
   AND is_deleted = false;

UPDATE ai_mcp
   SET endpoint = 'stdio: ${SAFARIDRIVER} --mcp',
       description = '打开页面、截图并校验交互；首次使用需在 Safari 开发者设置中允许远程自动化',
       config = jsonb_build_object(
           'read_only_tools',
           jsonb_build_array(
               'browser_console_messages',
               'get_network_request',
               'get_page_content',
               'list_network_requests',
               'list_tabs',
               'page_info',
               'wait_for_navigation'
           )
       ),
       status = '未测试',
       update_time = now()
 WHERE name = '浏览器自动化'
   AND endpoint IN (
       'http://localhost:8931/mcp',
       'stdio: ${NODE} ${FRONT_DIR}/scripts/browser_mcp.mjs'
   )
   AND is_deleted = false;

UPDATE ai_mcp
   SET description = '打开页面、截图并校验交互；首次使用需在 Safari 开发者设置中允许远程自动化',
       config = jsonb_build_object(
           'read_only_tools',
           jsonb_build_array(
               'browser_console_messages',
               'get_network_request',
               'get_page_content',
               'list_network_requests',
               'list_tabs',
               'page_info',
               'wait_for_navigation'
           )
       ),
       update_time = now()
 WHERE name = '浏览器自动化'
   AND endpoint = 'stdio: ${SAFARIDRIVER} --mcp'
   AND is_deleted = false;

UPDATE ai_mcp
   SET endpoint = 'stdio: ${PYTHON} ${PROJECT_ROOT}/site/admin/repository_mcp.py',
       config = '{}'::jsonb,
       status = '未测试',
       update_time = now()
 WHERE name = '代码仓库'
   AND endpoint IN ('stdio: git mcp', 'git mcp')
   AND is_deleted = false;

INSERT INTO ai_skill (name, description, meta, status, endpoint)
SELECT v.name, v.description, v.meta, v.status, v.endpoint
FROM (VALUES
    (1, '竞品分析', '检索、对比并输出结构化结论', '', '可用', ''),
    (2, '文案生成', '按品牌口径生成与改写文案', '', '可用', ''),
    (3, '数据可视化', '选择图表并渲染可视化结果', '', '可用', ''),
    (4, '会议纪要', '整理会议纪要与后续待办', '', '可用', '')
) AS v(ord, name, description, meta, status, endpoint)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_skill t WHERE t.name = v.name AND t.is_deleted = false
)
ORDER BY v.ord;

UPDATE ai_skill
   SET config = jsonb_build_object(
       'instructions', description,
       'requires_tools', '[]'::jsonb
   ),
       update_time = now()
 WHERE config = '{}'::jsonb
   AND is_deleted = false;

-- 内置 SKILL 的确定性 handler、输入 Schema 与输出 Schema。
UPDATE ai_skill
   SET config = config || jsonb_build_object(
       'handler', 'experts.builtin_skills:competitor_analysis',
       'timeout_seconds', 10,
       'test_input', jsonb_build_object(
           'competitors', jsonb_build_array(
               jsonb_build_object(
                   'name', '竞品 A',
                   'strengths', jsonb_build_array('渠道覆盖'),
                   'weaknesses', jsonb_build_array('内容深度')
               )
           ),
           'focus', '品牌差异'
       ),
       'input_schema', jsonb_build_object(
           'type', 'object',
           'properties', jsonb_build_object(
               'competitors', jsonb_build_object(
                   'type', 'array',
                   'items', jsonb_build_object('type', 'object')
               ),
               'focus', jsonb_build_object('type', 'string')
           ),
           'required', jsonb_build_array('competitors')
       ),
       'output_schema', jsonb_build_object(
           'type', 'object',
           'properties', jsonb_build_object(
               'focus', jsonb_build_object('type', 'string'),
               'competitors', jsonb_build_object('type', 'array'),
               'summary', jsonb_build_object('type', 'string')
           ),
           'required', jsonb_build_array('competitors', 'summary')
       )
   ),
       update_time = now()
 WHERE name = '竞品分析'
   AND NOT (COALESCE(config, '{}'::jsonb) ? 'handler')
   AND is_deleted = false;

UPDATE ai_skill
   SET config = config || jsonb_build_object(
       'handler', 'experts.builtin_skills:copywriting',
       'timeout_seconds', 10,
       'test_input', jsonb_build_object(
           'brief', '发布年度产品',
           'tone', '专业清晰',
           'channels', jsonb_build_array('官网')
       ),
       'input_schema', jsonb_build_object(
           'type', 'object',
           'properties', jsonb_build_object(
               'brief', jsonb_build_object('type', 'string'),
               'tone', jsonb_build_object('type', 'string'),
               'channels', jsonb_build_object(
                   'type', 'array',
                   'items', jsonb_build_object('type', 'string')
               )
           ),
           'required', jsonb_build_array('brief')
       ),
       'output_schema', jsonb_build_object(
           'type', 'object',
           'properties', jsonb_build_object(
               'drafts', jsonb_build_object('type', 'array')
           ),
           'required', jsonb_build_array('drafts')
       )
   ),
       update_time = now()
 WHERE name = '文案生成'
   AND NOT (COALESCE(config, '{}'::jsonb) ? 'handler')
   AND is_deleted = false;

UPDATE ai_skill
   SET config = config || jsonb_build_object(
       'handler', 'experts.builtin_skills:data_visualization',
       'timeout_seconds', 10,
       'test_input', jsonb_build_object(
           'data', jsonb_build_array(
               jsonb_build_object('name', '一月', 'value', 12),
               jsonb_build_object('name', '二月', 'value', 18)
           ),
           'x', 'name',
           'y', 'value',
           'chart_type', 'bar'
       ),
       'input_schema', jsonb_build_object(
           'type', 'object',
           'properties', jsonb_build_object(
               'data', jsonb_build_object(
                   'type', 'array',
                   'items', jsonb_build_object('type', 'object')
               ),
               'x', jsonb_build_object('type', 'string'),
               'y', jsonb_build_object('type', 'string'),
               'chart_type', jsonb_build_object('type', 'string')
           ),
           'required', jsonb_build_array('data')
       ),
       'output_schema', jsonb_build_object(
           'type', 'object',
           'properties', jsonb_build_object(
               'series', jsonb_build_object('type', 'array')
           ),
           'required', jsonb_build_array('series')
       )
   ),
       update_time = now()
 WHERE name = '数据可视化'
   AND NOT (COALESCE(config, '{}'::jsonb) ? 'handler')
   AND is_deleted = false;

UPDATE ai_skill
   SET config = config || jsonb_build_object(
       'handler', 'experts.builtin_skills:meeting_minutes',
       'timeout_seconds', 10,
       'test_input', jsonb_build_object(
           'transcript', E'确认本周上线。\n待办：完成回归测试，负责人：张三。'
       ),
       'input_schema', jsonb_build_object(
           'type', 'object',
           'properties', jsonb_build_object(
               'transcript', jsonb_build_object('type', 'string')
           ),
           'required', jsonb_build_array('transcript')
       ),
       'output_schema', jsonb_build_object(
           'type', 'object',
           'properties', jsonb_build_object(
               'summary', jsonb_build_object('type', 'string'),
               'actionItems', jsonb_build_object('type', 'array')
           ),
           'required', jsonb_build_array('summary', 'actionItems')
       )
   ),
       update_time = now()
 WHERE name = '会议纪要'
   AND NOT (COALESCE(config, '{}'::jsonb) ? 'handler')
   AND is_deleted = false;

INSERT INTO ai_model (name, description, meta, status, endpoint, model_key)
SELECT v.name, v.description, v.meta, v.status, v.endpoint, v.model_key
FROM (VALUES
    (1, 'GPT-5', 'OpenAI · 官方', '128K 上下文', '未测试', 'https://api.openai.com/v1', 'gpt-5'),
    (2, 'Claude Sonnet 4', 'Anthropic · 官方', '200K 上下文', '未测试', 'https://api.anthropic.com', 'claude-sonnet-4'),
    (3, 'Doubao Seed', '火山引擎 · 官方', '256K 上下文', '未测试', 'https://api.volces.com/v3', 'doubao-seed')
) AS v(ord, name, description, meta, status, endpoint, model_key)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_model t WHERE t.name = v.name AND t.is_deleted = false
)
ORDER BY v.ord;

UPDATE ai_model
   SET model_key = CASE name
       WHEN 'GPT-5' THEN 'gpt-5'
       WHEN 'Claude Sonnet 4' THEN 'claude-sonnet-4'
       WHEN 'Doubao Seed' THEN 'doubao-seed'
       ELSE model_key
   END,
       status = CASE WHEN api_key_enc = '' THEN '未测试' ELSE status END,
       update_time = now()
 WHERE name IN ('GPT-5', 'Claude Sonnet 4', 'Doubao Seed')
   AND is_deleted = false;

UPDATE ai_model
   SET provider = CASE
           WHEN endpoint ILIKE '%anthropic%' THEN 'anthropic'
           ELSE 'openai_compatible'
       END,
       capabilities = capabilities || jsonb_build_object(
           'contextWindow', CASE
               WHEN endpoint ILIKE '%anthropic%' THEN 200000
               WHEN endpoint ILIKE '%volces%' THEN 256000
               WHEN endpoint ILIKE '%deepseek%' THEN 128000
               ELSE 128000
           END,
           'maxOutputTokens', CASE
               WHEN endpoint ILIKE '%anthropic%' THEN 8192
               ELSE 4096
           END,
           'tools', provider <> 'anthropic' OR endpoint ILIKE '%anthropic%',
           'vision', endpoint NOT ILIKE '%deepseek%',
           'json', endpoint NOT ILIKE '%anthropic%',
           'streaming', true,
           'embeddings', false
       ),
       update_time = now()
 WHERE is_deleted = false
   AND capabilities = '{}'::jsonb;

UPDATE ai_model
   SET capabilities = jsonb_set(
           capabilities,
           '{vision}',
           'false'::jsonb,
           true
       ),
       update_time = now()
 WHERE endpoint ILIKE '%deepseek%'
   AND is_deleted = false;

INSERT INTO ai_expert (name, role, model, temperature, prompt, enabled, mcp_ids, skill_ids)
SELECT '品牌策略专家', '品牌与内容策略', 'GPT-5', '均衡 · 0.7',
       '你负责品牌策略与内容规划，先对齐年度主题，再给出可执行的交付建议。', true,
       COALESCE((
           SELECT jsonb_agg(data_id::text ORDER BY id)
             FROM ai_mcp
            WHERE name = ANY (ARRAY['文件系统', '数据库查询', '浏览器自动化']) AND is_deleted = false
       ), '[]'::jsonb),
       COALESCE((
           SELECT jsonb_agg(data_id::text ORDER BY id)
             FROM ai_skill
            WHERE name = ANY (ARRAY['竞品分析', '文案生成']) AND is_deleted = false
       ), '[]'::jsonb)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_expert t WHERE t.name = '品牌策略专家' AND t.is_deleted = false
);

INSERT INTO ai_expert (name, role, model, temperature, prompt, enabled, mcp_ids, skill_ids)
SELECT '数据分析专家', '数据与增长分析', 'Claude Sonnet 4', '精确 · 0.2',
       '你负责数据口径与增长分析，所有结论必须给出数据来源与计算方式。', true,
       COALESCE((
           SELECT jsonb_agg(data_id::text ORDER BY id)
             FROM ai_mcp
            WHERE name = ANY (ARRAY['数据库查询', '代码仓库']) AND is_deleted = false
       ), '[]'::jsonb),
       COALESCE((
           SELECT jsonb_agg(data_id::text ORDER BY id)
             FROM ai_skill
            WHERE name = ANY (ARRAY['数据可视化', '竞品分析']) AND is_deleted = false
       ), '[]'::jsonb)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_expert t WHERE t.name = '数据分析专家' AND t.is_deleted = false
);

INSERT INTO ai_expert (name, role, model, temperature, prompt, enabled, mcp_ids, skill_ids)
SELECT '客户成功专家', '客户沟通与交付', 'Doubao Seed', '均衡 · 0.7',
       '你负责客户沟通与交付跟进，先同步风险，再给出下一步动作与负责人。', false,
       COALESCE((
           SELECT jsonb_agg(data_id::text ORDER BY id)
             FROM ai_mcp
            WHERE name = ANY (ARRAY['文件系统']) AND is_deleted = false
       ), '[]'::jsonb),
       COALESCE((
           SELECT jsonb_agg(data_id::text ORDER BY id)
             FROM ai_skill
            WHERE name = ANY (ARRAY['会议纪要', '文案生成']) AND is_deleted = false
       ), '[]'::jsonb)
WHERE NOT EXISTS (
    SELECT 1 FROM ai_expert t WHERE t.name = '客户成功专家' AND t.is_deleted = false
);

-- 浏览器 MCP 未声明工具注解；品牌专家通过显式写入授权启用浏览器交互工具。
UPDATE ai_expert
   SET settings = COALESCE(settings, '{}'::jsonb)
                  || '{"allow_write_tools": true}'::jsonb,
       update_time = now()
 WHERE name = '品牌策略专家'
   AND COALESCE(
       settings->>'allow_write_tools',
       settings->>'allowWriteTools',
       'false'
   ) <> 'true'
   AND is_deleted = false;

INSERT INTO quota_model (model, price, used, quota_limit, sort_order)
SELECT v.model, v.price, v.used, v.quota_limit, v.sort_order
FROM (VALUES
    (1, 'GPT-4.1', '¥0.02 / 1K', 620::numeric, 1500::numeric, 1),
    (2, 'Claude 4 Sonnet', '¥0.018 / 1K', 480::numeric, 1200::numeric, 2),
    (3, 'DeepSeek-V3', '¥0.004 / 1K', 260::numeric, 800::numeric, 3),
    (4, 'Gemini 2.5 Pro', '¥0.012 / 1K', 0::numeric, 500::numeric, 4),
    (5, 'Qwen3-235B', '¥0.006 / 1K', 500::numeric, 500::numeric, 5)
) AS v(ord, model, price, used, quota_limit, sort_order)
WHERE NOT EXISTS (
    SELECT 1 FROM quota_model t WHERE t.model = v.model AND t.is_deleted = false
)
ORDER BY v.ord;

INSERT INTO quota_project (name, used, quota_limit, sort_order)
SELECT v.name, v.used, v.quota_limit, v.sort_order
FROM (VALUES
    (1, '品牌年度内容规划', 720::numeric, 1500::numeric, 1),
    (2, '新品上市传播', 540::numeric, 1200::numeric, 2),
    (3, '客户提案复盘', 280::numeric, 800::numeric, 3),
    (4, '内部试验', 320::numeric, 500::numeric, 4)
) AS v(ord, name, used, quota_limit, sort_order)
WHERE NOT EXISTS (
    SELECT 1 FROM quota_project t WHERE t.name = v.name AND t.is_deleted = false
)
ORDER BY v.ord;

INSERT INTO quota_setting (id, threshold, channel, notify_admin, stop_on_exceed)
SELECT 1, '80%', '站内 + 邮件', true, false
WHERE NOT EXISTS (SELECT 1 FROM quota_setting WHERE id = 1);

INSERT INTO admin_operation_log (user_name, action, target, create_time)
SELECT v.user_name, v.action, v.target, v.create_time
FROM (VALUES
    (1, '拥有者', '修改成员角色', '成员一 · 成员 → 管理员',
     date_trunc('day', now()) + interval '10 hours 24 minutes'),
    (2, '管理员一', '启用模型', 'DeepSeek-V3',
     date_trunc('day', now()) + interval '9 hours 12 minutes'),
    (3, '拥有者', '调整项目额度', '品牌年度内容规划 ¥1,200 → ¥1,500',
     date_trunc('day', now()) - interval '1 day' + interval '17 hours 40 minutes'),
    (4, '管理员一', '邀请成员', 'member3@example.com',
     date_trunc('day', now()) - interval '1 day' + interval '15 hours 2 minutes'),
    (5, '系统', '额度告警', '内部试验 使用率 64%',
     date_trunc('day', now()) - interval '1 day' + interval '11 hours 26 minutes'),
    (6, '拥有者', '停用 Agent', '专家 Agent',
     date_trunc('day', now()) - interval '3 days' + interval '16 hours 48 minutes')
) AS v(ord, user_name, action, target, create_time)
WHERE NOT EXISTS (
    SELECT 1 FROM admin_operation_log t
     WHERE t.user_name = v.user_name AND t.action = v.action AND t.target = v.target
)
ORDER BY v.ord;
