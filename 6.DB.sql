-- =============================================
-- 数据库：sa（PostgreSQL 18）
-- 来源：3.WBS.json 中 30 个数据库设计任务（WBS-DB-*），共 52 张业务表
-- 生成时间：2026-11-16
-- 依赖：INIT.SQL 中的 public.update_update_time() 触发器函数
-- =============================================


-- =============================================
-- WBS-DB-11-001: 知识片段与引用表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- knowledge_fragment 知识片段表 ----------
CREATE TABLE IF NOT EXISTS knowledge_fragment (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    fragment_no VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    source_ref VARCHAR(500) DEFAULT NULL,
    tags TEXT[] NOT NULL DEFAULT '{}'::text[],
    version_no INTEGER NOT NULL DEFAULT 1,
    confidence NUMERIC(5,4) DEFAULT NULL CHECK (confidence >= 0 AND confidence <= 1),
    fragment_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (fragment_status IN ('active','archived')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE knowledge_fragment IS '知识片段表';
COMMENT ON COLUMN knowledge_fragment.id IS '内部主键';
COMMENT ON COLUMN knowledge_fragment.uuid IS '外部唯一标识';
COMMENT ON COLUMN knowledge_fragment.fragment_no IS '片段编号';
COMMENT ON COLUMN knowledge_fragment.title IS '片段标题';
COMMENT ON COLUMN knowledge_fragment.content IS '片段内容';
COMMENT ON COLUMN knowledge_fragment.source_type IS '来源类型（document/manual/meeting/email）';
COMMENT ON COLUMN knowledge_fragment.source_ref IS '来源标识（文档ID/链接/文件名）';
COMMENT ON COLUMN knowledge_fragment.tags IS '标签集合';
COMMENT ON COLUMN knowledge_fragment.version_no IS '片段版本号';
COMMENT ON COLUMN knowledge_fragment.confidence IS '置信度';
COMMENT ON COLUMN knowledge_fragment.fragment_status IS '片段状态';
COMMENT ON COLUMN knowledge_fragment.create_by IS '创建人ID';
COMMENT ON COLUMN knowledge_fragment.update_by IS '更新人ID';
COMMENT ON COLUMN knowledge_fragment.delete_by IS '删除人ID';
COMMENT ON COLUMN knowledge_fragment.create_time IS '创建时间';
COMMENT ON COLUMN knowledge_fragment.update_time IS '更新时间';
COMMENT ON COLUMN knowledge_fragment.delete_time IS '删除时间';
COMMENT ON COLUMN knowledge_fragment.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN knowledge_fragment.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_fragment_uuid ON knowledge_fragment (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_fragment_fragment_no ON knowledge_fragment (fragment_no);
CREATE INDEX IF NOT EXISTS idx_knowledge_fragment_tags ON knowledge_fragment USING GIN (tags);
CREATE INDEX IF NOT EXISTS idx_knowledge_fragment_version_no ON knowledge_fragment (version_no);
CREATE INDEX IF NOT EXISTS idx_knowledge_fragment_source_type ON knowledge_fragment (source_type);
CREATE INDEX IF NOT EXISTS idx_knowledge_fragment_title ON knowledge_fragment (title);

DROP TRIGGER IF EXISTS trigger_knowledge_fragment_update_time ON knowledge_fragment;
CREATE TRIGGER trigger_knowledge_fragment_update_time
BEFORE UPDATE ON knowledge_fragment
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- fragment_citation 片段引用记录表 ----------
CREATE TABLE IF NOT EXISTS fragment_citation (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    fragment_id BIGINT NOT NULL REFERENCES knowledge_fragment(id),
    target_type VARCHAR(32) NOT NULL,
    target_id BIGINT DEFAULT NULL,
    target_uuid UUID DEFAULT NULL,
    location VARCHAR(200) DEFAULT NULL,
    quote_text TEXT DEFAULT NULL,
    confidence NUMERIC(5,4) DEFAULT NULL CHECK (confidence >= 0 AND confidence <= 1),
    cited_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE fragment_citation IS '片段引用记录表';
COMMENT ON COLUMN fragment_citation.id IS '内部主键';
COMMENT ON COLUMN fragment_citation.uuid IS '外部唯一标识';
COMMENT ON COLUMN fragment_citation.fragment_id IS '片段ID';
COMMENT ON COLUMN fragment_citation.target_type IS '引用目标类型';
COMMENT ON COLUMN fragment_citation.target_id IS '引用目标ID';
COMMENT ON COLUMN fragment_citation.target_uuid IS '引用目标UUID';
COMMENT ON COLUMN fragment_citation.location IS '引用位置（页码/段落/时间戳）';
COMMENT ON COLUMN fragment_citation.quote_text IS '引用原文';
COMMENT ON COLUMN fragment_citation.confidence IS '引用置信度';
COMMENT ON COLUMN fragment_citation.cited_time IS '引用时间';
COMMENT ON COLUMN fragment_citation.create_by IS '创建人ID';
COMMENT ON COLUMN fragment_citation.update_by IS '更新人ID';
COMMENT ON COLUMN fragment_citation.delete_by IS '删除人ID';
COMMENT ON COLUMN fragment_citation.create_time IS '创建时间';
COMMENT ON COLUMN fragment_citation.update_time IS '更新时间';
COMMENT ON COLUMN fragment_citation.delete_time IS '删除时间';
COMMENT ON COLUMN fragment_citation.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN fragment_citation.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_fragment_citation_uuid ON fragment_citation (uuid);
CREATE INDEX IF NOT EXISTS idx_fragment_citation_fragment_id ON fragment_citation (fragment_id);
CREATE INDEX IF NOT EXISTS idx_fragment_citation_target_type_target_id ON fragment_citation (target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_fragment_citation_cited_time ON fragment_citation (cited_time);

DROP TRIGGER IF EXISTS trigger_fragment_citation_update_time ON fragment_citation;
CREATE TRIGGER trigger_fragment_citation_update_time
BEFORE UPDATE ON fragment_citation
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-11-002: 客户档案与项目资料表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- fact_customer 客户档案事实表 ----------
CREATE TABLE IF NOT EXISTS fact_customer (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    customer_no VARCHAR(64) NOT NULL,
    customer_name VARCHAR(200) NOT NULL,
    company_name VARCHAR(200) DEFAULT NULL,
    contact_name VARCHAR(100) DEFAULT NULL,
    contact_phone VARCHAR(50) DEFAULT NULL,
    contact_email VARCHAR(150) DEFAULT NULL,
    industry VARCHAR(100) DEFAULT NULL,
    tier_tag VARCHAR(32) DEFAULT NULL,
    interaction_summary TEXT DEFAULT NULL,
    last_interaction_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    source_type VARCHAR(32) DEFAULT NULL,
    customer_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (customer_status IN ('active','inactive')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE fact_customer IS '客户档案事实表';
COMMENT ON COLUMN fact_customer.id IS '内部主键';
COMMENT ON COLUMN fact_customer.uuid IS '外部唯一标识';
COMMENT ON COLUMN fact_customer.customer_no IS '客户编号';
COMMENT ON COLUMN fact_customer.customer_name IS '客户名称';
COMMENT ON COLUMN fact_customer.company_name IS '公司名称';
COMMENT ON COLUMN fact_customer.contact_name IS '联系人';
COMMENT ON COLUMN fact_customer.contact_phone IS '联系电话';
COMMENT ON COLUMN fact_customer.contact_email IS '联系邮箱';
COMMENT ON COLUMN fact_customer.industry IS '所属行业';
COMMENT ON COLUMN fact_customer.tier_tag IS '客户分层标签';
COMMENT ON COLUMN fact_customer.interaction_summary IS '历史交互摘要';
COMMENT ON COLUMN fact_customer.last_interaction_time IS '最近交互时间';
COMMENT ON COLUMN fact_customer.source_type IS '资料来源';
COMMENT ON COLUMN fact_customer.customer_status IS '档案状态';
COMMENT ON COLUMN fact_customer.create_by IS '创建人ID';
COMMENT ON COLUMN fact_customer.update_by IS '更新人ID';
COMMENT ON COLUMN fact_customer.delete_by IS '删除人ID';
COMMENT ON COLUMN fact_customer.create_time IS '创建时间';
COMMENT ON COLUMN fact_customer.update_time IS '更新时间';
COMMENT ON COLUMN fact_customer.delete_time IS '删除时间';
COMMENT ON COLUMN fact_customer.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN fact_customer.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_customer_uuid ON fact_customer (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_customer_customer_no ON fact_customer (customer_no);
CREATE INDEX IF NOT EXISTS idx_fact_customer_customer_name ON fact_customer (customer_name);
CREATE INDEX IF NOT EXISTS idx_fact_customer_tier_tag ON fact_customer (tier_tag);
CREATE INDEX IF NOT EXISTS idx_fact_customer_contact_phone ON fact_customer (contact_phone);

DROP TRIGGER IF EXISTS trigger_fact_customer_update_time ON fact_customer;
CREATE TRIGGER trigger_fact_customer_update_time
BEFORE UPDATE ON fact_customer
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- project_material 项目资料表 ----------
CREATE TABLE IF NOT EXISTS project_material (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    material_no VARCHAR(64) NOT NULL,
    material_name VARCHAR(200) NOT NULL,
    material_type VARCHAR(32) NOT NULL CHECK (material_type IN ('template','solution','retrospect')),
    customer_id BIGINT DEFAULT NULL REFERENCES fact_customer(id),
    tags TEXT[] NOT NULL DEFAULT '{}'::text[],
    content TEXT DEFAULT NULL,
    file_uuid UUID DEFAULT NULL,
    version_no INTEGER NOT NULL DEFAULT 1,
    material_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (material_status IN ('active','archived')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE project_material IS '项目资料表';
COMMENT ON COLUMN project_material.id IS '内部主键';
COMMENT ON COLUMN project_material.uuid IS '外部唯一标识';
COMMENT ON COLUMN project_material.material_no IS '资料编号';
COMMENT ON COLUMN project_material.material_name IS '资料名称';
COMMENT ON COLUMN project_material.material_type IS '资料类型（模板/历史方案/复盘记录）';
COMMENT ON COLUMN project_material.customer_id IS '关联客户档案ID';
COMMENT ON COLUMN project_material.tags IS '标签集合';
COMMENT ON COLUMN project_material.content IS '资料内容';
COMMENT ON COLUMN project_material.file_uuid IS '附件UUID';
COMMENT ON COLUMN project_material.version_no IS '资料版本号';
COMMENT ON COLUMN project_material.material_status IS '资料状态';
COMMENT ON COLUMN project_material.create_by IS '创建人ID';
COMMENT ON COLUMN project_material.update_by IS '更新人ID';
COMMENT ON COLUMN project_material.delete_by IS '删除人ID';
COMMENT ON COLUMN project_material.create_time IS '创建时间';
COMMENT ON COLUMN project_material.update_time IS '更新时间';
COMMENT ON COLUMN project_material.delete_time IS '删除时间';
COMMENT ON COLUMN project_material.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN project_material.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_material_uuid ON project_material (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_material_material_no ON project_material (material_no);
CREATE INDEX IF NOT EXISTS idx_project_material_material_name ON project_material (material_name);
CREATE INDEX IF NOT EXISTS idx_project_material_material_type ON project_material (material_type);
CREATE INDEX IF NOT EXISTS idx_project_material_customer_id ON project_material (customer_id);
CREATE INDEX IF NOT EXISTS idx_project_material_tags ON project_material USING GIN (tags);

DROP TRIGGER IF EXISTS trigger_project_material_update_time ON project_material;
CREATE TRIGGER trigger_project_material_update_time
BEFORE UPDATE ON project_material
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-11-003: 偏好模板与审核反哺表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- preference_template 偏好模板表 ----------
CREATE TABLE IF NOT EXISTS preference_template (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    template_no VARCHAR(64) NOT NULL,
    template_name VARCHAR(200) NOT NULL,
    scene_type VARCHAR(32) DEFAULT NULL,
    style_desc TEXT DEFAULT NULL,
    format_spec TEXT DEFAULT NULL,
    forbidden_expressions TEXT DEFAULT NULL,
    source_type VARCHAR(32) DEFAULT NULL,
    version_no INTEGER NOT NULL DEFAULT 1,
    template_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (template_status IN ('active','disabled')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE preference_template IS '偏好模板表';
COMMENT ON COLUMN preference_template.id IS '内部主键';
COMMENT ON COLUMN preference_template.uuid IS '外部唯一标识';
COMMENT ON COLUMN preference_template.template_no IS '模板编号';
COMMENT ON COLUMN preference_template.template_name IS '模板名称';
COMMENT ON COLUMN preference_template.scene_type IS '适用场景';
COMMENT ON COLUMN preference_template.style_desc IS '风格描述';
COMMENT ON COLUMN preference_template.format_spec IS '格式规范';
COMMENT ON COLUMN preference_template.forbidden_expressions IS '禁用表达';
COMMENT ON COLUMN preference_template.source_type IS '模板来源';
COMMENT ON COLUMN preference_template.version_no IS '模板版本号';
COMMENT ON COLUMN preference_template.template_status IS '模板状态';
COMMENT ON COLUMN preference_template.create_by IS '创建人ID';
COMMENT ON COLUMN preference_template.update_by IS '更新人ID';
COMMENT ON COLUMN preference_template.delete_by IS '删除人ID';
COMMENT ON COLUMN preference_template.create_time IS '创建时间';
COMMENT ON COLUMN preference_template.update_time IS '更新时间';
COMMENT ON COLUMN preference_template.delete_time IS '删除时间';
COMMENT ON COLUMN preference_template.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN preference_template.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_preference_template_uuid ON preference_template (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_preference_template_template_no ON preference_template (template_no);
CREATE INDEX IF NOT EXISTS idx_preference_template_template_name ON preference_template (template_name);
CREATE INDEX IF NOT EXISTS idx_preference_template_scene_type ON preference_template (scene_type);

DROP TRIGGER IF EXISTS trigger_preference_template_update_time ON preference_template;
CREATE TRIGGER trigger_preference_template_update_time
BEFORE UPDATE ON preference_template
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- fact_feedback 审核反哺事实表 ----------
CREATE TABLE IF NOT EXISTS fact_feedback (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    source_review_id BIGINT DEFAULT NULL,
    source_review_type VARCHAR(32) DEFAULT NULL,
    template_id BIGINT DEFAULT NULL REFERENCES preference_template(id),
    fact_type VARCHAR(32) NOT NULL CHECK (fact_type IN ('style','format','forbidden')),
    fact_content TEXT NOT NULL,
    diff_content TEXT DEFAULT NULL,
    confirm_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (confirm_status IN ('pending','confirmed','rejected')),
    confirmed_by BIGINT DEFAULT NULL,
    confirmed_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE fact_feedback IS '审核反哺事实表';
COMMENT ON COLUMN fact_feedback.id IS '内部主键';
COMMENT ON COLUMN fact_feedback.uuid IS '外部唯一标识';
COMMENT ON COLUMN fact_feedback.source_review_id IS '来源审核记录ID';
COMMENT ON COLUMN fact_feedback.source_review_type IS '来源审核类型';
COMMENT ON COLUMN fact_feedback.template_id IS '关联偏好模板ID';
COMMENT ON COLUMN fact_feedback.fact_type IS '事实类型（风格/格式/禁用表达）';
COMMENT ON COLUMN fact_feedback.fact_content IS '事实条目内容';
COMMENT ON COLUMN fact_feedback.diff_content IS '审核差异内容';
COMMENT ON COLUMN fact_feedback.confirm_status IS '确认状态';
COMMENT ON COLUMN fact_feedback.confirmed_by IS '确认人ID';
COMMENT ON COLUMN fact_feedback.confirmed_time IS '确认时间';
COMMENT ON COLUMN fact_feedback.create_by IS '创建人ID';
COMMENT ON COLUMN fact_feedback.update_by IS '更新人ID';
COMMENT ON COLUMN fact_feedback.delete_by IS '删除人ID';
COMMENT ON COLUMN fact_feedback.create_time IS '创建时间';
COMMENT ON COLUMN fact_feedback.update_time IS '更新时间';
COMMENT ON COLUMN fact_feedback.delete_time IS '删除时间';
COMMENT ON COLUMN fact_feedback.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN fact_feedback.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_fact_feedback_uuid ON fact_feedback (uuid);
CREATE INDEX IF NOT EXISTS idx_fact_feedback_source_review_id_source_review_type ON fact_feedback (source_review_id, source_review_type);
CREATE INDEX IF NOT EXISTS idx_fact_feedback_template_id ON fact_feedback (template_id);
CREATE INDEX IF NOT EXISTS idx_fact_feedback_fact_type ON fact_feedback (fact_type);
CREATE INDEX IF NOT EXISTS idx_fact_feedback_confirm_status ON fact_feedback (confirm_status);

DROP TRIGGER IF EXISTS trigger_fact_feedback_update_time ON fact_feedback;
CREATE TRIGGER trigger_fact_feedback_update_time
BEFORE UPDATE ON fact_feedback
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-8-001: 分级规则表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- t_level_rule T1-T4 分级规则表 ----------
CREATE TABLE IF NOT EXISTS t_level_rule (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    rule_no VARCHAR(64) NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    t_level VARCHAR(4) NOT NULL CHECK (t_level IN ('T1','T2','T3','T4')),
    scene_list TEXT DEFAULT NULL,
    example_actions TEXT DEFAULT NULL,
    rule_condition JSONB NOT NULL DEFAULT '{}'::jsonb,
    rule_version VARCHAR(20) NOT NULL DEFAULT 'v1',
    priority_level INTEGER NOT NULL DEFAULT 0,
    is_enabled SMALLINT NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    effective_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    expire_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE t_level_rule IS 'T1-T4 分级规则表';
COMMENT ON COLUMN t_level_rule.id IS '内部主键';
COMMENT ON COLUMN t_level_rule.uuid IS '外部唯一标识';
COMMENT ON COLUMN t_level_rule.rule_no IS '规则编号';
COMMENT ON COLUMN t_level_rule.rule_name IS '规则名称';
COMMENT ON COLUMN t_level_rule.t_level IS '风险等级';
COMMENT ON COLUMN t_level_rule.scene_list IS 'T1-T4 场景清单';
COMMENT ON COLUMN t_level_rule.example_actions IS '示例动作';
COMMENT ON COLUMN t_level_rule.rule_condition IS '规则条件';
COMMENT ON COLUMN t_level_rule.rule_version IS '规则版本';
COMMENT ON COLUMN t_level_rule.priority_level IS '规则优先级';
COMMENT ON COLUMN t_level_rule.is_enabled IS '启停状态';
COMMENT ON COLUMN t_level_rule.effective_time IS '生效时间';
COMMENT ON COLUMN t_level_rule.expire_time IS '失效时间';
COMMENT ON COLUMN t_level_rule.create_by IS '创建人ID';
COMMENT ON COLUMN t_level_rule.update_by IS '更新人ID';
COMMENT ON COLUMN t_level_rule.delete_by IS '删除人ID';
COMMENT ON COLUMN t_level_rule.create_time IS '创建时间';
COMMENT ON COLUMN t_level_rule.update_time IS '更新时间';
COMMENT ON COLUMN t_level_rule.delete_time IS '删除时间';
COMMENT ON COLUMN t_level_rule.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN t_level_rule.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_t_level_rule_uuid ON t_level_rule (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_t_level_rule_rule_no_rule_version ON t_level_rule (rule_no, rule_version);
CREATE INDEX IF NOT EXISTS idx_t_level_rule_t_level ON t_level_rule (t_level);
CREATE INDEX IF NOT EXISTS idx_t_level_rule_is_enabled ON t_level_rule (is_enabled);
CREATE INDEX IF NOT EXISTS idx_t_level_rule_rule_no_create_time ON t_level_rule (rule_no, create_time);

DROP TRIGGER IF EXISTS trigger_t_level_rule_update_time ON t_level_rule;
CREATE TRIGGER trigger_t_level_rule_update_time
BEFORE UPDATE ON t_level_rule
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-8-002: 判定依据与人工覆盖表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- t_level_judgement 分级判定与人工覆盖表 ----------
CREATE TABLE IF NOT EXISTS t_level_judgement (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    task_id BIGINT NOT NULL,
    task_type VARCHAR(20) NOT NULL DEFAULT 'agent_task' CHECK (task_type IN ('agent_task','atomic_task')),
    matched_rule_id BIGINT DEFAULT NULL REFERENCES t_level_rule(id),
    matched_rule_version VARCHAR(20) DEFAULT NULL,
    judged_level VARCHAR(4) NOT NULL CHECK (judged_level IN ('T1','T2','T3','T4')),
    judge_source VARCHAR(20) NOT NULL DEFAULT 'auto' CHECK (judge_source IN ('auto','manual')),
    judge_reason TEXT DEFAULT NULL,
    judge_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    override_by BIGINT DEFAULT NULL,
    override_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    override_level VARCHAR(4) DEFAULT NULL CHECK (override_level IN ('T1','T2','T3','T4')),
    override_reason VARCHAR(500) DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE t_level_judgement IS '分级判定与人工覆盖表';
COMMENT ON COLUMN t_level_judgement.id IS '内部主键';
COMMENT ON COLUMN t_level_judgement.uuid IS '外部唯一标识';
COMMENT ON COLUMN t_level_judgement.task_id IS '任务ID';
COMMENT ON COLUMN t_level_judgement.task_type IS '任务类型';
COMMENT ON COLUMN t_level_judgement.matched_rule_id IS '命中规则ID';
COMMENT ON COLUMN t_level_judgement.matched_rule_version IS '命中规则版本';
COMMENT ON COLUMN t_level_judgement.judged_level IS '判定等级';
COMMENT ON COLUMN t_level_judgement.judge_source IS '判定来源';
COMMENT ON COLUMN t_level_judgement.judge_reason IS '判定依据';
COMMENT ON COLUMN t_level_judgement.judge_time IS '判定时间';
COMMENT ON COLUMN t_level_judgement.override_by IS '人工覆盖人ID';
COMMENT ON COLUMN t_level_judgement.override_time IS '人工覆盖时间';
COMMENT ON COLUMN t_level_judgement.override_level IS '覆盖后等级';
COMMENT ON COLUMN t_level_judgement.override_reason IS '覆盖原因';
COMMENT ON COLUMN t_level_judgement.create_by IS '创建人ID';
COMMENT ON COLUMN t_level_judgement.update_by IS '更新人ID';
COMMENT ON COLUMN t_level_judgement.delete_by IS '删除人ID';
COMMENT ON COLUMN t_level_judgement.create_time IS '创建时间';
COMMENT ON COLUMN t_level_judgement.update_time IS '更新时间';
COMMENT ON COLUMN t_level_judgement.delete_time IS '删除时间';
COMMENT ON COLUMN t_level_judgement.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN t_level_judgement.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_t_level_judgement_uuid ON t_level_judgement (uuid);
CREATE INDEX IF NOT EXISTS idx_t_level_judgement_task_id ON t_level_judgement (task_id);
CREATE INDEX IF NOT EXISTS idx_t_level_judgement_task_id_judge_time ON t_level_judgement (task_id, judge_time);
CREATE INDEX IF NOT EXISTS idx_t_level_judgement_judged_level ON t_level_judgement (judged_level);
CREATE INDEX IF NOT EXISTS idx_t_level_judgement_matched_rule_id ON t_level_judgement (matched_rule_id);

DROP TRIGGER IF EXISTS trigger_t_level_judgement_update_time ON t_level_judgement;
CREATE TRIGGER trigger_t_level_judgement_update_time
BEFORE UPDATE ON t_level_judgement
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-9-001: 围栏规则表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- fence_rule 围栏规则表 ----------
CREATE TABLE IF NOT EXISTS fence_rule (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    rule_no VARCHAR(64) NOT NULL,
    rule_name VARCHAR(200) NOT NULL,
    rule_type VARCHAR(20) NOT NULL CHECK (rule_type IN ('range','veto','time','threshold')),
    scene_type VARCHAR(32) DEFAULT NULL,
    rule_condition JSONB NOT NULL DEFAULT '{}'::jsonb,
    threshold_value NUMERIC(18,4) DEFAULT NULL,
    threshold_unit VARCHAR(32) DEFAULT NULL,
    effective_start TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    effective_end TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    rule_version VARCHAR(20) NOT NULL DEFAULT 'v1',
    is_enabled SMALLINT NOT NULL DEFAULT 1 CHECK (is_enabled IN (0, 1)),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE fence_rule IS '围栏规则表';
COMMENT ON COLUMN fence_rule.id IS '内部主键';
COMMENT ON COLUMN fence_rule.uuid IS '外部唯一标识';
COMMENT ON COLUMN fence_rule.rule_no IS '规则编号';
COMMENT ON COLUMN fence_rule.rule_name IS '规则名称';
COMMENT ON COLUMN fence_rule.rule_type IS '规则类型（范围/否决/时间/阈值）';
COMMENT ON COLUMN fence_rule.scene_type IS '适用场景';
COMMENT ON COLUMN fence_rule.rule_condition IS '规则条件';
COMMENT ON COLUMN fence_rule.threshold_value IS '阈值';
COMMENT ON COLUMN fence_rule.threshold_unit IS '阈值单位';
COMMENT ON COLUMN fence_rule.effective_start IS '生效开始时间';
COMMENT ON COLUMN fence_rule.effective_end IS '生效结束时间';
COMMENT ON COLUMN fence_rule.rule_version IS '规则版本';
COMMENT ON COLUMN fence_rule.is_enabled IS '启停状态';
COMMENT ON COLUMN fence_rule.create_by IS '创建人ID';
COMMENT ON COLUMN fence_rule.update_by IS '更新人ID';
COMMENT ON COLUMN fence_rule.delete_by IS '删除人ID';
COMMENT ON COLUMN fence_rule.create_time IS '创建时间';
COMMENT ON COLUMN fence_rule.update_time IS '更新时间';
COMMENT ON COLUMN fence_rule.delete_time IS '删除时间';
COMMENT ON COLUMN fence_rule.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN fence_rule.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_fence_rule_uuid ON fence_rule (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_fence_rule_rule_no_rule_version ON fence_rule (rule_no, rule_version);
CREATE INDEX IF NOT EXISTS idx_fence_rule_rule_type ON fence_rule (rule_type);
CREATE INDEX IF NOT EXISTS idx_fence_rule_scene_type ON fence_rule (scene_type);
CREATE INDEX IF NOT EXISTS idx_fence_rule_is_enabled ON fence_rule (is_enabled);

DROP TRIGGER IF EXISTS trigger_fence_rule_update_time ON fence_rule;
CREATE TRIGGER trigger_fence_rule_update_time
BEFORE UPDATE ON fence_rule
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-9-002: 校验记录与动作快照表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- fence_check_log 围栏校验记录表 ----------
CREATE TABLE IF NOT EXISTS fence_check_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    task_id BIGINT NOT NULL,
    task_type VARCHAR(20) NOT NULL DEFAULT 'agent_task' CHECK (task_type IN ('agent_task','atomic_task')),
    chain_id VARCHAR(64) DEFAULT NULL,
    matched_rule_id BIGINT DEFAULT NULL REFERENCES fence_rule(id),
    rule_version VARCHAR(20) DEFAULT NULL,
    check_result VARCHAR(20) NOT NULL CHECK (check_result IN ('pass','blocked','degraded')),
    degrade_reason VARCHAR(500) DEFAULT NULL,
    action_type VARCHAR(64) DEFAULT NULL,
    action_target VARCHAR(200) DEFAULT NULL,
    snapshot_id BIGINT DEFAULT NULL,
    check_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE fence_check_log IS '围栏校验记录表';
COMMENT ON COLUMN fence_check_log.id IS '内部主键';
COMMENT ON COLUMN fence_check_log.uuid IS '外部唯一标识';
COMMENT ON COLUMN fence_check_log.task_id IS '任务ID';
COMMENT ON COLUMN fence_check_log.task_type IS '任务类型';
COMMENT ON COLUMN fence_check_log.chain_id IS '链路ID';
COMMENT ON COLUMN fence_check_log.matched_rule_id IS '命中规则ID';
COMMENT ON COLUMN fence_check_log.rule_version IS '命中规则版本';
COMMENT ON COLUMN fence_check_log.check_result IS '校验结果';
COMMENT ON COLUMN fence_check_log.degrade_reason IS '降级原因';
COMMENT ON COLUMN fence_check_log.action_type IS '动作类型';
COMMENT ON COLUMN fence_check_log.action_target IS '动作对象';
COMMENT ON COLUMN fence_check_log.snapshot_id IS '动作快照ID';
COMMENT ON COLUMN fence_check_log.check_time IS '校验时间';
COMMENT ON COLUMN fence_check_log.create_by IS '创建人ID';
COMMENT ON COLUMN fence_check_log.update_by IS '更新人ID';
COMMENT ON COLUMN fence_check_log.delete_by IS '删除人ID';
COMMENT ON COLUMN fence_check_log.create_time IS '创建时间';
COMMENT ON COLUMN fence_check_log.update_time IS '更新时间';
COMMENT ON COLUMN fence_check_log.delete_time IS '删除时间';
COMMENT ON COLUMN fence_check_log.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN fence_check_log.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_fence_check_log_uuid ON fence_check_log (uuid);
CREATE INDEX IF NOT EXISTS idx_fence_check_log_task_id ON fence_check_log (task_id);
CREATE INDEX IF NOT EXISTS idx_fence_check_log_task_id_check_time ON fence_check_log (task_id, check_time);
CREATE INDEX IF NOT EXISTS idx_fence_check_log_check_time ON fence_check_log (check_time);
CREATE INDEX IF NOT EXISTS idx_fence_check_log_chain_id ON fence_check_log (chain_id);
CREATE INDEX IF NOT EXISTS idx_fence_check_log_matched_rule_id ON fence_check_log (matched_rule_id);

DROP TRIGGER IF EXISTS trigger_fence_check_log_update_time ON fence_check_log;
CREATE TRIGGER trigger_fence_check_log_update_time
BEFORE UPDATE ON fence_check_log
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- action_snapshot 动作前后快照表 ----------
CREATE TABLE IF NOT EXISTS action_snapshot (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    check_log_id BIGINT DEFAULT NULL REFERENCES fence_check_log(id),
    action_type VARCHAR(64) NOT NULL,
    action_target VARCHAR(200) DEFAULT NULL,
    before_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_data JSONB DEFAULT NULL,
    rollback_status VARCHAR(20) NOT NULL DEFAULT 'none' CHECK (rollback_status IN ('none','pending','rolled_back','failed')),
    rollback_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    rollback_by BIGINT DEFAULT NULL,
    snapshot_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE action_snapshot IS '动作前后快照表';
COMMENT ON COLUMN action_snapshot.id IS '内部主键';
COMMENT ON COLUMN action_snapshot.uuid IS '外部唯一标识';
COMMENT ON COLUMN action_snapshot.check_log_id IS '围栏校验记录ID';
COMMENT ON COLUMN action_snapshot.action_type IS '动作类型';
COMMENT ON COLUMN action_snapshot.action_target IS '动作对象';
COMMENT ON COLUMN action_snapshot.before_data IS '动作前完整数据';
COMMENT ON COLUMN action_snapshot.after_data IS '动作后数据';
COMMENT ON COLUMN action_snapshot.rollback_status IS '回滚状态';
COMMENT ON COLUMN action_snapshot.rollback_time IS '回滚时间';
COMMENT ON COLUMN action_snapshot.rollback_by IS '回滚人ID';
COMMENT ON COLUMN action_snapshot.snapshot_time IS '快照时间';
COMMENT ON COLUMN action_snapshot.create_by IS '创建人ID';
COMMENT ON COLUMN action_snapshot.update_by IS '更新人ID';
COMMENT ON COLUMN action_snapshot.delete_by IS '删除人ID';
COMMENT ON COLUMN action_snapshot.create_time IS '创建时间';
COMMENT ON COLUMN action_snapshot.update_time IS '更新时间';
COMMENT ON COLUMN action_snapshot.delete_time IS '删除时间';
COMMENT ON COLUMN action_snapshot.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN action_snapshot.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_action_snapshot_uuid ON action_snapshot (uuid);
CREATE INDEX IF NOT EXISTS idx_action_snapshot_check_log_id ON action_snapshot (check_log_id);
CREATE INDEX IF NOT EXISTS idx_action_snapshot_rollback_status ON action_snapshot (rollback_status);

DROP TRIGGER IF EXISTS trigger_action_snapshot_update_time ON action_snapshot;
CREATE TRIGGER trigger_action_snapshot_update_time
BEFORE UPDATE ON action_snapshot
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-7-001: 全局模式配置表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- runtime_mode_config 全局运行模式配置表 ----------
CREATE TABLE IF NOT EXISTS runtime_mode_config (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    config_key VARCHAR(64) NOT NULL DEFAULT 'global',
    default_mode VARCHAR(20) NOT NULL DEFAULT 'copilot' CHECK (default_mode IN ('copilot','autopilot')),
    global_switch VARCHAR(20) NOT NULL DEFAULT 'on' CHECK (global_switch IN ('on','off')),
    circuit_breaker_status VARCHAR(20) NOT NULL DEFAULT 'closed' CHECK (circuit_breaker_status IN ('closed','open','half_open')),
    circuit_breaker_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    operator_id BIGINT DEFAULT NULL,
    operator_name VARCHAR(100) DEFAULT NULL,
    config_version INTEGER NOT NULL DEFAULT 1,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE runtime_mode_config IS '全局运行模式配置表';
COMMENT ON COLUMN runtime_mode_config.id IS '内部主键';
COMMENT ON COLUMN runtime_mode_config.uuid IS '外部唯一标识';
COMMENT ON COLUMN runtime_mode_config.config_key IS '配置键';
COMMENT ON COLUMN runtime_mode_config.default_mode IS '默认运行模式（陪跑/自动）';
COMMENT ON COLUMN runtime_mode_config.global_switch IS '全局开关状态';
COMMENT ON COLUMN runtime_mode_config.circuit_breaker_status IS '熔断状态';
COMMENT ON COLUMN runtime_mode_config.circuit_breaker_time IS '熔断时间';
COMMENT ON COLUMN runtime_mode_config.operator_id IS '操作人ID';
COMMENT ON COLUMN runtime_mode_config.operator_name IS '操作人姓名';
COMMENT ON COLUMN runtime_mode_config.config_version IS '配置版本号';
COMMENT ON COLUMN runtime_mode_config.create_by IS '创建人ID';
COMMENT ON COLUMN runtime_mode_config.update_by IS '更新人ID';
COMMENT ON COLUMN runtime_mode_config.delete_by IS '删除人ID';
COMMENT ON COLUMN runtime_mode_config.create_time IS '创建时间';
COMMENT ON COLUMN runtime_mode_config.update_time IS '更新时间';
COMMENT ON COLUMN runtime_mode_config.delete_time IS '删除时间';
COMMENT ON COLUMN runtime_mode_config.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN runtime_mode_config.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_runtime_mode_config_uuid ON runtime_mode_config (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_runtime_mode_config_config_key ON runtime_mode_config (config_key) WHERE is_deleted = 0;
CREATE INDEX IF NOT EXISTS idx_runtime_mode_config_default_mode ON runtime_mode_config (default_mode);

DROP TRIGGER IF EXISTS trigger_runtime_mode_config_update_time ON runtime_mode_config;
CREATE TRIGGER trigger_runtime_mode_config_update_time
BEFORE UPDATE ON runtime_mode_config
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-7-002: 场景授权与任务覆盖表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- scene_authorization 场景授权表 ----------
CREATE TABLE IF NOT EXISTS scene_authorization (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    scene_type VARCHAR(32) NOT NULL,
    scene_name VARCHAR(100) DEFAULT NULL,
    auto_mode_enabled SMALLINT NOT NULL DEFAULT 0 CHECK (auto_mode_enabled IN (0, 1)),
    fence_rule_set JSONB NOT NULL DEFAULT '[]'::jsonb,
    authorize_by BIGINT NOT NULL,
    authorize_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    effective_start TIMESTAMP(3) WITH TIME ZONE NOT NULL,
    effective_end TIMESTAMP(3) WITH TIME ZONE NOT NULL,
    auth_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (auth_status IN ('active','revoked','expired')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL,
    CONSTRAINT ck_scene_authorization_1 CHECK (effective_end > effective_start)
);

COMMENT ON TABLE scene_authorization IS '场景授权表';
COMMENT ON COLUMN scene_authorization.id IS '内部主键';
COMMENT ON COLUMN scene_authorization.uuid IS '外部唯一标识';
COMMENT ON COLUMN scene_authorization.scene_type IS '场景类型';
COMMENT ON COLUMN scene_authorization.scene_name IS '场景名称';
COMMENT ON COLUMN scene_authorization.auto_mode_enabled IS '是否允许自动模式';
COMMENT ON COLUMN scene_authorization.fence_rule_set IS '绑定围栏规则集';
COMMENT ON COLUMN scene_authorization.authorize_by IS '授权人ID';
COMMENT ON COLUMN scene_authorization.authorize_time IS '授权时间';
COMMENT ON COLUMN scene_authorization.effective_start IS '有效期开始';
COMMENT ON COLUMN scene_authorization.effective_end IS '有效期结束';
COMMENT ON COLUMN scene_authorization.auth_status IS '授权状态';
COMMENT ON COLUMN scene_authorization.create_by IS '创建人ID';
COMMENT ON COLUMN scene_authorization.update_by IS '更新人ID';
COMMENT ON COLUMN scene_authorization.delete_by IS '删除人ID';
COMMENT ON COLUMN scene_authorization.create_time IS '创建时间';
COMMENT ON COLUMN scene_authorization.update_time IS '更新时间';
COMMENT ON COLUMN scene_authorization.delete_time IS '删除时间';
COMMENT ON COLUMN scene_authorization.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN scene_authorization.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_scene_authorization_uuid ON scene_authorization (uuid);
CREATE INDEX IF NOT EXISTS idx_scene_authorization_scene_type ON scene_authorization (scene_type);
CREATE INDEX IF NOT EXISTS idx_scene_authorization_effective_start_effective_end ON scene_authorization (effective_start, effective_end);
CREATE INDEX IF NOT EXISTS idx_scene_authorization_auth_status ON scene_authorization (auth_status);

DROP TRIGGER IF EXISTS trigger_scene_authorization_update_time ON scene_authorization;
CREATE TRIGGER trigger_scene_authorization_update_time
BEFORE UPDATE ON scene_authorization
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- task_mode_override 任务级模式覆盖表 ----------
CREATE TABLE IF NOT EXISTS task_mode_override (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    task_id BIGINT NOT NULL,
    task_type VARCHAR(20) NOT NULL DEFAULT 'agent_task' CHECK (task_type IN ('agent_task','atomic_task')),
    origin_mode VARCHAR(20) DEFAULT NULL CHECK (origin_mode IN ('copilot','autopilot')),
    override_mode VARCHAR(20) NOT NULL CHECK (override_mode IN ('copilot','autopilot')),
    override_reason VARCHAR(500) NOT NULL,
    override_by BIGINT NOT NULL,
    override_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    effective_until TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE task_mode_override IS '任务级模式覆盖表';
COMMENT ON COLUMN task_mode_override.id IS '内部主键';
COMMENT ON COLUMN task_mode_override.uuid IS '外部唯一标识';
COMMENT ON COLUMN task_mode_override.task_id IS '任务ID';
COMMENT ON COLUMN task_mode_override.task_type IS '任务类型';
COMMENT ON COLUMN task_mode_override.origin_mode IS '原运行模式';
COMMENT ON COLUMN task_mode_override.override_mode IS '覆盖后运行模式';
COMMENT ON COLUMN task_mode_override.override_reason IS '覆盖原因';
COMMENT ON COLUMN task_mode_override.override_by IS '覆盖人ID';
COMMENT ON COLUMN task_mode_override.override_time IS '覆盖时间';
COMMENT ON COLUMN task_mode_override.effective_until IS '覆盖有效期至';
COMMENT ON COLUMN task_mode_override.create_by IS '创建人ID';
COMMENT ON COLUMN task_mode_override.update_by IS '更新人ID';
COMMENT ON COLUMN task_mode_override.delete_by IS '删除人ID';
COMMENT ON COLUMN task_mode_override.create_time IS '创建时间';
COMMENT ON COLUMN task_mode_override.update_time IS '更新时间';
COMMENT ON COLUMN task_mode_override.delete_time IS '删除时间';
COMMENT ON COLUMN task_mode_override.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN task_mode_override.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_task_mode_override_uuid ON task_mode_override (uuid);
CREATE INDEX IF NOT EXISTS idx_task_mode_override_task_id ON task_mode_override (task_id);
CREATE INDEX IF NOT EXISTS idx_task_mode_override_override_time ON task_mode_override (override_time);

DROP TRIGGER IF EXISTS trigger_task_mode_override_update_time ON task_mode_override;
CREATE TRIGGER trigger_task_mode_override_update_time
BEFORE UPDATE ON task_mode_override
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-1-001: 意图与上下文快照表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- intent_record 意图记录表 ----------
CREATE TABLE IF NOT EXISTS intent_record (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    intent_no VARCHAR(64) NOT NULL,
    raw_text TEXT NOT NULL,
    parse_status VARCHAR(20) NOT NULL DEFAULT 'parsed' CHECK (parse_status IN ('parsed','clarifying','confirmed','failed')),
    intent_type VARCHAR(32) DEFAULT NULL,
    parsed_intent VARCHAR(200) DEFAULT NULL,
    parsed_slots JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence NUMERIC(5,4) DEFAULT NULL CHECK (confidence >= 0 AND confidence <= 1),
    clarify_count INTEGER NOT NULL DEFAULT 0,
    clarify_records JSONB NOT NULL DEFAULT '[]'::jsonb,
    confirmed_intent VARCHAR(200) DEFAULT NULL,
    confirm_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE intent_record IS '意图记录表';
COMMENT ON COLUMN intent_record.id IS '内部主键';
COMMENT ON COLUMN intent_record.uuid IS '外部唯一标识';
COMMENT ON COLUMN intent_record.intent_no IS '意图编号';
COMMENT ON COLUMN intent_record.raw_text IS '原始输入文本';
COMMENT ON COLUMN intent_record.parse_status IS '解析状态';
COMMENT ON COLUMN intent_record.intent_type IS '意图类型';
COMMENT ON COLUMN intent_record.parsed_intent IS '解析结果';
COMMENT ON COLUMN intent_record.parsed_slots IS '解析槽位';
COMMENT ON COLUMN intent_record.confidence IS '解析置信度';
COMMENT ON COLUMN intent_record.clarify_count IS '澄清轮次';
COMMENT ON COLUMN intent_record.clarify_records IS '澄清记录';
COMMENT ON COLUMN intent_record.confirmed_intent IS '确认后意图';
COMMENT ON COLUMN intent_record.confirm_time IS '确认时间';
COMMENT ON COLUMN intent_record.create_by IS '创建人ID';
COMMENT ON COLUMN intent_record.update_by IS '更新人ID';
COMMENT ON COLUMN intent_record.delete_by IS '删除人ID';
COMMENT ON COLUMN intent_record.create_time IS '创建时间';
COMMENT ON COLUMN intent_record.update_time IS '更新时间';
COMMENT ON COLUMN intent_record.delete_time IS '删除时间';
COMMENT ON COLUMN intent_record.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN intent_record.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_intent_record_uuid ON intent_record (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_intent_record_intent_no ON intent_record (intent_no);
CREATE INDEX IF NOT EXISTS idx_intent_record_parse_status ON intent_record (parse_status);
CREATE INDEX IF NOT EXISTS idx_intent_record_create_time ON intent_record (create_time);

DROP TRIGGER IF EXISTS trigger_intent_record_update_time ON intent_record;
CREATE TRIGGER trigger_intent_record_update_time
BEFORE UPDATE ON intent_record
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- context_snapshot 上下文快照表 ----------
CREATE TABLE IF NOT EXISTS context_snapshot (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    intent_id BIGINT DEFAULT NULL REFERENCES intent_record(id),
    snapshot_version INTEGER NOT NULL DEFAULT 1,
    snapshot_content JSONB NOT NULL DEFAULT '{}'::jsonb,
    permission_constraint JSONB NOT NULL DEFAULT '{}'::jsonb,
    effective_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    expire_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_valid SMALLINT NOT NULL DEFAULT 1 CHECK (is_valid IN (0, 1)),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE context_snapshot IS '上下文快照表';
COMMENT ON COLUMN context_snapshot.id IS '内部主键';
COMMENT ON COLUMN context_snapshot.uuid IS '外部唯一标识';
COMMENT ON COLUMN context_snapshot.intent_id IS '意图记录ID';
COMMENT ON COLUMN context_snapshot.snapshot_version IS '快照版本号';
COMMENT ON COLUMN context_snapshot.snapshot_content IS '上下文内容';
COMMENT ON COLUMN context_snapshot.permission_constraint IS '权限约束';
COMMENT ON COLUMN context_snapshot.effective_time IS '生效时间';
COMMENT ON COLUMN context_snapshot.expire_time IS '有效期至';
COMMENT ON COLUMN context_snapshot.is_valid IS '是否有效';
COMMENT ON COLUMN context_snapshot.create_by IS '创建人ID';
COMMENT ON COLUMN context_snapshot.update_by IS '更新人ID';
COMMENT ON COLUMN context_snapshot.delete_by IS '删除人ID';
COMMENT ON COLUMN context_snapshot.create_time IS '创建时间';
COMMENT ON COLUMN context_snapshot.update_time IS '更新时间';
COMMENT ON COLUMN context_snapshot.delete_time IS '删除时间';
COMMENT ON COLUMN context_snapshot.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN context_snapshot.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_context_snapshot_uuid ON context_snapshot (uuid);
CREATE INDEX IF NOT EXISTS idx_context_snapshot_intent_id ON context_snapshot (intent_id);
CREATE INDEX IF NOT EXISTS idx_context_snapshot_expire_time ON context_snapshot (expire_time);

DROP TRIGGER IF EXISTS trigger_context_snapshot_update_time ON context_snapshot;
CREATE TRIGGER trigger_context_snapshot_update_time
BEFORE UPDATE ON context_snapshot
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-1-002: 任务路由表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- agent_task 任务路由表 ----------
CREATE TABLE IF NOT EXISTS agent_task (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    task_no VARCHAR(64) NOT NULL,
    intent_id BIGINT DEFAULT NULL REFERENCES intent_record(id),
    context_snapshot_id BIGINT DEFAULT NULL REFERENCES context_snapshot(id),
    parent_task_id BIGINT DEFAULT NULL REFERENCES agent_task(id),
    task_title VARCHAR(200) DEFAULT NULL,
    task_content TEXT DEFAULT NULL,
    t_level VARCHAR(4) NOT NULL DEFAULT 'T1' CHECK (t_level IN ('T1','T2','T3','T4')),
    execution_mode VARCHAR(20) NOT NULL DEFAULT 'copilot' CHECK (execution_mode IN ('copilot','autopilot')),
    route_agent VARCHAR(64) DEFAULT NULL,
    route_scene VARCHAR(32) DEFAULT NULL,
    task_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (task_status IN ('pending','routed','running','waiting_review','completed','failed','cancelled','timeout')),
    chain_id VARCHAR(64) DEFAULT NULL,
    assigned_by BIGINT DEFAULT NULL,
    start_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    end_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE agent_task IS '任务路由表';
COMMENT ON COLUMN agent_task.id IS '内部主键';
COMMENT ON COLUMN agent_task.uuid IS '外部唯一标识';
COMMENT ON COLUMN agent_task.task_no IS '任务编号';
COMMENT ON COLUMN agent_task.intent_id IS '意图记录ID';
COMMENT ON COLUMN agent_task.context_snapshot_id IS '上下文快照ID';
COMMENT ON COLUMN agent_task.parent_task_id IS '父任务ID';
COMMENT ON COLUMN agent_task.task_title IS '任务标题';
COMMENT ON COLUMN agent_task.task_content IS '任务内容';
COMMENT ON COLUMN agent_task.t_level IS '风险等级';
COMMENT ON COLUMN agent_task.execution_mode IS '执行模式';
COMMENT ON COLUMN agent_task.route_agent IS '路由对象（Agent）';
COMMENT ON COLUMN agent_task.route_scene IS '路由场景';
COMMENT ON COLUMN agent_task.task_status IS '任务状态';
COMMENT ON COLUMN agent_task.chain_id IS '链路ID';
COMMENT ON COLUMN agent_task.assigned_by IS '派发人ID';
COMMENT ON COLUMN agent_task.start_time IS '开始时间';
COMMENT ON COLUMN agent_task.end_time IS '结束时间';
COMMENT ON COLUMN agent_task.create_by IS '创建人ID';
COMMENT ON COLUMN agent_task.update_by IS '更新人ID';
COMMENT ON COLUMN agent_task.delete_by IS '删除人ID';
COMMENT ON COLUMN agent_task.create_time IS '创建时间';
COMMENT ON COLUMN agent_task.update_time IS '更新时间';
COMMENT ON COLUMN agent_task.delete_time IS '删除时间';
COMMENT ON COLUMN agent_task.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN agent_task.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_task_uuid ON agent_task (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_task_task_no ON agent_task (task_no);
CREATE INDEX IF NOT EXISTS idx_agent_task_task_status ON agent_task (task_status);
CREATE INDEX IF NOT EXISTS idx_agent_task_task_status_t_level ON agent_task (task_status, t_level);
CREATE INDEX IF NOT EXISTS idx_agent_task_intent_id ON agent_task (intent_id);
CREATE INDEX IF NOT EXISTS idx_agent_task_context_snapshot_id ON agent_task (context_snapshot_id);
CREATE INDEX IF NOT EXISTS idx_agent_task_chain_id ON agent_task (chain_id);
CREATE INDEX IF NOT EXISTS idx_agent_task_route_agent ON agent_task (route_agent);

DROP TRIGGER IF EXISTS trigger_agent_task_update_time ON agent_task;
CREATE TRIGGER trigger_agent_task_update_time
BEFORE UPDATE ON agent_task
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-1-003: 审核项与简报表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- review_item 审核项表 ----------
CREATE TABLE IF NOT EXISTS review_item (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    review_no VARCHAR(64) NOT NULL,
    source_agent VARCHAR(64) NOT NULL,
    task_id BIGINT DEFAULT NULL REFERENCES agent_task(id),
    deliverable_id BIGINT DEFAULT NULL,
    submit_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','done')),
    review_result VARCHAR(20) DEFAULT NULL CHECK (review_result IN ('approved','modified','rejected')),
    review_opinion VARCHAR(500) DEFAULT NULL,
    reviewer_id BIGINT DEFAULT NULL,
    review_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE review_item IS '审核项表';
COMMENT ON COLUMN review_item.id IS '内部主键';
COMMENT ON COLUMN review_item.uuid IS '外部唯一标识';
COMMENT ON COLUMN review_item.review_no IS '审核编号';
COMMENT ON COLUMN review_item.source_agent IS '来源 Agent';
COMMENT ON COLUMN review_item.task_id IS '关联任务ID';
COMMENT ON COLUMN review_item.deliverable_id IS '关联产出物ID';
COMMENT ON COLUMN review_item.submit_time IS '提交时间';
COMMENT ON COLUMN review_item.review_status IS '审核状态';
COMMENT ON COLUMN review_item.review_result IS '处理结果（通过/修改/驳回）';
COMMENT ON COLUMN review_item.review_opinion IS '审核意见';
COMMENT ON COLUMN review_item.reviewer_id IS '审核人ID';
COMMENT ON COLUMN review_item.review_time IS '审核时间';
COMMENT ON COLUMN review_item.create_by IS '创建人ID';
COMMENT ON COLUMN review_item.update_by IS '更新人ID';
COMMENT ON COLUMN review_item.delete_by IS '删除人ID';
COMMENT ON COLUMN review_item.create_time IS '创建时间';
COMMENT ON COLUMN review_item.update_time IS '更新时间';
COMMENT ON COLUMN review_item.delete_time IS '删除时间';
COMMENT ON COLUMN review_item.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN review_item.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_review_item_uuid ON review_item (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_item_review_no ON review_item (review_no);
CREATE INDEX IF NOT EXISTS idx_review_item_review_status_submit_time ON review_item (review_status, submit_time);
CREATE INDEX IF NOT EXISTS idx_review_item_source_agent ON review_item (source_agent);
CREATE INDEX IF NOT EXISTS idx_review_item_task_id ON review_item (task_id);
CREATE INDEX IF NOT EXISTS idx_review_item_deliverable_id ON review_item (deliverable_id);

DROP TRIGGER IF EXISTS trigger_review_item_update_time ON review_item;
CREATE TRIGGER trigger_review_item_update_time
BEFORE UPDATE ON review_item
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- briefing 管家简报表 ----------
CREATE TABLE IF NOT EXISTS briefing (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    briefing_no VARCHAR(64) NOT NULL,
    period_type VARCHAR(20) NOT NULL CHECK (period_type IN ('day','week','month')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    todo_count INTEGER NOT NULL DEFAULT 0,
    risk_count INTEGER NOT NULL DEFAULT 0,
    pending_acceptance_count INTEGER NOT NULL DEFAULT 0,
    circuit_breaker_count INTEGER NOT NULL DEFAULT 0,
    degrade_count INTEGER NOT NULL DEFAULT 0,
    briefing_content JSONB NOT NULL DEFAULT '{}'::jsonb,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL,
    CONSTRAINT ck_briefing_1 CHECK (period_end >= period_start)
);

COMMENT ON TABLE briefing IS '管家简报表';
COMMENT ON COLUMN briefing.id IS '内部主键';
COMMENT ON COLUMN briefing.uuid IS '外部唯一标识';
COMMENT ON COLUMN briefing.briefing_no IS '简报编号';
COMMENT ON COLUMN briefing.period_type IS '简报周期类型';
COMMENT ON COLUMN briefing.period_start IS '周期开始日期';
COMMENT ON COLUMN briefing.period_end IS '周期结束日期';
COMMENT ON COLUMN briefing.todo_count IS '待办数量';
COMMENT ON COLUMN briefing.risk_count IS '风险数量';
COMMENT ON COLUMN briefing.pending_acceptance_count IS '待验收数量';
COMMENT ON COLUMN briefing.circuit_breaker_count IS '熔断次数';
COMMENT ON COLUMN briefing.degrade_count IS '降级次数';
COMMENT ON COLUMN briefing.briefing_content IS '简报内容';
COMMENT ON COLUMN briefing.create_by IS '创建人ID';
COMMENT ON COLUMN briefing.update_by IS '更新人ID';
COMMENT ON COLUMN briefing.delete_by IS '删除人ID';
COMMENT ON COLUMN briefing.create_time IS '创建时间';
COMMENT ON COLUMN briefing.update_time IS '更新时间';
COMMENT ON COLUMN briefing.delete_time IS '删除时间';
COMMENT ON COLUMN briefing.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN briefing.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_briefing_uuid ON briefing (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_briefing_briefing_no ON briefing (briefing_no);
CREATE UNIQUE INDEX IF NOT EXISTS uq_briefing_period_type_period_start ON briefing (period_type, period_start);
CREATE INDEX IF NOT EXISTS idx_briefing_period_type_period_start_period_end ON briefing (period_type, period_start, period_end);

DROP TRIGGER IF EXISTS trigger_briefing_update_time ON briefing;
CREATE TRIGGER trigger_briefing_update_time
BEFORE UPDATE ON briefing
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-6-001: 项目与里程碑表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- project 项目表 ----------
CREATE TABLE IF NOT EXISTS project (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    project_no VARCHAR(64) NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    customer_id BIGINT DEFAULT NULL REFERENCES fact_customer(id),
    total_duration_days INTEGER DEFAULT NULL,
    sla_days INTEGER DEFAULT NULL,
    output_list JSONB NOT NULL DEFAULT '[]'::jsonb,
    default_mode VARCHAR(20) NOT NULL DEFAULT 'copilot' CHECK (default_mode IN ('copilot','autopilot')),
    final_accept_t_level VARCHAR(4) NOT NULL DEFAULT 'T3' CHECK (final_accept_t_level IN ('T1','T2','T3','T4')),
    accept_criteria TEXT DEFAULT NULL,
    accept_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (accept_status IN ('pending','accepted','rejected')),
    reject_opinion VARCHAR(500) DEFAULT NULL,
    project_status VARCHAR(20) NOT NULL DEFAULT 'planning' CHECK (project_status IN ('planning','running','paused','completed','closed')),
    plan_start_date DATE DEFAULT NULL,
    plan_end_date DATE DEFAULT NULL,
    owner_id BIGINT DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE project IS '项目表';
COMMENT ON COLUMN project.id IS '内部主键';
COMMENT ON COLUMN project.uuid IS '外部唯一标识';
COMMENT ON COLUMN project.project_no IS '项目编号';
COMMENT ON COLUMN project.project_name IS '项目名称';
COMMENT ON COLUMN project.customer_id IS '客户档案ID';
COMMENT ON COLUMN project.total_duration_days IS '总周期（天）';
COMMENT ON COLUMN project.sla_days IS 'SLA（天）';
COMMENT ON COLUMN project.output_list IS '总产出清单';
COMMENT ON COLUMN project.default_mode IS '默认运行模式';
COMMENT ON COLUMN project.final_accept_t_level IS '终验 T 等级';
COMMENT ON COLUMN project.accept_criteria IS '验收标准';
COMMENT ON COLUMN project.accept_status IS '验收状态';
COMMENT ON COLUMN project.reject_opinion IS '驳回意见';
COMMENT ON COLUMN project.project_status IS '项目状态';
COMMENT ON COLUMN project.plan_start_date IS '计划开始日期';
COMMENT ON COLUMN project.plan_end_date IS '计划结束日期';
COMMENT ON COLUMN project.owner_id IS '项目负责人ID';
COMMENT ON COLUMN project.create_by IS '创建人ID';
COMMENT ON COLUMN project.update_by IS '更新人ID';
COMMENT ON COLUMN project.delete_by IS '删除人ID';
COMMENT ON COLUMN project.create_time IS '创建时间';
COMMENT ON COLUMN project.update_time IS '更新时间';
COMMENT ON COLUMN project.delete_time IS '删除时间';
COMMENT ON COLUMN project.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN project.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_uuid ON project (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_project_no ON project (project_no);
CREATE INDEX IF NOT EXISTS idx_project_customer_id ON project (customer_id);
CREATE INDEX IF NOT EXISTS idx_project_project_status ON project (project_status);
CREATE INDEX IF NOT EXISTS idx_project_project_name ON project (project_name);

DROP TRIGGER IF EXISTS trigger_project_update_time ON project;
CREATE TRIGGER trigger_project_update_time
BEFORE UPDATE ON project
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- milestone 里程碑表 ----------
CREATE TABLE IF NOT EXISTS milestone (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id BIGINT NOT NULL REFERENCES project(id),
    milestone_no VARCHAR(64) NOT NULL,
    milestone_name VARCHAR(200) NOT NULL,
    seq_no INTEGER NOT NULL DEFAULT 1,
    plan_start_date DATE DEFAULT NULL,
    plan_end_date DATE DEFAULT NULL,
    actual_start_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    actual_end_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    accept_criteria TEXT DEFAULT NULL,
    accept_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (accept_status IN ('pending','accepted','rejected')),
    reject_opinion VARCHAR(500) DEFAULT NULL,
    aggregated_outputs JSONB NOT NULL DEFAULT '[]'::jsonb,
    milestone_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (milestone_status IN ('pending','running','completed','accepted','rejected')),
    owner_id BIGINT DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE milestone IS '里程碑表';
COMMENT ON COLUMN milestone.id IS '内部主键';
COMMENT ON COLUMN milestone.uuid IS '外部唯一标识';
COMMENT ON COLUMN milestone.project_id IS '所属项目ID';
COMMENT ON COLUMN milestone.milestone_no IS '里程碑编号';
COMMENT ON COLUMN milestone.milestone_name IS '里程碑名称';
COMMENT ON COLUMN milestone.seq_no IS '排序号';
COMMENT ON COLUMN milestone.plan_start_date IS '计划开始日期';
COMMENT ON COLUMN milestone.plan_end_date IS '计划结束日期';
COMMENT ON COLUMN milestone.actual_start_time IS '实际开始时间';
COMMENT ON COLUMN milestone.actual_end_time IS '实际结束时间';
COMMENT ON COLUMN milestone.accept_criteria IS '验收标准';
COMMENT ON COLUMN milestone.accept_status IS '验收状态';
COMMENT ON COLUMN milestone.reject_opinion IS '驳回意见';
COMMENT ON COLUMN milestone.aggregated_outputs IS '聚合产出物';
COMMENT ON COLUMN milestone.milestone_status IS '里程碑状态';
COMMENT ON COLUMN milestone.owner_id IS '负责人ID';
COMMENT ON COLUMN milestone.create_by IS '创建人ID';
COMMENT ON COLUMN milestone.update_by IS '更新人ID';
COMMENT ON COLUMN milestone.delete_by IS '删除人ID';
COMMENT ON COLUMN milestone.create_time IS '创建时间';
COMMENT ON COLUMN milestone.update_time IS '更新时间';
COMMENT ON COLUMN milestone.delete_time IS '删除时间';
COMMENT ON COLUMN milestone.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN milestone.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_milestone_uuid ON milestone (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_milestone_milestone_no ON milestone (milestone_no);
CREATE UNIQUE INDEX IF NOT EXISTS uq_milestone_project_id_seq_no ON milestone (project_id, seq_no);
CREATE INDEX IF NOT EXISTS idx_milestone_project_id ON milestone (project_id);
CREATE INDEX IF NOT EXISTS idx_milestone_project_id_seq_no ON milestone (project_id, seq_no);
CREATE INDEX IF NOT EXISTS idx_milestone_milestone_status ON milestone (milestone_status);

DROP TRIGGER IF EXISTS trigger_milestone_update_time ON milestone;
CREATE TRIGGER trigger_milestone_update_time
BEFORE UPDATE ON milestone
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-6-002: 迭代与原子任务表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- iteration 迭代表 ----------
CREATE TABLE IF NOT EXISTS iteration (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id BIGINT NOT NULL REFERENCES project(id),
    milestone_id BIGINT NOT NULL REFERENCES milestone(id),
    iteration_no VARCHAR(64) NOT NULL,
    iteration_name VARCHAR(200) DEFAULT NULL,
    iteration_goal TEXT DEFAULT NULL,
    start_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    end_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    start_briefing TEXT DEFAULT NULL,
    closing_summary TEXT DEFAULT NULL,
    roll_source_task_id BIGINT DEFAULT NULL,
    roll_forward_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    owner_id BIGINT DEFAULT NULL,
    iteration_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (iteration_status IN ('pending','running','completed','closed')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE iteration IS '迭代表';
COMMENT ON COLUMN iteration.id IS '内部主键';
COMMENT ON COLUMN iteration.uuid IS '外部唯一标识';
COMMENT ON COLUMN iteration.project_id IS '所属项目ID';
COMMENT ON COLUMN iteration.milestone_id IS '所属里程碑ID';
COMMENT ON COLUMN iteration.iteration_no IS '迭代编号';
COMMENT ON COLUMN iteration.iteration_name IS '迭代名称';
COMMENT ON COLUMN iteration.iteration_goal IS '迭代目标';
COMMENT ON COLUMN iteration.start_time IS '迭代开始时间';
COMMENT ON COLUMN iteration.end_time IS '迭代结束时间';
COMMENT ON COLUMN iteration.start_briefing IS '启动简报';
COMMENT ON COLUMN iteration.closing_summary IS '收尾小结';
COMMENT ON COLUMN iteration.roll_source_task_id IS '滚动来源任务ID';
COMMENT ON COLUMN iteration.roll_forward_items IS '滚动未完成项';
COMMENT ON COLUMN iteration.owner_id IS '责任人ID';
COMMENT ON COLUMN iteration.iteration_status IS '迭代状态';
COMMENT ON COLUMN iteration.create_by IS '创建人ID';
COMMENT ON COLUMN iteration.update_by IS '更新人ID';
COMMENT ON COLUMN iteration.delete_by IS '删除人ID';
COMMENT ON COLUMN iteration.create_time IS '创建时间';
COMMENT ON COLUMN iteration.update_time IS '更新时间';
COMMENT ON COLUMN iteration.delete_time IS '删除时间';
COMMENT ON COLUMN iteration.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN iteration.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_iteration_uuid ON iteration (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_iteration_iteration_no ON iteration (iteration_no);
CREATE INDEX IF NOT EXISTS idx_iteration_milestone_id ON iteration (milestone_id);
CREATE INDEX IF NOT EXISTS idx_iteration_project_id ON iteration (project_id);
CREATE INDEX IF NOT EXISTS idx_iteration_milestone_id_start_time ON iteration (milestone_id, start_time);
CREATE INDEX IF NOT EXISTS idx_iteration_iteration_status ON iteration (iteration_status);

DROP TRIGGER IF EXISTS trigger_iteration_update_time ON iteration;
CREATE TRIGGER trigger_iteration_update_time
BEFORE UPDATE ON iteration
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- atomic_task 原子任务表 ----------
CREATE TABLE IF NOT EXISTS atomic_task (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    iteration_id BIGINT NOT NULL REFERENCES iteration(id),
    milestone_id BIGINT NOT NULL REFERENCES milestone(id),
    project_id BIGINT NOT NULL REFERENCES project(id),
    task_no VARCHAR(64) NOT NULL,
    task_name VARCHAR(200) NOT NULL,
    task_desc TEXT DEFAULT NULL,
    seq_no INTEGER NOT NULL DEFAULT 1,
    owner_id BIGINT DEFAULT NULL,
    t_level VARCHAR(4) NOT NULL DEFAULT 'T1' CHECK (t_level IN ('T1','T2','T3','T4')),
    execution_mode VARCHAR(20) NOT NULL DEFAULT 'copilot' CHECK (execution_mode IN ('copilot','autopilot')),
    mode_source VARCHAR(20) NOT NULL DEFAULT 'inherit' CHECK (mode_source IN ('inherit','override')),
    bound_deliverable_ids BIGINT[] NOT NULL DEFAULT '{}'::bigint[],
    pre_dependency_task_ids BIGINT[] NOT NULL DEFAULT '{}'::bigint[],
    block_reason VARCHAR(500) DEFAULT NULL,
    task_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (task_status IN ('pending','ready','running','blocked','waiting_review','completed','cancelled')),
    plan_start_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    plan_end_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    actual_start_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    actual_end_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    deliverable_desc TEXT DEFAULT NULL,
    accept_criteria TEXT DEFAULT NULL,
    retry_count SMALLINT NOT NULL DEFAULT 0,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE atomic_task IS '原子任务表';
COMMENT ON COLUMN atomic_task.id IS '内部主键';
COMMENT ON COLUMN atomic_task.uuid IS '外部唯一标识';
COMMENT ON COLUMN atomic_task.iteration_id IS '所属迭代ID';
COMMENT ON COLUMN atomic_task.milestone_id IS '所属里程碑ID';
COMMENT ON COLUMN atomic_task.project_id IS '所属项目ID';
COMMENT ON COLUMN atomic_task.task_no IS '任务编号';
COMMENT ON COLUMN atomic_task.task_name IS '任务名称';
COMMENT ON COLUMN atomic_task.task_desc IS '任务描述';
COMMENT ON COLUMN atomic_task.seq_no IS '排序号';
COMMENT ON COLUMN atomic_task.owner_id IS '责任人ID';
COMMENT ON COLUMN atomic_task.t_level IS '风险等级';
COMMENT ON COLUMN atomic_task.execution_mode IS '执行模式';
COMMENT ON COLUMN atomic_task.mode_source IS '执行模式来源（继承/覆盖）';
COMMENT ON COLUMN atomic_task.bound_deliverable_ids IS '绑定产出物ID集合';
COMMENT ON COLUMN atomic_task.pre_dependency_task_ids IS '前置依赖任务ID集合';
COMMENT ON COLUMN atomic_task.block_reason IS '阻塞原因';
COMMENT ON COLUMN atomic_task.task_status IS '任务状态';
COMMENT ON COLUMN atomic_task.plan_start_time IS '计划开始时间';
COMMENT ON COLUMN atomic_task.plan_end_time IS '计划结束时间';
COMMENT ON COLUMN atomic_task.actual_start_time IS '实际开始时间';
COMMENT ON COLUMN atomic_task.actual_end_time IS '实际结束时间';
COMMENT ON COLUMN atomic_task.deliverable_desc IS '产出物说明';
COMMENT ON COLUMN atomic_task.accept_criteria IS '验收标准';
COMMENT ON COLUMN atomic_task.retry_count IS '重试次数';
COMMENT ON COLUMN atomic_task.create_by IS '创建人ID';
COMMENT ON COLUMN atomic_task.update_by IS '更新人ID';
COMMENT ON COLUMN atomic_task.delete_by IS '删除人ID';
COMMENT ON COLUMN atomic_task.create_time IS '创建时间';
COMMENT ON COLUMN atomic_task.update_time IS '更新时间';
COMMENT ON COLUMN atomic_task.delete_time IS '删除时间';
COMMENT ON COLUMN atomic_task.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN atomic_task.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_atomic_task_uuid ON atomic_task (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_atomic_task_task_no ON atomic_task (task_no);
CREATE UNIQUE INDEX IF NOT EXISTS uq_atomic_task_iteration_id_seq_no ON atomic_task (iteration_id, seq_no);
CREATE INDEX IF NOT EXISTS idx_atomic_task_iteration_id ON atomic_task (iteration_id);
CREATE INDEX IF NOT EXISTS idx_atomic_task_project_id ON atomic_task (project_id);
CREATE INDEX IF NOT EXISTS idx_atomic_task_project_id_iteration_id ON atomic_task (project_id, iteration_id);
CREATE INDEX IF NOT EXISTS idx_atomic_task_project_id_task_status ON atomic_task (project_id, task_status);
CREATE INDEX IF NOT EXISTS idx_atomic_task_task_status ON atomic_task (task_status);
CREATE INDEX IF NOT EXISTS idx_atomic_task_owner_id ON atomic_task (owner_id);

DROP TRIGGER IF EXISTS trigger_atomic_task_update_time ON atomic_task;
CREATE TRIGGER trigger_atomic_task_update_time
BEFORE UPDATE ON atomic_task
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-6-003: 任务状态变更留痕表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- task_status_history 任务状态变更留痕表 ----------
CREATE TABLE IF NOT EXISTS task_status_history (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    task_id BIGINT NOT NULL,
    task_type VARCHAR(20) NOT NULL DEFAULT 'atomic_task' CHECK (task_type IN ('atomic_task','agent_task')),
    from_status VARCHAR(20) DEFAULT NULL,
    to_status VARCHAR(20) NOT NULL,
    operator_id BIGINT DEFAULT NULL,
    operator_name VARCHAR(100) DEFAULT NULL,
    operate_source VARCHAR(32) NOT NULL DEFAULT 'system' CHECK (operate_source IN ('manual','agent','system')),
    operate_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    version_no INTEGER NOT NULL DEFAULT 1,
    change_reason VARCHAR(500) DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE task_status_history IS '任务状态变更留痕表';
COMMENT ON COLUMN task_status_history.id IS '内部主键';
COMMENT ON COLUMN task_status_history.uuid IS '外部唯一标识';
COMMENT ON COLUMN task_status_history.task_id IS '任务ID';
COMMENT ON COLUMN task_status_history.task_type IS '任务类型';
COMMENT ON COLUMN task_status_history.from_status IS '变更前状态';
COMMENT ON COLUMN task_status_history.to_status IS '变更后状态';
COMMENT ON COLUMN task_status_history.operator_id IS '操作者ID';
COMMENT ON COLUMN task_status_history.operator_name IS '操作者姓名';
COMMENT ON COLUMN task_status_history.operate_source IS '操作来源';
COMMENT ON COLUMN task_status_history.operate_time IS '操作时间';
COMMENT ON COLUMN task_status_history.version_no IS '并发版本号';
COMMENT ON COLUMN task_status_history.change_reason IS '变更原因';
COMMENT ON COLUMN task_status_history.create_by IS '创建人ID';
COMMENT ON COLUMN task_status_history.update_by IS '更新人ID';
COMMENT ON COLUMN task_status_history.delete_by IS '删除人ID';
COMMENT ON COLUMN task_status_history.create_time IS '创建时间';
COMMENT ON COLUMN task_status_history.update_time IS '更新时间';
COMMENT ON COLUMN task_status_history.delete_time IS '删除时间';
COMMENT ON COLUMN task_status_history.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN task_status_history.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_task_status_history_uuid ON task_status_history (uuid);
CREATE INDEX IF NOT EXISTS idx_task_status_history_task_id_operate_time ON task_status_history (task_id, operate_time);
CREATE INDEX IF NOT EXISTS idx_task_status_history_operate_time ON task_status_history (operate_time);
CREATE INDEX IF NOT EXISTS idx_task_status_history_to_status ON task_status_history (to_status);
CREATE INDEX IF NOT EXISTS idx_task_status_history_operate_source ON task_status_history (operate_source);

DROP TRIGGER IF EXISTS trigger_task_status_history_update_time ON task_status_history;
CREATE TRIGGER trigger_task_status_history_update_time
BEFORE UPDATE ON task_status_history
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-10-001: 产出物与版本表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- deliverable 产出物表 ----------
CREATE TABLE IF NOT EXISTS deliverable (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    deliverable_no VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    deliverable_type VARCHAR(32) NOT NULL,
    node_type VARCHAR(20) NOT NULL CHECK (node_type IN ('project','milestone','iteration','atomic_task')),
    node_id BIGINT NOT NULL,
    project_id BIGINT DEFAULT NULL REFERENCES project(id),
    latest_version_no INTEGER NOT NULL DEFAULT 1,
    deliverable_status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (deliverable_status IN ('draft','submitted','reviewing','approved','rejected','archived')),
    content TEXT DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE deliverable IS '产出物表';
COMMENT ON COLUMN deliverable.id IS '内部主键';
COMMENT ON COLUMN deliverable.uuid IS '外部唯一标识';
COMMENT ON COLUMN deliverable.deliverable_no IS '产出物编号';
COMMENT ON COLUMN deliverable.title IS '产出物标题';
COMMENT ON COLUMN deliverable.deliverable_type IS '产出物类型';
COMMENT ON COLUMN deliverable.node_type IS '所属节点类型';
COMMENT ON COLUMN deliverable.node_id IS '所属节点ID';
COMMENT ON COLUMN deliverable.project_id IS '所属项目ID';
COMMENT ON COLUMN deliverable.latest_version_no IS '最新版本号';
COMMENT ON COLUMN deliverable.deliverable_status IS '产出物状态';
COMMENT ON COLUMN deliverable.content IS '当前内容';
COMMENT ON COLUMN deliverable.create_by IS '创建人ID';
COMMENT ON COLUMN deliverable.update_by IS '更新人ID';
COMMENT ON COLUMN deliverable.delete_by IS '删除人ID';
COMMENT ON COLUMN deliverable.create_time IS '创建时间';
COMMENT ON COLUMN deliverable.update_time IS '更新时间';
COMMENT ON COLUMN deliverable.delete_time IS '删除时间';
COMMENT ON COLUMN deliverable.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN deliverable.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_deliverable_uuid ON deliverable (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_deliverable_deliverable_no ON deliverable (deliverable_no);
CREATE INDEX IF NOT EXISTS idx_deliverable_node_type_node_id ON deliverable (node_type, node_id);
CREATE INDEX IF NOT EXISTS idx_deliverable_project_id ON deliverable (project_id);
CREATE INDEX IF NOT EXISTS idx_deliverable_deliverable_status ON deliverable (deliverable_status);
CREATE INDEX IF NOT EXISTS idx_deliverable_title ON deliverable (title);

DROP TRIGGER IF EXISTS trigger_deliverable_update_time ON deliverable;
CREATE TRIGGER trigger_deliverable_update_time
BEFORE UPDATE ON deliverable
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- deliverable_version 产出物版本表 ----------
CREATE TABLE IF NOT EXISTS deliverable_version (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    deliverable_id BIGINT NOT NULL REFERENCES deliverable(id),
    version_no INTEGER NOT NULL,
    title VARCHAR(200) DEFAULT NULL,
    content TEXT DEFAULT NULL,
    version_status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (version_status IN ('draft','submitted','reviewing','approved','rejected')),
    change_summary VARCHAR(500) DEFAULT NULL,
    source_agent VARCHAR(64) DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE deliverable_version IS '产出物版本表';
COMMENT ON COLUMN deliverable_version.id IS '内部主键';
COMMENT ON COLUMN deliverable_version.uuid IS '外部唯一标识';
COMMENT ON COLUMN deliverable_version.deliverable_id IS '产出物ID';
COMMENT ON COLUMN deliverable_version.version_no IS '版本号';
COMMENT ON COLUMN deliverable_version.title IS '版本标题';
COMMENT ON COLUMN deliverable_version.content IS '版本内容';
COMMENT ON COLUMN deliverable_version.version_status IS '版本状态';
COMMENT ON COLUMN deliverable_version.change_summary IS '变更说明';
COMMENT ON COLUMN deliverable_version.source_agent IS '生成 Agent';
COMMENT ON COLUMN deliverable_version.create_by IS '创建人ID';
COMMENT ON COLUMN deliverable_version.update_by IS '更新人ID';
COMMENT ON COLUMN deliverable_version.delete_by IS '删除人ID';
COMMENT ON COLUMN deliverable_version.create_time IS '创建时间';
COMMENT ON COLUMN deliverable_version.update_time IS '更新时间';
COMMENT ON COLUMN deliverable_version.delete_time IS '删除时间';
COMMENT ON COLUMN deliverable_version.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN deliverable_version.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_deliverable_version_uuid ON deliverable_version (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_deliverable_version_deliverable_id_version_no ON deliverable_version (deliverable_id, version_no);
CREATE INDEX IF NOT EXISTS idx_deliverable_version_deliverable_id ON deliverable_version (deliverable_id);
CREATE INDEX IF NOT EXISTS idx_deliverable_version_version_status ON deliverable_version (version_status);

DROP TRIGGER IF EXISTS trigger_deliverable_version_update_time ON deliverable_version;
CREATE TRIGGER trigger_deliverable_version_update_time
BEFORE UPDATE ON deliverable_version
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-10-002: 溯源与审核记录表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- deliverable_trace 产出物溯源表 ----------
CREATE TABLE IF NOT EXISTS deliverable_trace (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    deliverable_id BIGINT NOT NULL REFERENCES deliverable(id),
    version_id BIGINT DEFAULT NULL REFERENCES deliverable_version(id),
    source_agent VARCHAR(64) NOT NULL,
    t_level VARCHAR(4) NOT NULL CHECK (t_level IN ('T1','T2','T3','T4')),
    execution_mode VARCHAR(20) NOT NULL CHECK (execution_mode IN ('copilot','autopilot')),
    citation_fragment_uuids UUID[] NOT NULL DEFAULT '{}'::uuid[],
    citation_detail JSONB NOT NULL DEFAULT '[]'::jsonb,
    reviewer_id BIGINT DEFAULT NULL,
    fence_trigger_ids BIGINT[] NOT NULL DEFAULT '{}'::bigint[],
    fence_trigger_detail JSONB NOT NULL DEFAULT '[]'::jsonb,
    trace_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE deliverable_trace IS '产出物溯源表';
COMMENT ON COLUMN deliverable_trace.id IS '内部主键';
COMMENT ON COLUMN deliverable_trace.uuid IS '外部唯一标识';
COMMENT ON COLUMN deliverable_trace.deliverable_id IS '产出物ID';
COMMENT ON COLUMN deliverable_trace.version_id IS '版本ID';
COMMENT ON COLUMN deliverable_trace.source_agent IS 'Agent 来源';
COMMENT ON COLUMN deliverable_trace.t_level IS 'T 等级';
COMMENT ON COLUMN deliverable_trace.execution_mode IS '执行模式';
COMMENT ON COLUMN deliverable_trace.citation_fragment_uuids IS '引用片段UUID集合';
COMMENT ON COLUMN deliverable_trace.citation_detail IS '引用片段明细';
COMMENT ON COLUMN deliverable_trace.reviewer_id IS '审核人ID';
COMMENT ON COLUMN deliverable_trace.fence_trigger_ids IS '围栏触发记录ID集合';
COMMENT ON COLUMN deliverable_trace.fence_trigger_detail IS '围栏触发明细';
COMMENT ON COLUMN deliverable_trace.trace_time IS '溯源生成时间';
COMMENT ON COLUMN deliverable_trace.create_by IS '创建人ID';
COMMENT ON COLUMN deliverable_trace.update_by IS '更新人ID';
COMMENT ON COLUMN deliverable_trace.delete_by IS '删除人ID';
COMMENT ON COLUMN deliverable_trace.create_time IS '创建时间';
COMMENT ON COLUMN deliverable_trace.update_time IS '更新时间';
COMMENT ON COLUMN deliverable_trace.delete_time IS '删除时间';
COMMENT ON COLUMN deliverable_trace.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN deliverable_trace.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_deliverable_trace_uuid ON deliverable_trace (uuid);
CREATE INDEX IF NOT EXISTS idx_deliverable_trace_deliverable_id ON deliverable_trace (deliverable_id);
CREATE INDEX IF NOT EXISTS idx_deliverable_trace_version_id ON deliverable_trace (version_id);
CREATE INDEX IF NOT EXISTS idx_deliverable_trace_source_agent ON deliverable_trace (source_agent);

DROP TRIGGER IF EXISTS trigger_deliverable_trace_update_time ON deliverable_trace;
CREATE TRIGGER trigger_deliverable_trace_update_time
BEFORE UPDATE ON deliverable_trace
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- deliverable_review 产出物审核记录表 ----------
CREATE TABLE IF NOT EXISTS deliverable_review (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    deliverable_id BIGINT NOT NULL REFERENCES deliverable(id),
    version_id BIGINT DEFAULT NULL REFERENCES deliverable_version(id),
    reviewer_id BIGINT NOT NULL,
    review_result VARCHAR(20) NOT NULL CHECK (review_result IN ('approved','modified','rejected')),
    review_opinion VARCHAR(500) DEFAULT NULL,
    reject_reason VARCHAR(500) DEFAULT NULL,
    review_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE deliverable_review IS '产出物审核记录表';
COMMENT ON COLUMN deliverable_review.id IS '内部主键';
COMMENT ON COLUMN deliverable_review.uuid IS '外部唯一标识';
COMMENT ON COLUMN deliverable_review.deliverable_id IS '产出物ID';
COMMENT ON COLUMN deliverable_review.version_id IS '版本ID';
COMMENT ON COLUMN deliverable_review.reviewer_id IS '审核人ID';
COMMENT ON COLUMN deliverable_review.review_result IS '审核结果';
COMMENT ON COLUMN deliverable_review.review_opinion IS '审核意见';
COMMENT ON COLUMN deliverable_review.reject_reason IS '驳回原因';
COMMENT ON COLUMN deliverable_review.review_time IS '审核时间';
COMMENT ON COLUMN deliverable_review.create_by IS '创建人ID';
COMMENT ON COLUMN deliverable_review.update_by IS '更新人ID';
COMMENT ON COLUMN deliverable_review.delete_by IS '删除人ID';
COMMENT ON COLUMN deliverable_review.create_time IS '创建时间';
COMMENT ON COLUMN deliverable_review.update_time IS '更新时间';
COMMENT ON COLUMN deliverable_review.delete_time IS '删除时间';
COMMENT ON COLUMN deliverable_review.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN deliverable_review.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_deliverable_review_uuid ON deliverable_review (uuid);
CREATE INDEX IF NOT EXISTS idx_deliverable_review_deliverable_id ON deliverable_review (deliverable_id);
CREATE INDEX IF NOT EXISTS idx_deliverable_review_review_result ON deliverable_review (review_result);
CREATE INDEX IF NOT EXISTS idx_deliverable_review_reviewer_id ON deliverable_review (reviewer_id);

DROP TRIGGER IF EXISTS trigger_deliverable_review_update_time ON deliverable_review;
CREATE TRIGGER trigger_deliverable_review_update_time
BEFORE UPDATE ON deliverable_review
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-12-001: 动作日志与链路表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- action_log 动作日志表 ----------
CREATE TABLE IF NOT EXISTS action_log (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    chain_id VARCHAR(64) DEFAULT NULL,
    task_id BIGINT DEFAULT NULL,
    task_type VARCHAR(20) DEFAULT NULL CHECK (task_type IN ('agent_task','atomic_task')),
    agent_name VARCHAR(64) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    action_object VARCHAR(200) DEFAULT NULL,
    t_level VARCHAR(4) DEFAULT NULL CHECK (t_level IN ('T1','T2','T3','T4')),
    execution_mode VARCHAR(20) DEFAULT NULL CHECK (execution_mode IN ('copilot','autopilot')),
    action_result VARCHAR(20) NOT NULL CHECK (action_result IN ('success','failed','blocked','degraded')),
    duration_ms INTEGER DEFAULT NULL,
    action_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE action_log IS '动作日志表';
COMMENT ON COLUMN action_log.id IS '内部主键';
COMMENT ON COLUMN action_log.uuid IS '外部唯一标识';
COMMENT ON COLUMN action_log.chain_id IS '链路ID';
COMMENT ON COLUMN action_log.task_id IS '任务ID';
COMMENT ON COLUMN action_log.task_type IS '任务类型';
COMMENT ON COLUMN action_log.agent_name IS 'Agent 名称';
COMMENT ON COLUMN action_log.action_type IS '动作类型';
COMMENT ON COLUMN action_log.action_object IS '动作对象';
COMMENT ON COLUMN action_log.t_level IS 'T 等级';
COMMENT ON COLUMN action_log.execution_mode IS '执行模式';
COMMENT ON COLUMN action_log.action_result IS '动作结果';
COMMENT ON COLUMN action_log.duration_ms IS '耗时（毫秒）';
COMMENT ON COLUMN action_log.action_time IS '动作时间';
COMMENT ON COLUMN action_log.detail IS '动作明细';
COMMENT ON COLUMN action_log.create_by IS '创建人ID';
COMMENT ON COLUMN action_log.update_by IS '更新人ID';
COMMENT ON COLUMN action_log.delete_by IS '删除人ID';
COMMENT ON COLUMN action_log.create_time IS '创建时间';
COMMENT ON COLUMN action_log.update_time IS '更新时间';
COMMENT ON COLUMN action_log.delete_time IS '删除时间';
COMMENT ON COLUMN action_log.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN action_log.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_action_log_uuid ON action_log (uuid);
CREATE INDEX IF NOT EXISTS idx_action_log_chain_id ON action_log (chain_id);
CREATE INDEX IF NOT EXISTS idx_action_log_chain_id_action_time ON action_log (chain_id, action_time);
CREATE INDEX IF NOT EXISTS idx_action_log_task_id ON action_log (task_id);
CREATE INDEX IF NOT EXISTS idx_action_log_action_time ON action_log (action_time);
CREATE INDEX IF NOT EXISTS idx_action_log_agent_name ON action_log (agent_name);

DROP TRIGGER IF EXISTS trigger_action_log_update_time ON action_log;
CREATE TRIGGER trigger_action_log_update_time
BEFORE UPDATE ON action_log
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-12-002: 简报与超时检测表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- log_briefing 日志简报表 ----------
CREATE TABLE IF NOT EXISTS log_briefing (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    briefing_no VARCHAR(64) NOT NULL,
    period_type VARCHAR(20) NOT NULL CHECK (period_type IN ('day','week','month')),
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    todo_count INTEGER NOT NULL DEFAULT 0,
    risk_count INTEGER NOT NULL DEFAULT 0,
    pending_acceptance_count INTEGER NOT NULL DEFAULT 0,
    circuit_breaker_count INTEGER NOT NULL DEFAULT 0,
    degrade_count INTEGER NOT NULL DEFAULT 0,
    briefing_content JSONB NOT NULL DEFAULT '{}'::jsonb,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL,
    CONSTRAINT ck_log_briefing_1 CHECK (period_end >= period_start)
);

COMMENT ON TABLE log_briefing IS '日志简报表';
COMMENT ON COLUMN log_briefing.id IS '内部主键';
COMMENT ON COLUMN log_briefing.uuid IS '外部唯一标识';
COMMENT ON COLUMN log_briefing.briefing_no IS '简报编号';
COMMENT ON COLUMN log_briefing.period_type IS '简报周期类型';
COMMENT ON COLUMN log_briefing.period_start IS '周期开始日期';
COMMENT ON COLUMN log_briefing.period_end IS '周期结束日期';
COMMENT ON COLUMN log_briefing.todo_count IS '待办数量';
COMMENT ON COLUMN log_briefing.risk_count IS '风险数量';
COMMENT ON COLUMN log_briefing.pending_acceptance_count IS '待验收数量';
COMMENT ON COLUMN log_briefing.circuit_breaker_count IS '熔断次数';
COMMENT ON COLUMN log_briefing.degrade_count IS '降级次数';
COMMENT ON COLUMN log_briefing.briefing_content IS '简报内容';
COMMENT ON COLUMN log_briefing.create_by IS '创建人ID';
COMMENT ON COLUMN log_briefing.update_by IS '更新人ID';
COMMENT ON COLUMN log_briefing.delete_by IS '删除人ID';
COMMENT ON COLUMN log_briefing.create_time IS '创建时间';
COMMENT ON COLUMN log_briefing.update_time IS '更新时间';
COMMENT ON COLUMN log_briefing.delete_time IS '删除时间';
COMMENT ON COLUMN log_briefing.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN log_briefing.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_log_briefing_uuid ON log_briefing (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_log_briefing_briefing_no ON log_briefing (briefing_no);
CREATE UNIQUE INDEX IF NOT EXISTS uq_log_briefing_period_type_period_start ON log_briefing (period_type, period_start);
CREATE INDEX IF NOT EXISTS idx_log_briefing_period_type_period_start ON log_briefing (period_type, period_start);

DROP TRIGGER IF EXISTS trigger_log_briefing_update_time ON log_briefing;
CREATE TRIGGER trigger_log_briefing_update_time
BEFORE UPDATE ON log_briefing
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- timeout_record 超时检测记录表 ----------
CREATE TABLE IF NOT EXISTS timeout_record (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    node_type VARCHAR(20) NOT NULL CHECK (node_type IN ('project','milestone','iteration','atomic_task','agent_task')),
    node_id BIGINT NOT NULL,
    node_name VARCHAR(200) DEFAULT NULL,
    task_id BIGINT DEFAULT NULL,
    owner_id BIGINT DEFAULT NULL,
    plan_end_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    detect_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    timeout_minutes INTEGER NOT NULL DEFAULT 0,
    timeout_status VARCHAR(20) NOT NULL DEFAULT 'detected' CHECK (timeout_status IN ('detected','notified','handled','closed')),
    handle_desc VARCHAR(500) DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE timeout_record IS '超时检测记录表';
COMMENT ON COLUMN timeout_record.id IS '内部主键';
COMMENT ON COLUMN timeout_record.uuid IS '外部唯一标识';
COMMENT ON COLUMN timeout_record.node_type IS '超时节点类型';
COMMENT ON COLUMN timeout_record.node_id IS '超时节点ID';
COMMENT ON COLUMN timeout_record.node_name IS '节点名称';
COMMENT ON COLUMN timeout_record.task_id IS '关联任务ID';
COMMENT ON COLUMN timeout_record.owner_id IS '责任人ID';
COMMENT ON COLUMN timeout_record.plan_end_time IS '计划结束时间';
COMMENT ON COLUMN timeout_record.detect_time IS '检测时间';
COMMENT ON COLUMN timeout_record.timeout_minutes IS '超时时长（分钟）';
COMMENT ON COLUMN timeout_record.timeout_status IS '处理状态';
COMMENT ON COLUMN timeout_record.handle_desc IS '处理说明';
COMMENT ON COLUMN timeout_record.create_by IS '创建人ID';
COMMENT ON COLUMN timeout_record.update_by IS '更新人ID';
COMMENT ON COLUMN timeout_record.delete_by IS '删除人ID';
COMMENT ON COLUMN timeout_record.create_time IS '创建时间';
COMMENT ON COLUMN timeout_record.update_time IS '更新时间';
COMMENT ON COLUMN timeout_record.delete_time IS '删除时间';
COMMENT ON COLUMN timeout_record.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN timeout_record.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_timeout_record_uuid ON timeout_record (uuid);
CREATE INDEX IF NOT EXISTS idx_timeout_record_node_type_node_id ON timeout_record (node_type, node_id);
CREATE INDEX IF NOT EXISTS idx_timeout_record_owner_id ON timeout_record (owner_id);
CREATE INDEX IF NOT EXISTS idx_timeout_record_detect_time ON timeout_record (detect_time);
CREATE INDEX IF NOT EXISTS idx_timeout_record_timeout_status ON timeout_record (timeout_status);

DROP TRIGGER IF EXISTS trigger_timeout_record_update_time ON timeout_record;
CREATE TRIGGER trigger_timeout_record_update_time
BEFORE UPDATE ON timeout_record
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-3-001: 规划与规划节点表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- project_plan 项目规划表 ----------
CREATE TABLE IF NOT EXISTS project_plan (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    plan_no VARCHAR(64) NOT NULL,
    project_id BIGINT DEFAULT NULL REFERENCES project(id),
    project_name VARCHAR(200) NOT NULL,
    total_duration_days INTEGER DEFAULT NULL,
    plan_status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (plan_status IN ('draft','reviewing','approved','rejected','archived')),
    current_version_no INTEGER NOT NULL DEFAULT 1,
    plan_content JSONB NOT NULL DEFAULT '{}'::jsonb,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE project_plan IS '项目规划表';
COMMENT ON COLUMN project_plan.id IS '内部主键';
COMMENT ON COLUMN project_plan.uuid IS '外部唯一标识';
COMMENT ON COLUMN project_plan.plan_no IS '规划编号';
COMMENT ON COLUMN project_plan.project_id IS '所属项目ID';
COMMENT ON COLUMN project_plan.project_name IS '项目名称';
COMMENT ON COLUMN project_plan.total_duration_days IS '总周期（天）';
COMMENT ON COLUMN project_plan.plan_status IS '规划状态';
COMMENT ON COLUMN project_plan.current_version_no IS '当前版本号';
COMMENT ON COLUMN project_plan.plan_content IS '规划内容';
COMMENT ON COLUMN project_plan.create_by IS '创建人ID';
COMMENT ON COLUMN project_plan.update_by IS '更新人ID';
COMMENT ON COLUMN project_plan.delete_by IS '删除人ID';
COMMENT ON COLUMN project_plan.create_time IS '创建时间';
COMMENT ON COLUMN project_plan.update_time IS '更新时间';
COMMENT ON COLUMN project_plan.delete_time IS '删除时间';
COMMENT ON COLUMN project_plan.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN project_plan.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_project_plan_uuid ON project_plan (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_project_plan_plan_no ON project_plan (plan_no);
CREATE INDEX IF NOT EXISTS idx_project_plan_project_id ON project_plan (project_id);
CREATE INDEX IF NOT EXISTS idx_project_plan_plan_status ON project_plan (plan_status);

DROP TRIGGER IF EXISTS trigger_project_plan_update_time ON project_plan;
CREATE TRIGGER trigger_project_plan_update_time
BEFORE UPDATE ON project_plan
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- plan_node 规划节点表 ----------
CREATE TABLE IF NOT EXISTS plan_node (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    plan_id BIGINT NOT NULL REFERENCES project_plan(id),
    parent_id BIGINT DEFAULT NULL REFERENCES plan_node(id),
    node_type VARCHAR(20) NOT NULL CHECK (node_type IN ('project','milestone','iteration','atomic_task')),
    node_level SMALLINT NOT NULL CHECK (node_level BETWEEN 1 AND 4),
    node_name VARCHAR(200) NOT NULL,
    seq_no INTEGER NOT NULL DEFAULT 1,
    plan_start_date DATE DEFAULT NULL,
    plan_end_date DATE DEFAULT NULL,
    estimate_hours NUMERIC(6,1) DEFAULT NULL,
    output_desc TEXT DEFAULT NULL,
    accept_criteria TEXT DEFAULT NULL,
    citation_fragment_uuids UUID[] NOT NULL DEFAULT '{}'::uuid[],
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE plan_node IS '规划节点表';
COMMENT ON COLUMN plan_node.id IS '内部主键';
COMMENT ON COLUMN plan_node.uuid IS '外部唯一标识';
COMMENT ON COLUMN plan_node.plan_id IS '所属规划ID';
COMMENT ON COLUMN plan_node.parent_id IS '父节点ID';
COMMENT ON COLUMN plan_node.node_type IS '节点类型';
COMMENT ON COLUMN plan_node.node_level IS '节点层级（1-4）';
COMMENT ON COLUMN plan_node.node_name IS '节点名称';
COMMENT ON COLUMN plan_node.seq_no IS '排序号';
COMMENT ON COLUMN plan_node.plan_start_date IS '计划开始日期';
COMMENT ON COLUMN plan_node.plan_end_date IS '计划结束日期';
COMMENT ON COLUMN plan_node.estimate_hours IS '预估工时';
COMMENT ON COLUMN plan_node.output_desc IS '产出物';
COMMENT ON COLUMN plan_node.accept_criteria IS '验收标准';
COMMENT ON COLUMN plan_node.citation_fragment_uuids IS '引用片段UUID集合';
COMMENT ON COLUMN plan_node.create_by IS '创建人ID';
COMMENT ON COLUMN plan_node.update_by IS '更新人ID';
COMMENT ON COLUMN plan_node.delete_by IS '删除人ID';
COMMENT ON COLUMN plan_node.create_time IS '创建时间';
COMMENT ON COLUMN plan_node.update_time IS '更新时间';
COMMENT ON COLUMN plan_node.delete_time IS '删除时间';
COMMENT ON COLUMN plan_node.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN plan_node.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_plan_node_uuid ON plan_node (uuid);
CREATE INDEX IF NOT EXISTS idx_plan_node_plan_id ON plan_node (plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_node_parent_id ON plan_node (parent_id);
CREATE INDEX IF NOT EXISTS idx_plan_node_plan_id_node_level_seq_no ON plan_node (plan_id, node_level, seq_no);
CREATE INDEX IF NOT EXISTS idx_plan_node_plan_id_node_type ON plan_node (plan_id, node_type);

DROP TRIGGER IF EXISTS trigger_plan_node_update_time ON plan_node;
CREATE TRIGGER trigger_plan_node_update_time
BEFORE UPDATE ON plan_node
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-3-002: 规划版本与进度摘要表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- plan_version 规划版本表 ----------
CREATE TABLE IF NOT EXISTS plan_version (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    plan_id BIGINT NOT NULL REFERENCES project_plan(id),
    version_no INTEGER NOT NULL,
    version_content JSONB NOT NULL DEFAULT '{}'::jsonb,
    change_reason VARCHAR(500) DEFAULT NULL,
    review_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','approved','rejected')),
    review_opinion VARCHAR(500) DEFAULT NULL,
    reviewer_id BIGINT DEFAULT NULL,
    review_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE plan_version IS '规划版本表';
COMMENT ON COLUMN plan_version.id IS '内部主键';
COMMENT ON COLUMN plan_version.uuid IS '外部唯一标识';
COMMENT ON COLUMN plan_version.plan_id IS '规划ID';
COMMENT ON COLUMN plan_version.version_no IS '版本号';
COMMENT ON COLUMN plan_version.version_content IS '版本内容';
COMMENT ON COLUMN plan_version.change_reason IS '变更原因';
COMMENT ON COLUMN plan_version.review_status IS '审核状态';
COMMENT ON COLUMN plan_version.review_opinion IS '审核意见';
COMMENT ON COLUMN plan_version.reviewer_id IS '审核人ID';
COMMENT ON COLUMN plan_version.review_time IS '审核时间';
COMMENT ON COLUMN plan_version.create_by IS '创建人ID';
COMMENT ON COLUMN plan_version.update_by IS '更新人ID';
COMMENT ON COLUMN plan_version.delete_by IS '删除人ID';
COMMENT ON COLUMN plan_version.create_time IS '创建时间';
COMMENT ON COLUMN plan_version.update_time IS '更新时间';
COMMENT ON COLUMN plan_version.delete_time IS '删除时间';
COMMENT ON COLUMN plan_version.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN plan_version.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_plan_version_uuid ON plan_version (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_plan_version_plan_id_version_no ON plan_version (plan_id, version_no);
CREATE INDEX IF NOT EXISTS idx_plan_version_plan_id ON plan_version (plan_id);
CREATE INDEX IF NOT EXISTS idx_plan_version_review_status ON plan_version (review_status);

DROP TRIGGER IF EXISTS trigger_plan_version_update_time ON plan_version;
CREATE TRIGGER trigger_plan_version_update_time
BEFORE UPDATE ON plan_version
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- progress_summary 进度摘要表 ----------
CREATE TABLE IF NOT EXISTS progress_summary (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    project_id BIGINT NOT NULL REFERENCES project(id),
    plan_id BIGINT DEFAULT NULL REFERENCES project_plan(id),
    summary_date DATE NOT NULL,
    progress_percent NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (progress_percent >= 0 AND progress_percent <= 100),
    total_task_count INTEGER NOT NULL DEFAULT 0,
    completed_task_count INTEGER NOT NULL DEFAULT 0,
    risk_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    block_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    pending_acceptance_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE progress_summary IS '进度摘要表';
COMMENT ON COLUMN progress_summary.id IS '内部主键';
COMMENT ON COLUMN progress_summary.uuid IS '外部唯一标识';
COMMENT ON COLUMN progress_summary.project_id IS '项目ID';
COMMENT ON COLUMN progress_summary.plan_id IS '规划ID';
COMMENT ON COLUMN progress_summary.summary_date IS '摘要日期';
COMMENT ON COLUMN progress_summary.progress_percent IS '进度百分比';
COMMENT ON COLUMN progress_summary.total_task_count IS '任务总数';
COMMENT ON COLUMN progress_summary.completed_task_count IS '已完成任务数';
COMMENT ON COLUMN progress_summary.risk_items IS '风险项';
COMMENT ON COLUMN progress_summary.block_items IS '阻塞项';
COMMENT ON COLUMN progress_summary.pending_acceptance_items IS '待验收项';
COMMENT ON COLUMN progress_summary.create_by IS '创建人ID';
COMMENT ON COLUMN progress_summary.update_by IS '更新人ID';
COMMENT ON COLUMN progress_summary.delete_by IS '删除人ID';
COMMENT ON COLUMN progress_summary.create_time IS '创建时间';
COMMENT ON COLUMN progress_summary.update_time IS '更新时间';
COMMENT ON COLUMN progress_summary.delete_time IS '删除时间';
COMMENT ON COLUMN progress_summary.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN progress_summary.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_progress_summary_uuid ON progress_summary (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_progress_summary_project_id_summary_date ON progress_summary (project_id, summary_date);
CREATE INDEX IF NOT EXISTS idx_progress_summary_project_id ON progress_summary (project_id);
CREATE INDEX IF NOT EXISTS idx_progress_summary_summary_date ON progress_summary (summary_date);

DROP TRIGGER IF EXISTS trigger_progress_summary_update_time ON progress_summary;
CREATE TRIGGER trigger_progress_summary_update_time
BEFORE UPDATE ON progress_summary
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-2-001: 线索与客户档案表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- lead_record 线索记录表 ----------
CREATE TABLE IF NOT EXISTS lead_record (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    lead_no VARCHAR(64) NOT NULL,
    source_channel VARCHAR(32) DEFAULT NULL,
    contact_name VARCHAR(100) DEFAULT NULL,
    company_name VARCHAR(200) DEFAULT NULL,
    phone VARCHAR(50) DEFAULT NULL,
    email VARCHAR(150) DEFAULT NULL,
    wechat VARCHAR(100) DEFAULT NULL,
    demand_summary TEXT DEFAULT NULL,
    current_stage VARCHAR(32) NOT NULL DEFAULT 'new' CHECK (current_stage IN ('new','contacted','confirmed','quoted','won','lost')),
    missing_fields VARCHAR(500) DEFAULT NULL,
    customer_profile_id BIGINT DEFAULT NULL,
    owner_id BIGINT DEFAULT NULL,
    lead_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (lead_status IN ('active','converted','invalid')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE lead_record IS '线索记录表';
COMMENT ON COLUMN lead_record.id IS '内部主键';
COMMENT ON COLUMN lead_record.uuid IS '外部唯一标识';
COMMENT ON COLUMN lead_record.lead_no IS '线索编号';
COMMENT ON COLUMN lead_record.source_channel IS '来源渠道';
COMMENT ON COLUMN lead_record.contact_name IS '联系人姓名';
COMMENT ON COLUMN lead_record.company_name IS '公司名称';
COMMENT ON COLUMN lead_record.phone IS '联系电话';
COMMENT ON COLUMN lead_record.email IS '联系邮箱';
COMMENT ON COLUMN lead_record.wechat IS '微信';
COMMENT ON COLUMN lead_record.demand_summary IS '需求摘要';
COMMENT ON COLUMN lead_record.current_stage IS '当前阶段';
COMMENT ON COLUMN lead_record.missing_fields IS '缺失字段标记（待补）';
COMMENT ON COLUMN lead_record.customer_profile_id IS '关联客户档案ID';
COMMENT ON COLUMN lead_record.owner_id IS '负责人ID';
COMMENT ON COLUMN lead_record.lead_status IS '线索状态';
COMMENT ON COLUMN lead_record.create_by IS '创建人ID';
COMMENT ON COLUMN lead_record.update_by IS '更新人ID';
COMMENT ON COLUMN lead_record.delete_by IS '删除人ID';
COMMENT ON COLUMN lead_record.create_time IS '创建时间';
COMMENT ON COLUMN lead_record.update_time IS '更新时间';
COMMENT ON COLUMN lead_record.delete_time IS '删除时间';
COMMENT ON COLUMN lead_record.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN lead_record.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_lead_record_uuid ON lead_record (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_lead_record_lead_no ON lead_record (lead_no);
CREATE INDEX IF NOT EXISTS idx_lead_record_current_stage ON lead_record (current_stage);
CREATE INDEX IF NOT EXISTS idx_lead_record_contact_name ON lead_record (contact_name);
CREATE INDEX IF NOT EXISTS idx_lead_record_phone ON lead_record (phone);
CREATE INDEX IF NOT EXISTS idx_lead_record_source_channel ON lead_record (source_channel);

DROP TRIGGER IF EXISTS trigger_lead_record_update_time ON lead_record;
CREATE TRIGGER trigger_lead_record_update_time
BEFORE UPDATE ON lead_record
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- customer_profile 客户档案表 ----------
CREATE TABLE IF NOT EXISTS customer_profile (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    lead_id BIGINT DEFAULT NULL REFERENCES lead_record(id),
    customer_no VARCHAR(64) NOT NULL,
    customer_name VARCHAR(200) NOT NULL,
    company_name VARCHAR(200) DEFAULT NULL,
    contact_name VARCHAR(100) DEFAULT NULL,
    phone VARCHAR(50) DEFAULT NULL,
    email VARCHAR(150) DEFAULT NULL,
    tier_tag VARCHAR(32) DEFAULT NULL,
    current_stage VARCHAR(32) DEFAULT NULL,
    interaction_summary TEXT DEFAULT NULL,
    last_interaction_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    profile_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (profile_status IN ('active','archived')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE customer_profile IS '客户档案表';
COMMENT ON COLUMN customer_profile.id IS '内部主键';
COMMENT ON COLUMN customer_profile.uuid IS '外部唯一标识';
COMMENT ON COLUMN customer_profile.lead_id IS '来源线索ID';
COMMENT ON COLUMN customer_profile.customer_no IS '客户编号';
COMMENT ON COLUMN customer_profile.customer_name IS '客户名称';
COMMENT ON COLUMN customer_profile.company_name IS '公司名称';
COMMENT ON COLUMN customer_profile.contact_name IS '联系人';
COMMENT ON COLUMN customer_profile.phone IS '联系电话';
COMMENT ON COLUMN customer_profile.email IS '联系邮箱';
COMMENT ON COLUMN customer_profile.tier_tag IS '分层标签';
COMMENT ON COLUMN customer_profile.current_stage IS '当前阶段';
COMMENT ON COLUMN customer_profile.interaction_summary IS '交互摘要';
COMMENT ON COLUMN customer_profile.last_interaction_time IS '最近交互时间';
COMMENT ON COLUMN customer_profile.profile_status IS '档案状态';
COMMENT ON COLUMN customer_profile.create_by IS '创建人ID';
COMMENT ON COLUMN customer_profile.update_by IS '更新人ID';
COMMENT ON COLUMN customer_profile.delete_by IS '删除人ID';
COMMENT ON COLUMN customer_profile.create_time IS '创建时间';
COMMENT ON COLUMN customer_profile.update_time IS '更新时间';
COMMENT ON COLUMN customer_profile.delete_time IS '删除时间';
COMMENT ON COLUMN customer_profile.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN customer_profile.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_profile_uuid ON customer_profile (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_customer_profile_customer_no ON customer_profile (customer_no);
CREATE INDEX IF NOT EXISTS idx_customer_profile_lead_id ON customer_profile (lead_id);
CREATE INDEX IF NOT EXISTS idx_customer_profile_customer_name ON customer_profile (customer_name);
CREATE INDEX IF NOT EXISTS idx_customer_profile_tier_tag ON customer_profile (tier_tag);
CREATE INDEX IF NOT EXISTS idx_customer_profile_phone ON customer_profile (phone);

DROP TRIGGER IF EXISTS trigger_customer_profile_update_time ON customer_profile;
CREATE TRIGGER trigger_customer_profile_update_time
BEFORE UPDATE ON customer_profile
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-2-002: 跟进 SOP 与 FAQ 草稿表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- followup_sop 跟进 SOP 表 ----------
CREATE TABLE IF NOT EXISTS followup_sop (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    sop_no VARCHAR(64) NOT NULL,
    sop_name VARCHAR(200) NOT NULL,
    customer_stage VARCHAR(32) NOT NULL,
    suggested_action TEXT NOT NULL,
    action_limit_hours INTEGER DEFAULT NULL,
    sort_no INTEGER NOT NULL DEFAULT 1,
    content_template TEXT DEFAULT NULL,
    sop_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (sop_status IN ('active','disabled')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE followup_sop IS '跟进 SOP 表';
COMMENT ON COLUMN followup_sop.id IS '内部主键';
COMMENT ON COLUMN followup_sop.uuid IS '外部唯一标识';
COMMENT ON COLUMN followup_sop.sop_no IS 'SOP 编号';
COMMENT ON COLUMN followup_sop.sop_name IS 'SOP 名称';
COMMENT ON COLUMN followup_sop.customer_stage IS '适用客户阶段';
COMMENT ON COLUMN followup_sop.suggested_action IS '建议动作';
COMMENT ON COLUMN followup_sop.action_limit_hours IS '动作时限（小时）';
COMMENT ON COLUMN followup_sop.sort_no IS '排序号';
COMMENT ON COLUMN followup_sop.content_template IS '话术模板';
COMMENT ON COLUMN followup_sop.sop_status IS 'SOP 状态';
COMMENT ON COLUMN followup_sop.create_by IS '创建人ID';
COMMENT ON COLUMN followup_sop.update_by IS '更新人ID';
COMMENT ON COLUMN followup_sop.delete_by IS '删除人ID';
COMMENT ON COLUMN followup_sop.create_time IS '创建时间';
COMMENT ON COLUMN followup_sop.update_time IS '更新时间';
COMMENT ON COLUMN followup_sop.delete_time IS '删除时间';
COMMENT ON COLUMN followup_sop.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN followup_sop.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_followup_sop_uuid ON followup_sop (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_followup_sop_sop_no ON followup_sop (sop_no);
CREATE INDEX IF NOT EXISTS idx_followup_sop_customer_stage ON followup_sop (customer_stage);
CREATE INDEX IF NOT EXISTS idx_followup_sop_sop_status ON followup_sop (sop_status);

DROP TRIGGER IF EXISTS trigger_followup_sop_update_time ON followup_sop;
CREATE TRIGGER trigger_followup_sop_update_time
BEFORE UPDATE ON followup_sop
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- faq_draft FAQ 草稿表 ----------
CREATE TABLE IF NOT EXISTS faq_draft (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    lead_id BIGINT DEFAULT NULL REFERENCES lead_record(id),
    customer_profile_id BIGINT DEFAULT NULL,
    question TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    citation_fragment_uuids UUID[] NOT NULL DEFAULT '{}'::uuid[],
    citation_detail JSONB NOT NULL DEFAULT '[]'::jsonb,
    draft_status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (draft_status IN ('draft','reviewing','approved','rejected')),
    reviewer_id BIGINT DEFAULT NULL,
    review_opinion VARCHAR(500) DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL,
    CONSTRAINT ck_faq_draft_1 CHECK (cardinality(citation_fragment_uuids) > 0)
);

COMMENT ON TABLE faq_draft IS 'FAQ 草稿表';
COMMENT ON COLUMN faq_draft.id IS '内部主键';
COMMENT ON COLUMN faq_draft.uuid IS '外部唯一标识';
COMMENT ON COLUMN faq_draft.lead_id IS '关联线索ID';
COMMENT ON COLUMN faq_draft.customer_profile_id IS '关联客户档案ID';
COMMENT ON COLUMN faq_draft.question IS '客户问题';
COMMENT ON COLUMN faq_draft.answer_text IS '回复文本';
COMMENT ON COLUMN faq_draft.citation_fragment_uuids IS '引用片段UUID集合';
COMMENT ON COLUMN faq_draft.citation_detail IS '引用片段明细';
COMMENT ON COLUMN faq_draft.draft_status IS '草稿状态';
COMMENT ON COLUMN faq_draft.reviewer_id IS '审核人ID';
COMMENT ON COLUMN faq_draft.review_opinion IS '审核意见';
COMMENT ON COLUMN faq_draft.create_by IS '创建人ID';
COMMENT ON COLUMN faq_draft.update_by IS '更新人ID';
COMMENT ON COLUMN faq_draft.delete_by IS '删除人ID';
COMMENT ON COLUMN faq_draft.create_time IS '创建时间';
COMMENT ON COLUMN faq_draft.update_time IS '更新时间';
COMMENT ON COLUMN faq_draft.delete_time IS '删除时间';
COMMENT ON COLUMN faq_draft.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN faq_draft.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_faq_draft_uuid ON faq_draft (uuid);
CREATE INDEX IF NOT EXISTS idx_faq_draft_lead_id ON faq_draft (lead_id);
CREATE INDEX IF NOT EXISTS idx_faq_draft_customer_profile_id ON faq_draft (customer_profile_id);
CREATE INDEX IF NOT EXISTS idx_faq_draft_draft_status ON faq_draft (draft_status);

DROP TRIGGER IF EXISTS trigger_faq_draft_update_time ON faq_draft;
CREATE TRIGGER trigger_faq_draft_update_time
BEFORE UPDATE ON faq_draft
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-4-001: 选题与稿件表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- content_topic 内容选题表 ----------
CREATE TABLE IF NOT EXISTS content_topic (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    topic_no VARCHAR(64) NOT NULL,
    topic_title VARCHAR(200) NOT NULL,
    topic_angle TEXT DEFAULT NULL,
    citation_fragment_uuids UUID[] NOT NULL DEFAULT '{}'::uuid[],
    citation_detail JSONB NOT NULL DEFAULT '[]'::jsonb,
    target_platform VARCHAR(32) DEFAULT NULL,
    priority_level SMALLINT NOT NULL DEFAULT 3 CHECK (priority_level BETWEEN 1 AND 5),
    owner_id BIGINT DEFAULT NULL,
    topic_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (topic_status IN ('pending','selected','writing','published','rejected')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE content_topic IS '内容选题表';
COMMENT ON COLUMN content_topic.id IS '内部主键';
COMMENT ON COLUMN content_topic.uuid IS '外部唯一标识';
COMMENT ON COLUMN content_topic.topic_no IS '选题编号';
COMMENT ON COLUMN content_topic.topic_title IS '选题标题';
COMMENT ON COLUMN content_topic.topic_angle IS '选题角度';
COMMENT ON COLUMN content_topic.citation_fragment_uuids IS '依据片段UUID集合';
COMMENT ON COLUMN content_topic.citation_detail IS '依据片段明细';
COMMENT ON COLUMN content_topic.target_platform IS '目标平台';
COMMENT ON COLUMN content_topic.priority_level IS '优先级';
COMMENT ON COLUMN content_topic.owner_id IS '负责人ID';
COMMENT ON COLUMN content_topic.topic_status IS '选题状态';
COMMENT ON COLUMN content_topic.create_by IS '创建人ID';
COMMENT ON COLUMN content_topic.update_by IS '更新人ID';
COMMENT ON COLUMN content_topic.delete_by IS '删除人ID';
COMMENT ON COLUMN content_topic.create_time IS '创建时间';
COMMENT ON COLUMN content_topic.update_time IS '更新时间';
COMMENT ON COLUMN content_topic.delete_time IS '删除时间';
COMMENT ON COLUMN content_topic.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN content_topic.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_content_topic_uuid ON content_topic (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_topic_topic_no ON content_topic (topic_no);
CREATE INDEX IF NOT EXISTS idx_content_topic_topic_status ON content_topic (topic_status);
CREATE INDEX IF NOT EXISTS idx_content_topic_target_platform ON content_topic (target_platform);
CREATE INDEX IF NOT EXISTS idx_content_topic_topic_title ON content_topic (topic_title);

DROP TRIGGER IF EXISTS trigger_content_topic_update_time ON content_topic;
CREATE TRIGGER trigger_content_topic_update_time
BEFORE UPDATE ON content_topic
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- content_draft 内容稿件表 ----------
CREATE TABLE IF NOT EXISTS content_draft (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    topic_id BIGINT NOT NULL REFERENCES content_topic(id),
    draft_no VARCHAR(64) NOT NULL,
    genre VARCHAR(32) NOT NULL CHECK (genre IN ('article','post','script','copy')),
    title VARCHAR(200) DEFAULT NULL,
    body TEXT NOT NULL,
    citations JSONB NOT NULL DEFAULT '[]'::jsonb,
    version_no INTEGER NOT NULL DEFAULT 1,
    word_count INTEGER DEFAULT NULL,
    draft_status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (draft_status IN ('draft','reviewing','approved','rejected','published')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE content_draft IS '内容稿件表';
COMMENT ON COLUMN content_draft.id IS '内部主键';
COMMENT ON COLUMN content_draft.uuid IS '外部唯一标识';
COMMENT ON COLUMN content_draft.topic_id IS '所属选题ID';
COMMENT ON COLUMN content_draft.draft_no IS '稿件编号';
COMMENT ON COLUMN content_draft.genre IS '体裁';
COMMENT ON COLUMN content_draft.title IS '稿件标题';
COMMENT ON COLUMN content_draft.body IS '正文';
COMMENT ON COLUMN content_draft.citations IS '引用明细';
COMMENT ON COLUMN content_draft.version_no IS '版本号';
COMMENT ON COLUMN content_draft.word_count IS '字数';
COMMENT ON COLUMN content_draft.draft_status IS '稿件状态';
COMMENT ON COLUMN content_draft.create_by IS '创建人ID';
COMMENT ON COLUMN content_draft.update_by IS '更新人ID';
COMMENT ON COLUMN content_draft.delete_by IS '删除人ID';
COMMENT ON COLUMN content_draft.create_time IS '创建时间';
COMMENT ON COLUMN content_draft.update_time IS '更新时间';
COMMENT ON COLUMN content_draft.delete_time IS '删除时间';
COMMENT ON COLUMN content_draft.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN content_draft.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_content_draft_uuid ON content_draft (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_draft_draft_no ON content_draft (draft_no);
CREATE UNIQUE INDEX IF NOT EXISTS uq_content_draft_topic_id_version_no ON content_draft (topic_id, version_no);
CREATE INDEX IF NOT EXISTS idx_content_draft_topic_id ON content_draft (topic_id);
CREATE INDEX IF NOT EXISTS idx_content_draft_draft_status ON content_draft (draft_status);
CREATE INDEX IF NOT EXISTS idx_content_draft_genre ON content_draft (genre);

DROP TRIGGER IF EXISTS trigger_content_draft_update_time ON content_draft;
CREATE TRIGGER trigger_content_draft_update_time
BEFORE UPDATE ON content_draft
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-4-002: 风格模板与自检记录表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- style_binding 风格绑定表 ----------
CREATE TABLE IF NOT EXISTS style_binding (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    preference_template_id BIGINT NOT NULL REFERENCES preference_template(id),
    scene_type VARCHAR(32) NOT NULL,
    content_type VARCHAR(32) DEFAULT NULL,
    forbidden_expressions TEXT DEFAULT NULL,
    style_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    effective_start TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    effective_end TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    binding_status VARCHAR(20) NOT NULL DEFAULT 'active' CHECK (binding_status IN ('active','disabled')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE style_binding IS '风格绑定表';
COMMENT ON COLUMN style_binding.id IS '内部主键';
COMMENT ON COLUMN style_binding.uuid IS '外部唯一标识';
COMMENT ON COLUMN style_binding.preference_template_id IS '偏好模板ID';
COMMENT ON COLUMN style_binding.scene_type IS '适用场景';
COMMENT ON COLUMN style_binding.content_type IS '内容类型';
COMMENT ON COLUMN style_binding.forbidden_expressions IS '禁用表达快照';
COMMENT ON COLUMN style_binding.style_snapshot IS '风格参数快照';
COMMENT ON COLUMN style_binding.effective_start IS '生效开始时间';
COMMENT ON COLUMN style_binding.effective_end IS '生效结束时间';
COMMENT ON COLUMN style_binding.binding_status IS '绑定状态';
COMMENT ON COLUMN style_binding.create_by IS '创建人ID';
COMMENT ON COLUMN style_binding.update_by IS '更新人ID';
COMMENT ON COLUMN style_binding.delete_by IS '删除人ID';
COMMENT ON COLUMN style_binding.create_time IS '创建时间';
COMMENT ON COLUMN style_binding.update_time IS '更新时间';
COMMENT ON COLUMN style_binding.delete_time IS '删除时间';
COMMENT ON COLUMN style_binding.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN style_binding.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_style_binding_uuid ON style_binding (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_style_binding_preference_template_id_scene_type_content_type ON style_binding (preference_template_id, scene_type, content_type) WHERE is_deleted = 0;
CREATE INDEX IF NOT EXISTS idx_style_binding_preference_template_id ON style_binding (preference_template_id);
CREATE INDEX IF NOT EXISTS idx_style_binding_scene_type ON style_binding (scene_type);

DROP TRIGGER IF EXISTS trigger_style_binding_update_time ON style_binding;
CREATE TRIGGER trigger_style_binding_update_time
BEFORE UPDATE ON style_binding
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- sensitive_check_record 敏感词自检记录表 ----------
CREATE TABLE IF NOT EXISTS sensitive_check_record (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    draft_id BIGINT NOT NULL REFERENCES content_draft(id),
    check_type VARCHAR(20) NOT NULL CHECK (check_type IN ('sensitive_word','forbidden_expression','compliance')),
    hit_word VARCHAR(100) DEFAULT NULL,
    matched_text VARCHAR(500) DEFAULT NULL,
    sentence_no INTEGER DEFAULT NULL,
    hit_position VARCHAR(500) DEFAULT NULL,
    replace_suggestion VARCHAR(500) DEFAULT NULL,
    handle_result VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (handle_result IN ('pending','replaced','ignored','rejected')),
    handler_id BIGINT DEFAULT NULL,
    check_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE sensitive_check_record IS '敏感词自检记录表';
COMMENT ON COLUMN sensitive_check_record.id IS '内部主键';
COMMENT ON COLUMN sensitive_check_record.uuid IS '外部唯一标识';
COMMENT ON COLUMN sensitive_check_record.draft_id IS '稿件ID';
COMMENT ON COLUMN sensitive_check_record.check_type IS '自检类型';
COMMENT ON COLUMN sensitive_check_record.hit_word IS '命中敏感词';
COMMENT ON COLUMN sensitive_check_record.matched_text IS '命中原文';
COMMENT ON COLUMN sensitive_check_record.sentence_no IS '命中句子序号';
COMMENT ON COLUMN sensitive_check_record.hit_position IS '命中位置';
COMMENT ON COLUMN sensitive_check_record.replace_suggestion IS '替换建议';
COMMENT ON COLUMN sensitive_check_record.handle_result IS '处理结果';
COMMENT ON COLUMN sensitive_check_record.handler_id IS '处理人ID';
COMMENT ON COLUMN sensitive_check_record.check_time IS '自检时间';
COMMENT ON COLUMN sensitive_check_record.create_by IS '创建人ID';
COMMENT ON COLUMN sensitive_check_record.update_by IS '更新人ID';
COMMENT ON COLUMN sensitive_check_record.delete_by IS '删除人ID';
COMMENT ON COLUMN sensitive_check_record.create_time IS '创建时间';
COMMENT ON COLUMN sensitive_check_record.update_time IS '更新时间';
COMMENT ON COLUMN sensitive_check_record.delete_time IS '删除时间';
COMMENT ON COLUMN sensitive_check_record.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN sensitive_check_record.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_sensitive_check_record_uuid ON sensitive_check_record (uuid);
CREATE INDEX IF NOT EXISTS idx_sensitive_check_record_draft_id ON sensitive_check_record (draft_id);
CREATE INDEX IF NOT EXISTS idx_sensitive_check_record_draft_id_sentence_no ON sensitive_check_record (draft_id, sentence_no);
CREATE INDEX IF NOT EXISTS idx_sensitive_check_record_handle_result ON sensitive_check_record (handle_result);
CREATE INDEX IF NOT EXISTS idx_sensitive_check_record_check_type ON sensitive_check_record (check_type);

DROP TRIGGER IF EXISTS trigger_sensitive_check_record_update_time ON sensitive_check_record;
CREATE TRIGGER trigger_sensitive_check_record_update_time
BEFORE UPDATE ON sensitive_check_record
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-5-001: 纪要与日程表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- meeting_minutes 会议纪要表 ----------
CREATE TABLE IF NOT EXISTS meeting_minutes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    minutes_no VARCHAR(64) NOT NULL,
    meeting_title VARCHAR(200) NOT NULL,
    meeting_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    participants JSONB NOT NULL DEFAULT '[]'::jsonb,
    location VARCHAR(200) DEFAULT NULL,
    agenda JSONB NOT NULL DEFAULT '[]'::jsonb,
    conclusions TEXT DEFAULT NULL,
    todos JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence NUMERIC(5,4) DEFAULT NULL CHECK (confidence >= 0 AND confidence <= 1),
    audio_source VARCHAR(500) DEFAULT NULL,
    minutes_status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (minutes_status IN ('draft','confirmed','archived')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE meeting_minutes IS '会议纪要表';
COMMENT ON COLUMN meeting_minutes.id IS '内部主键';
COMMENT ON COLUMN meeting_minutes.uuid IS '外部唯一标识';
COMMENT ON COLUMN meeting_minutes.minutes_no IS '纪要编号';
COMMENT ON COLUMN meeting_minutes.meeting_title IS '会议主题';
COMMENT ON COLUMN meeting_minutes.meeting_time IS '会议时间';
COMMENT ON COLUMN meeting_minutes.participants IS '参与人';
COMMENT ON COLUMN meeting_minutes.location IS '会议地点';
COMMENT ON COLUMN meeting_minutes.agenda IS '议题';
COMMENT ON COLUMN meeting_minutes.conclusions IS '结论';
COMMENT ON COLUMN meeting_minutes.todos IS '待办（内容/责任人/截止时间）';
COMMENT ON COLUMN meeting_minutes.confidence IS '整体置信度';
COMMENT ON COLUMN meeting_minutes.audio_source IS '音频来源';
COMMENT ON COLUMN meeting_minutes.minutes_status IS '纪要状态';
COMMENT ON COLUMN meeting_minutes.create_by IS '创建人ID';
COMMENT ON COLUMN meeting_minutes.update_by IS '更新人ID';
COMMENT ON COLUMN meeting_minutes.delete_by IS '删除人ID';
COMMENT ON COLUMN meeting_minutes.create_time IS '创建时间';
COMMENT ON COLUMN meeting_minutes.update_time IS '更新时间';
COMMENT ON COLUMN meeting_minutes.delete_time IS '删除时间';
COMMENT ON COLUMN meeting_minutes.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN meeting_minutes.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_meeting_minutes_uuid ON meeting_minutes (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_meeting_minutes_minutes_no ON meeting_minutes (minutes_no);
CREATE INDEX IF NOT EXISTS idx_meeting_minutes_meeting_time ON meeting_minutes (meeting_time);
CREATE INDEX IF NOT EXISTS idx_meeting_minutes_minutes_status ON meeting_minutes (minutes_status);
CREATE INDEX IF NOT EXISTS idx_meeting_minutes_meeting_title ON meeting_minutes (meeting_title);

DROP TRIGGER IF EXISTS trigger_meeting_minutes_update_time ON meeting_minutes;
CREATE TRIGGER trigger_meeting_minutes_update_time
BEFORE UPDATE ON meeting_minutes
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- schedule_item 日程表 ----------
CREATE TABLE IF NOT EXISTS schedule_item (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    title VARCHAR(200) NOT NULL,
    start_time TIMESTAMP(3) WITH TIME ZONE NOT NULL,
    end_time TIMESTAMP(3) WITH TIME ZONE NOT NULL,
    participants JSONB NOT NULL DEFAULT '[]'::jsonb,
    location VARCHAR(200) DEFAULT NULL,
    conflict_flag SMALLINT NOT NULL DEFAULT 0 CHECK (conflict_flag IN (0, 1)),
    conflict_detail VARCHAR(500) DEFAULT NULL,
    source_minutes_id BIGINT DEFAULT NULL REFERENCES meeting_minutes(id),
    confidence NUMERIC(5,4) DEFAULT NULL CHECK (confidence >= 0 AND confidence <= 1),
    schedule_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (schedule_status IN ('pending','confirmed','cancelled')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL,
    CONSTRAINT ck_schedule_item_1 CHECK (end_time > start_time)
);

COMMENT ON TABLE schedule_item IS '日程表';
COMMENT ON COLUMN schedule_item.id IS '内部主键';
COMMENT ON COLUMN schedule_item.uuid IS '外部唯一标识';
COMMENT ON COLUMN schedule_item.title IS '日程标题';
COMMENT ON COLUMN schedule_item.start_time IS '开始时间';
COMMENT ON COLUMN schedule_item.end_time IS '结束时间';
COMMENT ON COLUMN schedule_item.participants IS '参与人';
COMMENT ON COLUMN schedule_item.location IS '地点';
COMMENT ON COLUMN schedule_item.conflict_flag IS '冲突标记';
COMMENT ON COLUMN schedule_item.conflict_detail IS '冲突说明';
COMMENT ON COLUMN schedule_item.source_minutes_id IS '来源纪要ID';
COMMENT ON COLUMN schedule_item.confidence IS '置信度';
COMMENT ON COLUMN schedule_item.schedule_status IS '日程状态';
COMMENT ON COLUMN schedule_item.create_by IS '创建人ID';
COMMENT ON COLUMN schedule_item.update_by IS '更新人ID';
COMMENT ON COLUMN schedule_item.delete_by IS '删除人ID';
COMMENT ON COLUMN schedule_item.create_time IS '创建时间';
COMMENT ON COLUMN schedule_item.update_time IS '更新时间';
COMMENT ON COLUMN schedule_item.delete_time IS '删除时间';
COMMENT ON COLUMN schedule_item.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN schedule_item.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_item_uuid ON schedule_item (uuid);
CREATE INDEX IF NOT EXISTS idx_schedule_item_start_time ON schedule_item (start_time);
CREATE INDEX IF NOT EXISTS idx_schedule_item_start_time_end_time ON schedule_item (start_time, end_time);
CREATE INDEX IF NOT EXISTS idx_schedule_item_conflict_flag ON schedule_item (conflict_flag);
CREATE INDEX IF NOT EXISTS idx_schedule_item_schedule_status ON schedule_item (schedule_status);

DROP TRIGGER IF EXISTS trigger_schedule_item_update_time ON schedule_item;
CREATE TRIGGER trigger_schedule_item_update_time
BEFORE UPDATE ON schedule_item
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-5-002: 邮件草稿与冲突记录表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- mail_draft 邮件草稿表 ----------
CREATE TABLE IF NOT EXISTS mail_draft (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    recipients JSONB NOT NULL DEFAULT '[]'::jsonb,
    cc_recipients JSONB NOT NULL DEFAULT '[]'::jsonb,
    subject VARCHAR(500) NOT NULL,
    body TEXT NOT NULL,
    attachments JSONB NOT NULL DEFAULT '[]'::jsonb,
    related_task_id BIGINT DEFAULT NULL,
    reference_minutes_id BIGINT DEFAULT NULL REFERENCES meeting_minutes(id),
    draft_status VARCHAR(20) NOT NULL DEFAULT 'draft' CHECK (draft_status IN ('draft','reviewing','approved','discarded')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE mail_draft IS '邮件草稿表';
COMMENT ON COLUMN mail_draft.id IS '内部主键';
COMMENT ON COLUMN mail_draft.uuid IS '外部唯一标识';
COMMENT ON COLUMN mail_draft.recipients IS '收件人';
COMMENT ON COLUMN mail_draft.cc_recipients IS '抄送人';
COMMENT ON COLUMN mail_draft.subject IS '邮件主题';
COMMENT ON COLUMN mail_draft.body IS '邮件正文';
COMMENT ON COLUMN mail_draft.attachments IS '附件';
COMMENT ON COLUMN mail_draft.related_task_id IS '关联任务ID';
COMMENT ON COLUMN mail_draft.reference_minutes_id IS '关联纪要ID';
COMMENT ON COLUMN mail_draft.draft_status IS '草稿状态';
COMMENT ON COLUMN mail_draft.create_by IS '创建人ID';
COMMENT ON COLUMN mail_draft.update_by IS '更新人ID';
COMMENT ON COLUMN mail_draft.delete_by IS '删除人ID';
COMMENT ON COLUMN mail_draft.create_time IS '创建时间';
COMMENT ON COLUMN mail_draft.update_time IS '更新时间';
COMMENT ON COLUMN mail_draft.delete_time IS '删除时间';
COMMENT ON COLUMN mail_draft.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN mail_draft.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_mail_draft_uuid ON mail_draft (uuid);
CREATE INDEX IF NOT EXISTS idx_mail_draft_draft_status ON mail_draft (draft_status);
CREATE INDEX IF NOT EXISTS idx_mail_draft_related_task_id ON mail_draft (related_task_id);
CREATE INDEX IF NOT EXISTS idx_mail_draft_create_time ON mail_draft (create_time);

DROP TRIGGER IF EXISTS trigger_mail_draft_update_time ON mail_draft;
CREATE TRIGGER trigger_mail_draft_update_time
BEFORE UPDATE ON mail_draft
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- schedule_conflict 日程冲突记录表 ----------
CREATE TABLE IF NOT EXISTS schedule_conflict (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    schedule_item_id BIGINT NOT NULL REFERENCES schedule_item(id),
    conflict_item_id BIGINT DEFAULT NULL REFERENCES schedule_item(id),
    conflict_start TIMESTAMP(3) WITH TIME ZONE NOT NULL,
    conflict_end TIMESTAMP(3) WITH TIME ZONE NOT NULL,
    conflict_desc VARCHAR(500) DEFAULT NULL,
    optional_slots JSONB NOT NULL DEFAULT '[]'::jsonb,
    handle_result VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (handle_result IN ('pending','resolved','ignored')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL,
    CONSTRAINT ck_schedule_conflict_1 CHECK (conflict_end > conflict_start)
);

COMMENT ON TABLE schedule_conflict IS '日程冲突记录表';
COMMENT ON COLUMN schedule_conflict.id IS '内部主键';
COMMENT ON COLUMN schedule_conflict.uuid IS '外部唯一标识';
COMMENT ON COLUMN schedule_conflict.schedule_item_id IS '冲突日程ID';
COMMENT ON COLUMN schedule_conflict.conflict_item_id IS '冲突对象日程ID';
COMMENT ON COLUMN schedule_conflict.conflict_start IS '冲突开始时间';
COMMENT ON COLUMN schedule_conflict.conflict_end IS '冲突结束时间';
COMMENT ON COLUMN schedule_conflict.conflict_desc IS '冲突说明';
COMMENT ON COLUMN schedule_conflict.optional_slots IS '可选时段';
COMMENT ON COLUMN schedule_conflict.handle_result IS '处理结果';
COMMENT ON COLUMN schedule_conflict.create_by IS '创建人ID';
COMMENT ON COLUMN schedule_conflict.update_by IS '更新人ID';
COMMENT ON COLUMN schedule_conflict.delete_by IS '删除人ID';
COMMENT ON COLUMN schedule_conflict.create_time IS '创建时间';
COMMENT ON COLUMN schedule_conflict.update_time IS '更新时间';
COMMENT ON COLUMN schedule_conflict.delete_time IS '删除时间';
COMMENT ON COLUMN schedule_conflict.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN schedule_conflict.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_schedule_conflict_uuid ON schedule_conflict (uuid);
CREATE INDEX IF NOT EXISTS idx_schedule_conflict_schedule_item_id ON schedule_conflict (schedule_item_id);
CREATE INDEX IF NOT EXISTS idx_schedule_conflict_conflict_start_conflict_end ON schedule_conflict (conflict_start, conflict_end);
CREATE INDEX IF NOT EXISTS idx_schedule_conflict_handle_result ON schedule_conflict (handle_result);

DROP TRIGGER IF EXISTS trigger_schedule_conflict_update_time ON schedule_conflict;
CREATE TRIGGER trigger_schedule_conflict_update_time
BEFORE UPDATE ON schedule_conflict
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-13-001: 渠道配置表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- channel_config 外部渠道配置表 ----------
CREATE TABLE IF NOT EXISTS channel_config (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    channel_no VARCHAR(64) NOT NULL,
    channel_name VARCHAR(200) NOT NULL,
    channel_type VARCHAR(20) NOT NULL CHECK (channel_type IN ('email','calendar','im','crm','meeting')),
    account_name VARCHAR(200) DEFAULT NULL,
    auth_status VARCHAR(20) NOT NULL DEFAULT 'unauthorized' CHECK (auth_status IN ('unauthorized','authorized','expired','revoked')),
    auth_credential_ref VARCHAR(500) DEFAULT NULL,
    auth_expire_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    config_content JSONB NOT NULL DEFAULT '{}'::jsonb,
    channel_status VARCHAR(20) NOT NULL DEFAULT 'enabled' CHECK (channel_status IN ('enabled','disabled')),
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE channel_config IS '外部渠道配置表';
COMMENT ON COLUMN channel_config.id IS '内部主键';
COMMENT ON COLUMN channel_config.uuid IS '外部唯一标识';
COMMENT ON COLUMN channel_config.channel_no IS '渠道编号';
COMMENT ON COLUMN channel_config.channel_name IS '渠道名称';
COMMENT ON COLUMN channel_config.channel_type IS '渠道类型（五类）';
COMMENT ON COLUMN channel_config.account_name IS '渠道账号';
COMMENT ON COLUMN channel_config.auth_status IS '鉴权状态';
COMMENT ON COLUMN channel_config.auth_credential_ref IS '鉴权凭据引用';
COMMENT ON COLUMN channel_config.auth_expire_time IS '鉴权有效期';
COMMENT ON COLUMN channel_config.config_content IS '渠道配置内容';
COMMENT ON COLUMN channel_config.channel_status IS '渠道状态';
COMMENT ON COLUMN channel_config.create_by IS '创建人ID';
COMMENT ON COLUMN channel_config.update_by IS '更新人ID';
COMMENT ON COLUMN channel_config.delete_by IS '删除人ID';
COMMENT ON COLUMN channel_config.create_time IS '创建时间';
COMMENT ON COLUMN channel_config.update_time IS '更新时间';
COMMENT ON COLUMN channel_config.delete_time IS '删除时间';
COMMENT ON COLUMN channel_config.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN channel_config.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_config_uuid ON channel_config (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_config_channel_no ON channel_config (channel_no);
CREATE INDEX IF NOT EXISTS idx_channel_config_channel_type ON channel_config (channel_type);
CREATE INDEX IF NOT EXISTS idx_channel_config_auth_status ON channel_config (auth_status);
CREATE INDEX IF NOT EXISTS idx_channel_config_auth_expire_time ON channel_config (auth_expire_time);

DROP TRIGGER IF EXISTS trigger_channel_config_update_time ON channel_config;
CREATE TRIGGER trigger_channel_config_update_time
BEFORE UPDATE ON channel_config
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-13-002: 事件与内外发记录表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- external_event 外部事件表 ----------
CREATE TABLE IF NOT EXISTS external_event (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    event_source VARCHAR(32) NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    raw_content TEXT DEFAULT NULL,
    normalized_fields JSONB NOT NULL DEFAULT '{}'::jsonb,
    channel_id BIGINT DEFAULT NULL REFERENCES channel_config(id),
    received_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    process_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (process_status IN ('pending','processed','failed','ignored')),
    related_task_id BIGINT DEFAULT NULL,
    processed_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE external_event IS '外部事件表';
COMMENT ON COLUMN external_event.id IS '内部主键';
COMMENT ON COLUMN external_event.uuid IS '外部唯一标识';
COMMENT ON COLUMN external_event.event_source IS '事件来源';
COMMENT ON COLUMN external_event.event_type IS '事件类型';
COMMENT ON COLUMN external_event.idempotency_key IS '幂等键';
COMMENT ON COLUMN external_event.raw_content IS '原始内容';
COMMENT ON COLUMN external_event.normalized_fields IS '归一化字段';
COMMENT ON COLUMN external_event.channel_id IS '来源渠道ID';
COMMENT ON COLUMN external_event.received_time IS '接收时间';
COMMENT ON COLUMN external_event.process_status IS '处理状态';
COMMENT ON COLUMN external_event.related_task_id IS '关联任务ID';
COMMENT ON COLUMN external_event.processed_time IS '处理时间';
COMMENT ON COLUMN external_event.create_by IS '创建人ID';
COMMENT ON COLUMN external_event.update_by IS '更新人ID';
COMMENT ON COLUMN external_event.delete_by IS '删除人ID';
COMMENT ON COLUMN external_event.create_time IS '创建时间';
COMMENT ON COLUMN external_event.update_time IS '更新时间';
COMMENT ON COLUMN external_event.delete_time IS '删除时间';
COMMENT ON COLUMN external_event.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN external_event.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_external_event_uuid ON external_event (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_external_event_idempotency_key ON external_event (idempotency_key) WHERE is_deleted = 0;
CREATE INDEX IF NOT EXISTS idx_external_event_event_source_event_type ON external_event (event_source, event_type);
CREATE INDEX IF NOT EXISTS idx_external_event_process_status ON external_event (process_status);
CREATE INDEX IF NOT EXISTS idx_external_event_received_time ON external_event (received_time);

DROP TRIGGER IF EXISTS trigger_external_event_update_time ON external_event;
CREATE TRIGGER trigger_external_event_update_time
BEFORE UPDATE ON external_event
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- outbound_record 外发记录表 ----------
CREATE TABLE IF NOT EXISTS outbound_record (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    event_id BIGINT DEFAULT NULL REFERENCES external_event(id),
    channel_id BIGINT DEFAULT NULL REFERENCES channel_config(id),
    target VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    check_result VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (check_result IN ('pending','pass','blocked','degraded')),
    check_detail VARCHAR(500) DEFAULT NULL,
    receipt_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (receipt_status IN ('pending','sent','delivered','failed','receipted')),
    receipt_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    sent_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    retry_count SMALLINT NOT NULL DEFAULT 0,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE outbound_record IS '外发记录表';
COMMENT ON COLUMN outbound_record.id IS '内部主键';
COMMENT ON COLUMN outbound_record.uuid IS '外部唯一标识';
COMMENT ON COLUMN outbound_record.event_id IS '关联事件ID';
COMMENT ON COLUMN outbound_record.channel_id IS '外发渠道ID';
COMMENT ON COLUMN outbound_record.target IS '外发目标';
COMMENT ON COLUMN outbound_record.content IS '外发内容';
COMMENT ON COLUMN outbound_record.check_result IS '围栏校验结果';
COMMENT ON COLUMN outbound_record.check_detail IS '校验明细';
COMMENT ON COLUMN outbound_record.receipt_status IS '回执状态';
COMMENT ON COLUMN outbound_record.receipt_time IS '回执时间';
COMMENT ON COLUMN outbound_record.sent_time IS '发送时间';
COMMENT ON COLUMN outbound_record.retry_count IS '重试次数';
COMMENT ON COLUMN outbound_record.create_by IS '创建人ID';
COMMENT ON COLUMN outbound_record.update_by IS '更新人ID';
COMMENT ON COLUMN outbound_record.delete_by IS '删除人ID';
COMMENT ON COLUMN outbound_record.create_time IS '创建时间';
COMMENT ON COLUMN outbound_record.update_time IS '更新时间';
COMMENT ON COLUMN outbound_record.delete_time IS '删除时间';
COMMENT ON COLUMN outbound_record.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN outbound_record.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_outbound_record_uuid ON outbound_record (uuid);
CREATE INDEX IF NOT EXISTS idx_outbound_record_event_id ON outbound_record (event_id);
CREATE INDEX IF NOT EXISTS idx_outbound_record_channel_id ON outbound_record (channel_id);
CREATE INDEX IF NOT EXISTS idx_outbound_record_receipt_status ON outbound_record (receipt_status);
CREATE INDEX IF NOT EXISTS idx_outbound_record_check_result ON outbound_record (check_result);

DROP TRIGGER IF EXISTS trigger_outbound_record_update_time ON outbound_record;
CREATE TRIGGER trigger_outbound_record_update_time
BEFORE UPDATE ON outbound_record
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- WBS-DB-14-001: 链路实例与步骤记录表结构设计
-- 创建时间: 2026-11-16
-- =============================================

-- ---------- chain_instance 协作链路实例表 ----------
CREATE TABLE IF NOT EXISTS chain_instance (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    chain_no VARCHAR(64) NOT NULL,
    task_id BIGINT DEFAULT NULL,
    chain_type VARCHAR(32) NOT NULL,
    current_step_no SMALLINT NOT NULL DEFAULT 1 CHECK (current_step_no BETWEEN 1 AND 7),
    current_step_name VARCHAR(64) DEFAULT NULL,
    chain_status VARCHAR(20) NOT NULL DEFAULT 'running' CHECK (chain_status IN ('running','completed','failed','paused','cancelled')),
    t_level VARCHAR(4) DEFAULT NULL CHECK (t_level IN ('T1','T2','T3','T4')),
    execution_mode VARCHAR(20) DEFAULT NULL CHECK (execution_mode IN ('copilot','autopilot')),
    start_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    end_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    duration_ms INTEGER DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE chain_instance IS '协作链路实例表';
COMMENT ON COLUMN chain_instance.id IS '内部主键';
COMMENT ON COLUMN chain_instance.uuid IS '外部唯一标识';
COMMENT ON COLUMN chain_instance.chain_no IS '链路编号';
COMMENT ON COLUMN chain_instance.task_id IS '关联任务ID';
COMMENT ON COLUMN chain_instance.chain_type IS '链路类型';
COMMENT ON COLUMN chain_instance.current_step_no IS '当前步骤序号';
COMMENT ON COLUMN chain_instance.current_step_name IS '当前步骤名称';
COMMENT ON COLUMN chain_instance.chain_status IS '链路状态';
COMMENT ON COLUMN chain_instance.t_level IS 'T 等级';
COMMENT ON COLUMN chain_instance.execution_mode IS '执行模式';
COMMENT ON COLUMN chain_instance.start_time IS '开始时间';
COMMENT ON COLUMN chain_instance.end_time IS '结束时间';
COMMENT ON COLUMN chain_instance.duration_ms IS '总耗时（毫秒）';
COMMENT ON COLUMN chain_instance.create_by IS '创建人ID';
COMMENT ON COLUMN chain_instance.update_by IS '更新人ID';
COMMENT ON COLUMN chain_instance.delete_by IS '删除人ID';
COMMENT ON COLUMN chain_instance.create_time IS '创建时间';
COMMENT ON COLUMN chain_instance.update_time IS '更新时间';
COMMENT ON COLUMN chain_instance.delete_time IS '删除时间';
COMMENT ON COLUMN chain_instance.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN chain_instance.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_chain_instance_uuid ON chain_instance (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chain_instance_chain_no ON chain_instance (chain_no);
CREATE INDEX IF NOT EXISTS idx_chain_instance_task_id ON chain_instance (task_id);
CREATE INDEX IF NOT EXISTS idx_chain_instance_chain_status ON chain_instance (chain_status);
CREATE INDEX IF NOT EXISTS idx_chain_instance_start_time ON chain_instance (start_time);

DROP TRIGGER IF EXISTS trigger_chain_instance_update_time ON chain_instance;
CREATE TRIGGER trigger_chain_instance_update_time
BEFORE UPDATE ON chain_instance
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- ---------- chain_step 协作链路步骤记录表 ----------
CREATE TABLE IF NOT EXISTS chain_step (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    uuid UUID NOT NULL DEFAULT gen_random_uuid(),
    chain_id BIGINT NOT NULL REFERENCES chain_instance(id),
    step_no SMALLINT NOT NULL CHECK (step_no BETWEEN 1 AND 7),
    step_name VARCHAR(64) NOT NULL,
    step_status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (step_status IN ('pending','running','completed','failed','skipped')),
    input_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    output_result JSONB NOT NULL DEFAULT '{}'::jsonb,
    start_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    end_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    duration_ms INTEGER DEFAULT NULL,
    error_message VARCHAR(500) DEFAULT NULL,
    create_by BIGINT NOT NULL DEFAULT 0,
    update_by BIGINT NOT NULL DEFAULT 0,
    delete_by BIGINT DEFAULT NULL,
    create_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    update_time TIMESTAMP(3) WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    delete_time TIMESTAMP(3) WITH TIME ZONE DEFAULT NULL,
    is_deleted SMALLINT NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    remark VARCHAR(500) DEFAULT NULL
);

COMMENT ON TABLE chain_step IS '协作链路步骤记录表';
COMMENT ON COLUMN chain_step.id IS '内部主键';
COMMENT ON COLUMN chain_step.uuid IS '外部唯一标识';
COMMENT ON COLUMN chain_step.chain_id IS '链路实例ID';
COMMENT ON COLUMN chain_step.step_no IS '步骤序号（1-7）';
COMMENT ON COLUMN chain_step.step_name IS '步骤名称';
COMMENT ON COLUMN chain_step.step_status IS '步骤状态';
COMMENT ON COLUMN chain_step.input_snapshot IS '输入快照';
COMMENT ON COLUMN chain_step.output_result IS '输出结果';
COMMENT ON COLUMN chain_step.start_time IS '开始时间';
COMMENT ON COLUMN chain_step.end_time IS '结束时间';
COMMENT ON COLUMN chain_step.duration_ms IS '耗时（毫秒）';
COMMENT ON COLUMN chain_step.error_message IS '错误信息';
COMMENT ON COLUMN chain_step.create_by IS '创建人ID';
COMMENT ON COLUMN chain_step.update_by IS '更新人ID';
COMMENT ON COLUMN chain_step.delete_by IS '删除人ID';
COMMENT ON COLUMN chain_step.create_time IS '创建时间';
COMMENT ON COLUMN chain_step.update_time IS '更新时间';
COMMENT ON COLUMN chain_step.delete_time IS '删除时间';
COMMENT ON COLUMN chain_step.is_deleted IS '逻辑删除标志';
COMMENT ON COLUMN chain_step.remark IS '备注';

CREATE UNIQUE INDEX IF NOT EXISTS uq_chain_step_uuid ON chain_step (uuid);
CREATE UNIQUE INDEX IF NOT EXISTS uq_chain_step_chain_id_step_no ON chain_step (chain_id, step_no);
CREATE INDEX IF NOT EXISTS idx_chain_step_chain_id ON chain_step (chain_id);
CREATE INDEX IF NOT EXISTS idx_chain_step_chain_id_step_no ON chain_step (chain_id, step_no);
CREATE INDEX IF NOT EXISTS idx_chain_step_step_status ON chain_step (step_status);

DROP TRIGGER IF EXISTS trigger_chain_step_update_time ON chain_step;
CREATE TRIGGER trigger_chain_step_update_time
BEFORE UPDATE ON chain_step
FOR EACH ROW EXECUTE FUNCTION update_update_time();

-- =============================================
-- 初始化数据：全局运行模式配置（单记录）
-- 创建时间: 2026-11-16
-- 说明：config_key='global' 全局唯一，默认模式 copilot（陪跑），可重复执行
-- =============================================

INSERT INTO runtime_mode_config (uuid, config_key, default_mode, global_switch, circuit_breaker_status, config_version)
SELECT gen_random_uuid(), 'global', 'copilot', 'on', 'closed', 1
WHERE NOT EXISTS (
    SELECT 1 FROM runtime_mode_config WHERE config_key = 'global' AND is_deleted = 0
);
