-- 总管会话与 Harness² 单步递归数据表（幂等）
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS chief_session (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    title VARCHAR(200) NOT NULL DEFAULT '新会话',
    project_id UUID,
    domain VARCHAR(40) NOT NULL DEFAULT 'general',
    risk_tier VARCHAR(4) NOT NULL DEFAULT 'T2',
    is_archived BOOLEAN NOT NULL DEFAULT false,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_session_data_id ON chief_session (data_id);
ALTER TABLE chief_session ADD COLUMN IF NOT EXISTS project_id UUID;
ALTER TABLE chief_session ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE chief_session ADD COLUMN IF NOT EXISTS expert_id UUID;
CREATE INDEX IF NOT EXISTS idx_chief_session_project
    ON chief_session (project_id, update_time DESC) WHERE project_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_chief_session_expert
    ON chief_session (expert_id, update_time DESC) WHERE expert_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS chief_project (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    status VARCHAR(30) NOT NULL DEFAULT '进行中',
    context JSONB NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_project_data_id ON chief_project (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_project_name
    ON chief_project (lower(name)) WHERE is_deleted = false;
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS is_archived BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS expert_id UUID;
ALTER TABLE chief_project
    ADD COLUMN IF NOT EXISTS phase VARCHAR(30) NOT NULL DEFAULT 'requirements';
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS requirement_html TEXT NOT NULL DEFAULT '';
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS requirement_text TEXT NOT NULL DEFAULT '';
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS requirement_confirmed_at TIMESTAMPTZ;
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS solution_html TEXT NOT NULL DEFAULT '';
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS solution_text TEXT NOT NULL DEFAULT '';
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS solution_confirmed_at TIMESTAMPTZ;
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS task_plan JSONB NOT NULL DEFAULT '{}';
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS task_plan_confirmed_at TIMESTAMPTZ;
ALTER TABLE chief_project
    ADD COLUMN IF NOT EXISTS execution_status VARCHAR(30) NOT NULL DEFAULT 'idle';
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS execution_error TEXT NOT NULL DEFAULT '';
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS execution_started_at TIMESTAMPTZ;
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS execution_finished_at TIMESTAMPTZ;
ALTER TABLE chief_project ADD COLUMN IF NOT EXISTS source_session_id UUID;

INSERT INTO chief_project (name, description, status, context, sort_order)
SELECT v.name, v.description, v.status, v.context::jsonb, v.ord
FROM (VALUES
    (
        1,
        '品牌年度内容规划',
        '年度内容主题、信息屋与渠道节奏',
        '进行中',
        '{"objective":"完成品牌年度内容规划与核心信息屋","scope":"品牌策略、内容主题、渠道节奏","constraints":["不跨项目讨论","事实不足时明确说明"]}'
    ),
    (
        2,
        '新品上市传播',
        '新品上市策略、主文案与首批物料',
        '进行中',
        '{"objective":"完成新品上市传播方案与首批交付物","scope":"上市策略、主文案、渠道物料","constraints":["不跨项目讨论","外部发布前必须审核"]}'
    ),
    (
        3,
        '客户提案复盘',
        '客户提案结果、偏差与改进项',
        '复盘',
        '{"objective":"复盘客户提案并沉淀改进项","scope":"提案结果、客户反馈、流程改进","constraints":["不跨项目讨论","客户信息需脱敏"]}'
    ),
    (
        4,
        '内部试验',
        '新方法、新工具和内部验证任务',
        '试验',
        '{"objective":"验证新方法与工具是否可推广","scope":"内部流程、Agent 能力、工具验证","constraints":["不跨项目讨论","试验结论需标注证据"]}'
    )
) AS v(ord, name, description, status, context)
WHERE NOT EXISTS (
    SELECT 1 FROM chief_project p
     WHERE lower(p.name) = lower(v.name) AND p.is_deleted = false
);

UPDATE chief_project p
   SET sort_order = v.ord,
       update_time = now()
  FROM (VALUES
      ('品牌年度内容规划', 1),
      ('新品上市传播', 2),
      ('客户提案复盘', 3),
      ('内部试验', 4)
  ) AS v(name, ord)
 WHERE lower(p.name) = lower(v.name)
   AND p.is_deleted = false;

CREATE TABLE IF NOT EXISTS chief_milestone (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT '未开始',
    starts_at DATE,
    due_at DATE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_milestone_data_id
    ON chief_milestone (data_id);
CREATE INDEX IF NOT EXISTS idx_chief_milestone_project
    ON chief_milestone (project_id, sort_order, id)
    WHERE is_deleted = false;

CREATE TABLE IF NOT EXISTS chief_task (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    milestone_id UUID NOT NULL,
    session_id UUID,
    title VARCHAR(200) NOT NULL,
    priority VARCHAR(10) NOT NULL DEFAULT 'P2',
    status VARCHAR(30) NOT NULL DEFAULT '未开始',
    due_at DATE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_task_data_id ON chief_task (data_id);
CREATE INDEX IF NOT EXISTS idx_chief_task_milestone
    ON chief_task (milestone_id, sort_order, id)
    WHERE is_deleted = false;
ALTER TABLE chief_task ADD COLUMN IF NOT EXISTS session_id UUID;
ALTER TABLE chief_task ADD COLUMN IF NOT EXISTS task_key VARCHAR(80);
ALTER TABLE chief_task ADD COLUMN IF NOT EXISTS description TEXT NOT NULL DEFAULT '';
ALTER TABLE chief_task
    ADD COLUMN IF NOT EXISTS acceptance_criteria TEXT NOT NULL DEFAULT '';
ALTER TABLE chief_task ADD COLUMN IF NOT EXISTS depends_on JSONB NOT NULL DEFAULT '[]';
ALTER TABLE chief_task
    ADD COLUMN IF NOT EXISTS auto_created BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE chief_task
    ADD COLUMN IF NOT EXISTS phase VARCHAR(30) NOT NULL DEFAULT 'communicating';
ALTER TABLE chief_task ADD COLUMN IF NOT EXISTS spec_confirmed_at TIMESTAMPTZ;
ALTER TABLE chief_task ADD COLUMN IF NOT EXISTS spec_snapshot JSONB NOT NULL DEFAULT '{}';
ALTER TABLE chief_task ADD COLUMN IF NOT EXISTS active_deliverable_id UUID;

CREATE TABLE IF NOT EXISTS chief_deliverable (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    task_id UUID NOT NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    latest_version_no INTEGER NOT NULL DEFAULT 0,
    draft_html TEXT NOT NULL DEFAULT '',
    draft_text TEXT NOT NULL DEFAULT '',
    draft_source_message_id UUID,
    draft_source_session_id UUID,
    draft_source_run_id UUID,
    draft_source_expert_id UUID,
    draft_update_time TIMESTAMPTZ,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_deliverable_data_id
    ON chief_deliverable (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_deliverable_task
    ON chief_deliverable (task_id) WHERE is_deleted = false;

CREATE TABLE IF NOT EXISTS chief_deliverable_version (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    deliverable_id UUID NOT NULL,
    version_no INTEGER NOT NULL,
    content_html TEXT NOT NULL,
    content_text TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    source_message_id UUID,
    source_session_id UUID,
    source_run_id UUID,
    source_expert_id UUID,
    confirmed_by UUID,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    create_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_deliverable_version_data_id
    ON chief_deliverable_version (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_deliverable_version_no
    ON chief_deliverable_version (deliverable_id, version_no);

CREATE TABLE IF NOT EXISTS chief_project_deliverable (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    kind VARCHAR(30) NOT NULL,
    title VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    latest_version_no INTEGER NOT NULL DEFAULT 0,
    draft_html TEXT NOT NULL DEFAULT '',
    draft_text TEXT NOT NULL DEFAULT '',
    source_deliverable_id UUID,
    source_version_id UUID,
    source_version_no INTEGER,
    draft_update_time TIMESTAMPTZ,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_project_deliverable_data_id
    ON chief_project_deliverable (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_project_deliverable_kind
    ON chief_project_deliverable (project_id, kind)
    WHERE is_deleted = false;
ALTER TABLE chief_project_deliverable
    ADD COLUMN IF NOT EXISTS source_deliverable_id UUID;
ALTER TABLE chief_project_deliverable
    ADD COLUMN IF NOT EXISTS source_version_id UUID;
ALTER TABLE chief_project_deliverable
    ADD COLUMN IF NOT EXISTS source_version_no INTEGER;

CREATE TABLE IF NOT EXISTS chief_project_deliverable_version (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    deliverable_id UUID NOT NULL,
    version_no INTEGER NOT NULL,
    content_html TEXT NOT NULL,
    content_text TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    source_deliverable_id UUID,
    source_version_id UUID,
    source_version_no INTEGER,
    confirmed_by UUID,
    confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    create_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_project_deliverable_version_data_id
    ON chief_project_deliverable_version (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_project_deliverable_version_no
    ON chief_project_deliverable_version (deliverable_id, version_no);
ALTER TABLE chief_project_deliverable_version
    ADD COLUMN IF NOT EXISTS source_deliverable_id UUID;
ALTER TABLE chief_project_deliverable_version
    ADD COLUMN IF NOT EXISTS source_version_id UUID;
ALTER TABLE chief_project_deliverable_version
    ADD COLUMN IF NOT EXISTS source_version_no INTEGER;

CREATE TABLE IF NOT EXISTS chief_document (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id UUID,
    project_id UUID,
    source_message_id UUID,
    title VARCHAR(200) NOT NULL,
    kind VARCHAR(30) NOT NULL DEFAULT 'custom',
    status VARCHAR(30) NOT NULL DEFAULT 'draft',
    content_html TEXT NOT NULL DEFAULT '',
    content_text TEXT NOT NULL DEFAULT '',
    create_by UUID,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
ALTER TABLE chief_document
    ALTER COLUMN session_id DROP NOT NULL;
ALTER TABLE chief_document
    ADD COLUMN IF NOT EXISTS kind VARCHAR(30) NOT NULL DEFAULT 'custom';
ALTER TABLE chief_document
    ADD COLUMN IF NOT EXISTS status VARCHAR(30) NOT NULL DEFAULT 'draft';
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_document_data_id
    ON chief_document (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_document_workflow_kind
    ON chief_document (project_id, kind)
    WHERE is_deleted = false
      AND kind IN ('requirements', 'solution', 'task_plan');
CREATE INDEX IF NOT EXISTS idx_chief_document_session
    ON chief_document (session_id, update_time DESC, id DESC)
    WHERE is_deleted = false;
CREATE INDEX IF NOT EXISTS idx_chief_document_project
    ON chief_document (project_id, update_time DESC, id DESC)
    WHERE project_id IS NOT NULL AND is_deleted = false;

CREATE TABLE IF NOT EXISTS chief_session_document (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    document_id UUID NOT NULL,
    add_by UUID,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_session_document_data_id
    ON chief_session_document (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_session_document_link
    ON chief_session_document (session_id, document_id);
CREATE INDEX IF NOT EXISTS idx_chief_session_document_session
    ON chief_session_document (session_id, id);

INSERT INTO chief_document (
    session_id, project_id, kind, title, status,
    content_html, content_text
)
SELECT p.source_session_id,
       deliverable.project_id,
       deliverable.kind,
       deliverable.title,
       deliverable.status,
       COALESCE(
           NULLIF(deliverable.draft_html, ''),
           CASE deliverable.kind
               WHEN 'requirements' THEN p.requirement_html
               WHEN 'solution' THEN p.solution_html
               ELSE ''
           END,
           ''
       ),
       COALESCE(
           NULLIF(deliverable.draft_text, ''),
           CASE deliverable.kind
               WHEN 'requirements' THEN p.requirement_text
               WHEN 'solution' THEN p.solution_text
               WHEN 'task_plan' THEN p.task_plan::text
               ELSE ''
           END,
           ''
       )
  FROM chief_project_deliverable deliverable
  JOIN chief_project p ON p.data_id = deliverable.project_id
 WHERE deliverable.is_deleted = false
   AND p.is_deleted = false
   AND NOT EXISTS (
       SELECT 1
         FROM chief_document document
        WHERE document.project_id = deliverable.project_id
          AND document.kind = deliverable.kind
          AND document.is_deleted = false
   );

CREATE TABLE IF NOT EXISTS chief_task_attachment (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    task_id UUID NOT NULL,
    file_uuid UUID NOT NULL,
    file_name VARCHAR(300) NOT NULL,
    file_ext VARCHAR(30) NOT NULL DEFAULT '',
    file_size BIGINT NOT NULL DEFAULT 0,
    mime_type VARCHAR(200) NOT NULL DEFAULT 'application/octet-stream',
    kind VARCHAR(20) NOT NULL DEFAULT '输入',
    sort_order INTEGER NOT NULL DEFAULT 0,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_task_attachment_data_id
    ON chief_task_attachment (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_task_attachment_file
    ON chief_task_attachment (task_id, file_uuid)
    WHERE is_deleted = false;
CREATE INDEX IF NOT EXISTS idx_chief_task_attachment_task
    ON chief_task_attachment (task_id, kind, sort_order, id)
    WHERE is_deleted = false;

ALTER TABLE chief_session ADD COLUMN IF NOT EXISTS task_id UUID;
CREATE INDEX IF NOT EXISTS idx_chief_session_task
    ON chief_session (task_id, update_time DESC) WHERE task_id IS NOT NULL;

DO $$
DECLARE
    project_row UUID;
    milestone_row UUID;
    task_row UUID;
    session_row UUID;
    milestone_item RECORD;
    task_item RECORD;
BEGIN
    SELECT data_id INTO project_row
      FROM chief_project
     WHERE name = '品牌年度内容规划' AND is_deleted = false
     LIMIT 1;
    IF project_row IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM chief_milestone
         WHERE project_id = project_row AND is_deleted = false
    ) THEN
        FOR milestone_item IN
            SELECT * FROM (VALUES
                (1, 'M2 内容策略定稿', '待验收', DATE '2026-11-20'),
                (2, '迭代 04 素材制作', '进行中', DATE '2026-11-20'),
                (3, '迭代 05 渠道分发', '未开始', DATE '2026-11-23')
            ) AS v(ord, title, status, due_at)
        LOOP
            INSERT INTO chief_milestone (
                project_id, title, status, due_at, sort_order
            )
            VALUES (
                project_row, milestone_item.title, milestone_item.status,
                milestone_item.due_at, milestone_item.ord
            )
            RETURNING data_id INTO milestone_row;

            FOR task_item IN
                SELECT * FROM (VALUES
                    (1, 1, '梳理核心信息屋', 'P0', '进行中', DATE '2026-11-19'),
                    (1, 2, '撰写发布会主文案', 'P1', '待审核', DATE '2026-11-20'),
                    (1, 3, '校对渠道物料清单', 'P2', '已完成', NULL::DATE),
                    (2, 1, '拍摄脚本评审', 'P1', '待审核', DATE '2026-11-20'),
                    (2, 2, '素材交付排期', 'P2', '进行中', DATE '2026-11-21'),
                    (3, 1, '分发渠道确认', 'P1', '未开始', DATE '2026-11-22'),
                    (3, 2, '投放数据埋点核对', 'P2', '未开始', DATE '2026-11-23')
                ) AS v(milestone_ord, task_ord, title, priority, status, due_at)
                WHERE v.milestone_ord = milestone_item.ord
            LOOP
                INSERT INTO chief_task (
                    project_id, milestone_id, title, priority, status,
                    due_at, sort_order
                )
                VALUES (
                    project_row, milestone_row, task_item.title,
                    task_item.priority, task_item.status, task_item.due_at,
                    task_item.task_ord
                )
                RETURNING data_id INTO task_row;
                INSERT INTO chief_session (
                    title, domain, risk_tier, project_id, task_id
                )
                VALUES (
                    task_item.title, 'project', 'T3', project_row, task_row
                )
                RETURNING data_id INTO session_row;
                UPDATE chief_task SET session_id = session_row
                 WHERE data_id = task_row;
            END LOOP;
        END LOOP;
    END IF;

    SELECT data_id INTO project_row
      FROM chief_project
     WHERE name = '新品上市传播' AND is_deleted = false
     LIMIT 1;
    IF project_row IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM chief_milestone
         WHERE project_id = project_row AND is_deleted = false
    ) THEN
        FOR milestone_item IN
            SELECT * FROM (VALUES
                (1, 'M1 上市节奏确认', '已完成', DATE '2026-11-12'),
                (2, 'M2 首波传播执行', '进行中', DATE '2026-11-25')
            ) AS v(ord, title, status, due_at)
        LOOP
            INSERT INTO chief_milestone (
                project_id, title, status, due_at, sort_order
            )
            VALUES (
                project_row, milestone_item.title, milestone_item.status,
                milestone_item.due_at, milestone_item.ord
            )
            RETURNING data_id INTO milestone_row;

            FOR task_item IN
                SELECT * FROM (VALUES
                    (1, 1, '上市时间线锁定', 'P0', '已完成', DATE '2026-11-12'),
                    (1, 2, '预热物料清单', 'P1', '待审核', DATE '2026-11-18'),
                    (2, 1, '首波通稿撰写', 'P1', '进行中', DATE '2026-11-22'),
                    (2, 2, 'KOL 名单对接', 'P2', '未开始', DATE '2026-11-24')
                ) AS v(milestone_ord, task_ord, title, priority, status, due_at)
                WHERE v.milestone_ord = milestone_item.ord
            LOOP
                INSERT INTO chief_task (
                    project_id, milestone_id, title, priority, status,
                    due_at, sort_order
                )
                VALUES (
                    project_row, milestone_row, task_item.title,
                    task_item.priority, task_item.status, task_item.due_at,
                    task_item.task_ord
                )
                RETURNING data_id INTO task_row;
                INSERT INTO chief_session (
                    title, domain, risk_tier, project_id, task_id
                )
                VALUES (
                    task_item.title, 'project', 'T3', project_row, task_row
                )
                RETURNING data_id INTO session_row;
                UPDATE chief_task SET session_id = session_row
                 WHERE data_id = task_row;
            END LOOP;
        END LOOP;
    END IF;
END $$;

-- 默认项目绑定最匹配的内置专家；已有绑定不会被覆盖。
UPDATE chief_project p
   SET expert_id = e.data_id, update_time = now()
  FROM ai_expert e
 WHERE p.expert_id IS NULL
   AND p.is_deleted = false
   AND e.is_deleted = false
   AND (
       (p.name IN ('品牌年度内容规划', '新品上市传播') AND e.name = '品牌策略专家')
       OR (p.name = '客户提案复盘' AND e.name = '客户成功专家')
       OR (p.name = '内部试验' AND e.name = '数据分析专家')
   );

UPDATE chief_session s
   SET expert_id = p.expert_id, update_time = now()
  FROM chief_project p
 WHERE s.project_id = p.data_id
   AND s.expert_id IS NULL
   AND p.expert_id IS NOT NULL
   AND s.is_deleted = false;

CREATE TABLE IF NOT EXISTS chief_message (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    run_id UUID,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    meta JSONB NOT NULL DEFAULT '{}',
    attachments JSONB NOT NULL DEFAULT '[]',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_message_data_id ON chief_message (data_id);
CREATE INDEX IF NOT EXISTS idx_chief_message_session ON chief_message (session_id, id);

-- 项目任务会话迁移到专家会话：保留历史消息并解除对总管会话的依赖。
DO $$
DECLARE
    task_record RECORD;
    expert_session_id UUID;
BEGIN
    FOR task_record IN
        SELECT task.data_id AS task_id,
               task.project_id,
               task.session_id AS old_session_id,
               task.title,
               project.expert_id
          FROM chief_task task
          JOIN chief_project project ON project.data_id = task.project_id
         WHERE task.is_deleted = false
           AND task.session_id IS NOT NULL
           AND project.expert_id IS NOT NULL
           AND NOT EXISTS (
               SELECT 1 FROM ai_expert_session
                WHERE task_id = task.data_id AND is_deleted = false
           )
    LOOP
        INSERT INTO ai_expert_session (
            expert_id, project_id, task_id, title
        )
        VALUES (
            task_record.expert_id,
            task_record.project_id,
            task_record.task_id,
            task_record.title
        )
        RETURNING data_id INTO expert_session_id;

        INSERT INTO ai_expert_message (
            session_id, run_id, role, content, attachments, meta, create_time
        )
        SELECT expert_session_id, message.run_id, message.role,
               message.content, message.attachments, message.meta,
               message.create_time
          FROM chief_message message
         WHERE message.session_id = task_record.old_session_id
           AND message.is_deleted = false
         ORDER BY message.id ASC;

        UPDATE chief_task
           SET session_id = expert_session_id, update_time = now()
         WHERE data_id = task_record.task_id;

        UPDATE chief_session
           SET is_deleted = true, update_time = now()
         WHERE data_id = task_record.old_session_id
           AND task_id = task_record.task_id;
    END LOOP;
END $$;

CREATE TABLE IF NOT EXISTS chief_harness (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    domain VARCHAR(40) NOT NULL,
    version INTEGER NOT NULL,
    parent_id UUID,
    components JSONB NOT NULL DEFAULT '{}',
    content_hash VARCHAR(64) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'proposed',
    evidence JSONB NOT NULL DEFAULT '{}',
    create_by UUID,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_harness_data_id ON chief_harness (data_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_harness_domain_version
    ON chief_harness (domain, version) WHERE is_deleted = false;
CREATE INDEX IF NOT EXISTS idx_chief_harness_active
    ON chief_harness (domain, status, create_time DESC);

CREATE TABLE IF NOT EXISTS chief_run (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    session_id UUID NOT NULL,
    user_message_id UUID,
    assistant_message_id UUID,
    status VARCHAR(30) NOT NULL DEFAULT 'running',
    domain VARCHAR(40) NOT NULL,
    risk_tier VARCHAR(4) NOT NULL,
    baseline_harness_id UUID,
    selected_harness_id UUID,
    expert_id UUID,
    model_name VARCHAR(200) NOT NULL DEFAULT '',
    answer TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    requires_approval BOOLEAN NOT NULL DEFAULT false,
    approved_by UUID,
    approve_time TIMESTAMPTZ,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_run_data_id ON chief_run (data_id);
CREATE INDEX IF NOT EXISTS idx_chief_run_session ON chief_run (session_id, id DESC);

CREATE TABLE IF NOT EXISTS chief_run_event (
    id BIGSERIAL PRIMARY KEY,
    run_id UUID NOT NULL,
    seq INTEGER NOT NULL,
    stage VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_run_event_seq ON chief_run_event (run_id, seq);

CREATE TABLE IF NOT EXISTS chief_candidate (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    run_id UUID NOT NULL,
    label VARCHAR(80) NOT NULL,
    scope VARCHAR(30) NOT NULL,
    step INTEGER NOT NULL DEFAULT 1,
    harness JSONB NOT NULL,
    harness_id UUID,
    answer TEXT NOT NULL DEFAULT '',
    score NUMERIC(8, 4) NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost NUMERIC(12, 6) NOT NULL DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'probed',
    trace JSONB NOT NULL DEFAULT '{}',
    create_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_candidate_data_id ON chief_candidate (data_id);
CREATE INDEX IF NOT EXISTS idx_chief_candidate_run ON chief_candidate (run_id, id);
ALTER TABLE chief_candidate ADD COLUMN IF NOT EXISTS step INTEGER NOT NULL DEFAULT 1;
ALTER TABLE chief_candidate ADD COLUMN IF NOT EXISTS input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chief_candidate ADD COLUMN IF NOT EXISTS output_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chief_candidate ADD COLUMN IF NOT EXISTS estimated_cost NUMERIC(12, 6) NOT NULL DEFAULT 0;

ALTER TABLE chief_run ADD COLUMN IF NOT EXISTS recursion_mode VARCHAR(20) NOT NULL DEFAULT 'sequential';
ALTER TABLE chief_run ADD COLUMN IF NOT EXISTS recursion_k INTEGER NOT NULL DEFAULT 1;
ALTER TABLE chief_run ADD COLUMN IF NOT EXISTS input_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chief_run ADD COLUMN IF NOT EXISTS output_tokens INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chief_run ADD COLUMN IF NOT EXISTS estimated_cost NUMERIC(12, 6) NOT NULL DEFAULT 0;
ALTER TABLE chief_run ADD COLUMN IF NOT EXISTS regression_passed BOOLEAN;
ALTER TABLE chief_run ADD COLUMN IF NOT EXISTS run_mode VARCHAR(20) NOT NULL DEFAULT 'harness';
ALTER TABLE chief_run ADD COLUMN IF NOT EXISTS auto_adopt_reason TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS chief_reflection (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    domain VARCHAR(40) NOT NULL,
    harness_id UUID NOT NULL,
    lessons JSONB NOT NULL DEFAULT '{}',
    score NUMERIC(8, 4) NOT NULL DEFAULT 0,
    create_by UUID,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_reflection_data_id ON chief_reflection (data_id);
CREATE INDEX IF NOT EXISTS idx_chief_reflection_domain ON chief_reflection (domain, create_time DESC);

CREATE TABLE IF NOT EXISTS chief_regression_case (
    id BIGSERIAL PRIMARY KEY,
    data_id UUID NOT NULL DEFAULT gen_random_uuid(),
    domain VARCHAR(40) NOT NULL,
    question TEXT NOT NULL,
    source_answer TEXT NOT NULL DEFAULT '',
    expected_score NUMERIC(8, 4) NOT NULL DEFAULT 0,
    source_run_id UUID,
    harness_id UUID,
    enabled BOOLEAN NOT NULL DEFAULT true,
    create_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_deleted BOOLEAN NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chief_regression_case_data_id
    ON chief_regression_case (data_id);
CREATE INDEX IF NOT EXISTS idx_chief_regression_case_domain
    ON chief_regression_case (domain, create_time DESC) WHERE enabled = true;

CREATE TABLE IF NOT EXISTS chief_setting (
    id INTEGER PRIMARY KEY DEFAULT 1,
    enabled BOOLEAN NOT NULL DEFAULT true,
    recursion_mode VARCHAR(20) NOT NULL DEFAULT 'sequential',
    recursion_k INTEGER NOT NULL DEFAULT 1,
    recursion_max INTEGER NOT NULL DEFAULT 2,
    regression_enabled BOOLEAN NOT NULL DEFAULT true,
    regression_cases INTEGER NOT NULL DEFAULT 2,
    auto_adopt_min_score NUMERIC(8, 2) NOT NULL DEFAULT 60,
    auto_adopt_min_gain NUMERIC(8, 2) NOT NULL DEFAULT 5,
    domain_experts JSONB NOT NULL DEFAULT '{}',
    update_by UUID,
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chief_setting_singleton CHECK (id = 1)
);
CREATE TABLE IF NOT EXISTS call_setting (
    id INTEGER PRIMARY KEY DEFAULT 1,
    push_to_talk_key VARCHAR(30) NOT NULL DEFAULT 'Escape',
    asr_url VARCHAR(500) NOT NULL DEFAULT 'https://api.deepseek.com/v1/tools/asr',
    tts_url VARCHAR(500) NOT NULL DEFAULT 'https://api.deepseek.com/v1/tools/tts',
    update_by UUID,
    update_time TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT call_setting_singleton CHECK (id = 1)
);
ALTER TABLE call_setting
    ALTER COLUMN push_to_talk_key SET DEFAULT 'Escape';

-- 单次模型调用成本通常低于 0.01 元，额度账本必须保留足够精度。
ALTER TABLE quota_model
    ALTER COLUMN used TYPE NUMERIC(14, 6) USING used::NUMERIC(14, 6);
