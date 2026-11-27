"""管理后台路由（/front/admin，全部 POST）"""
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import AliasChoices, BaseModel, Field

from common import ApiProblem, get_client_ip, success
from admin.auth import require_admin_user
from chief.chief_controller import ChiefController

from admin.admin_controller import (
    ExpertController,
    AuthController,
    LogController,
    MemberController,
    QuotaController,
    RegistryController,
)

public_router = APIRouter(prefix="/front/admin", tags=["前台-管理后台-认证"])
router = APIRouter(
    prefix="/front/admin",
    tags=["前台-管理后台"],
    dependencies=[Depends(require_admin_user)],
)


class IdRequest(BaseModel):
    id: str = Field(..., description="记录 data_id")


class MemberCreateRequest(BaseModel):
    email: str = Field(..., description="邮箱")
    role: str = Field("成员", description="拥有者/管理员/成员/访客")
    name: str | None = Field(None, description="姓名，默认取邮箱前缀")


class MemberUpdateRequest(BaseModel):
    id: str
    email: str | None = None
    role: str | None = None
    name: str | None = None
    enabled: bool | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class AcceptInviteRequest(BaseModel):
    token: str
    password: str
    name: str | None = None


class ExpertCreateRequest(BaseModel):
    name: str
    role: str | None = None
    model: str | None = None
    model_id: str | None = Field(
        None, validation_alias=AliasChoices("model_id", "modelId"), description="模型 data_id"
    )
    temperature: str | None = None
    prompt: str | None = None
    enabled: bool | None = None
    mcp_ids: list[str] | None = Field(
        None, validation_alias=AliasChoices("mcp_ids", "mcpIds"), description="MCP data_id 列表"
    )
    skill_ids: list[str] | None = Field(
        None, validation_alias=AliasChoices("skill_ids", "skillIds"), description="SKILL data_id 列表"
    )
    settings: dict[str, Any] | None = Field(
        None, description="工具调用步数、超时与写入授权"
    )


class ExpertUpdateRequest(ExpertCreateRequest):
    id: str


class ExpertChatRequest(BaseModel):
    id: str
    message: str
    session_id: str | None = Field(
        None, validation_alias=AliasChoices("session_id", "sessionId")
    )
    project_id: str | None = Field(
        None, validation_alias=AliasChoices("project_id", "projectId")
    )
    task_id: str | None = Field(
        None, validation_alias=AliasChoices("task_id", "taskId")
    )
    history: list[dict[str, str]] | None = None
    attachments: list[dict[str, Any]] | None = None


class ExpertRunsRequest(BaseModel):
    id: str
    limit: int | None = Field(5, ge=1, le=20)


class ExpertSessionsRequest(BaseModel):
    id: str
    limit: int | None = Field(20, ge=1, le=100)


class ExpertResumeRequest(BaseModel):
    id: str
    approvals: dict[str, bool] | list[dict[str, Any]]


class RegistryCreateRequest(BaseModel):
    name: str
    description: str | None = None
    meta: str | None = None
    status: str | None = Field(None, description="可用/异常/未测试")
    endpoint: str | None = None
    model_key: str | None = Field(
        None, validation_alias=AliasChoices("model_key", "modelKey")
    )
    provider: str | None = None
    capabilities: dict[str, Any] | None = None
    enabled: bool | None = None
    priority: int | None = Field(None, ge=1, le=1000)
    config: dict[str, Any] | None = None
    api_key: str | None = Field(
        None, validation_alias=AliasChoices("api_key", "apiKey"), description="模型 API Key，仅密文入库"
    )


class RegistryUpdateRequest(RegistryCreateRequest):
    id: str


class ModelTestRequest(BaseModel):
    id: str
    deep: bool = False


class ModelQuotaItem(BaseModel):
    id: str
    limit: float


class UpdateModelQuotasRequest(BaseModel):
    items: list[ModelQuotaItem]


class UpdateAlertSettingsRequest(BaseModel):
    threshold: str | None = None
    channel: str | None = None
    notify_admin: bool | None = Field(
        None, validation_alias=AliasChoices("notify_admin", "notifyAdmin")
    )


class ProjectQuotaCreateRequest(BaseModel):
    name: str
    used: float = 0
    limit: float


class ProjectQuotaUpdateRequest(BaseModel):
    items: list[ModelQuotaItem]
    stop_on_exceed: bool | None = Field(
        None, validation_alias=AliasChoices("stop_on_exceed", "stopOnExceed")
    )


class LogListRequest(BaseModel):
    limit: int | None = Field(None, description="默认 50，最大 200")
    page: int | None = None
    page_size: int | None = Field(
        None, validation_alias=AliasChoices("page_size", "pageSize")
    )
    keyword: str | None = None
    action: str | None = None
    start_time: str | None = Field(
        None, validation_alias=AliasChoices("start_time", "startTime")
    )
    end_time: str | None = Field(
        None, validation_alias=AliasChoices("end_time", "endTime")
    )


def _body(req: BaseModel | None) -> dict[str, Any]:
    return req.model_dump(exclude_unset=True) if req is not None else {}


# ---------------- 认证 ----------------

@public_router.post("/auth/login", summary="管理员登录")
async def admin_login(req: LoginRequest):
    return success(await AuthController().login(_body(req)))


@public_router.post("/auth/accept-invite", summary="接受成员邀请")
async def admin_accept_invite(req: AcceptInviteRequest):
    return success(await AuthController().accept_invite(_body(req)))


@public_router.post("/auth/dev-login", summary="开发环境自动登录")
async def admin_dev_login(request: Request):
    from settings import settings

    if not settings.admin_auto_login:
        raise ApiProblem(403, "开发自动登录未启用。")
    if get_client_ip(request) not in {"127.0.0.1", "::1", "localhost"}:
        raise ApiProblem(403, "开发自动登录仅允许本机调用。")
    return success(await AuthController().development_login())


@router.post("/auth/me", summary="当前管理员")
async def admin_me():
    return success(await AuthController().me())


@router.post("/auth/change-password", summary="修改管理员密码")
async def admin_change_password(req: ChangePasswordRequest):
    await AuthController().change_password(_body(req))
    return success(None)


# ---------------- 成员 ----------------

@router.post("/members/list", summary="成员列表")
async def members_list(req: dict[str, Any] | None = None):
    return success(await MemberController().list())


@router.post("/members/create", summary="邀请成员")
async def members_create(req: MemberCreateRequest):
    return success(await MemberController().create(_body(req)))


@router.post("/members/update", summary="更新成员")
async def members_update(req: MemberUpdateRequest):
    await MemberController().update(_body(req))
    return success(None)


@router.post("/members/delete", summary="移除成员")
async def members_delete(req: IdRequest):
    await MemberController().delete(_body(req))
    return success(None)


@router.post("/members/resend-invite", summary="重新发送邀请")
async def members_resend_invite(req: IdRequest):
    return success(await MemberController().resend_invitation(_body(req)))


# ---------------- 专家 ----------------

@router.post("/experts/list", summary="专家列表")
async def experts_list(req: dict[str, Any] | None = None):
    return success(await ExpertController().list())


@router.post("/experts/create", summary="新增专家")
async def experts_create(req: ExpertCreateRequest):
    return success(await ExpertController().create(_body(req)))


@router.post("/experts/update", summary="更新专家")
async def experts_update(req: ExpertUpdateRequest):
    await ExpertController().update(_body(req))
    return success(None)


@router.post("/experts/delete", summary="删除专家")
async def experts_delete(req: IdRequest):
    await ExpertController().delete(_body(req))
    return success(None)


@router.post("/experts/test", summary="测试专家（按所选模型真实连通）")
async def experts_test(req: IdRequest):
    return success(await ExpertController().test(_body(req)))


@router.post("/experts/chat", summary="与专家进行真实对话")
async def experts_chat(req: ExpertChatRequest):
    return success(await ExpertController().chat(_body(req)))


@router.post("/experts/chat/resume", summary="确认并继续专家工具调用")
async def experts_chat_resume(req: ExpertResumeRequest):
    return success(await ExpertController().resume(_body(req)))


@router.post("/experts/runs", summary="专家最近运行记录")
async def experts_runs(req: ExpertRunsRequest):
    return success(await ExpertController().runs(_body(req)))


@router.post("/experts/sessions/list", summary="专家历史会话")
async def experts_sessions_list(req: ExpertSessionsRequest):
    return success(await ExpertController().sessions(_body(req)))


@router.post("/experts/sessions/get", summary="获取专家历史会话")
async def experts_sessions_get(req: IdRequest):
    return success(await ExpertController().session(_body(req)))


@router.post("/experts/sessions/delete", summary="删除专家历史会话")
async def experts_sessions_delete(req: IdRequest):
    await ExpertController().delete_session(_body(req))
    return success(None)


# ---------------- 注册表：模型 / MCP / SKILL ----------------

@router.post("/models/list", summary="模型列表")
async def models_list(req: dict[str, Any] | None = None):
    return success(await RegistryController("model").list())


@router.post("/models/create", summary="新增模型")
async def models_create(req: RegistryCreateRequest):
    return success(await RegistryController("model").create(_body(req)))


@router.post("/models/update", summary="更新模型")
async def models_update(req: RegistryUpdateRequest):
    await RegistryController("model").update(_body(req))
    return success(None)


@router.post("/models/delete", summary="删除模型")
async def models_delete(req: IdRequest):
    await RegistryController("model").delete(_body(req))
    return success(None)


@router.post("/models/test", summary="测试模型连通性（真实请求供应商）")
async def models_test(req: ModelTestRequest):
    return success(await RegistryController("model").test(_body(req)))


@router.post("/models/health-check", summary="检查全部启用模型健康状态")
async def models_health_check():
    return success(await RegistryController("model").health_check())


@router.post("/mcp/list", summary="MCP 列表")
async def mcp_list(req: dict[str, Any] | None = None):
    return success(await RegistryController("mcp").list())


@router.post("/mcp/create", summary="新增 MCP")
async def mcp_create(req: RegistryCreateRequest):
    return success(await RegistryController("mcp").create(_body(req)))


@router.post("/mcp/update", summary="更新 MCP")
async def mcp_update(req: RegistryUpdateRequest):
    await RegistryController("mcp").update(_body(req))
    return success(None)


@router.post("/mcp/delete", summary="删除 MCP")
async def mcp_delete(req: IdRequest):
    await RegistryController("mcp").delete(_body(req))
    return success(None)


@router.post("/mcp/test", summary="测试 MCP 端点或命令")
async def mcp_test(req: IdRequest):
    return success(await RegistryController("mcp").test(_body(req)))


@router.post("/mcp/tools", summary="发现 MCP 工具")
async def mcp_tools(req: IdRequest):
    return success(await RegistryController("mcp").tools(_body(req)))


@router.post("/skills/list", summary="SKILL 列表")
async def skills_list(req: dict[str, Any] | None = None):
    return success(await RegistryController("skill").list())


@router.post("/skills/create", summary="新增 SKILL")
async def skills_create(req: RegistryCreateRequest):
    return success(await RegistryController("skill").create(_body(req)))


@router.post("/skills/update", summary="更新 SKILL")
async def skills_update(req: RegistryUpdateRequest):
    await RegistryController("skill").update(_body(req))
    return success(None)


@router.post("/skills/delete", summary="删除 SKILL")
async def skills_delete(req: IdRequest):
    await RegistryController("skill").delete(_body(req))
    return success(None)


@router.post("/skills/test", summary="测试 SKILL 定义完整性")
async def skills_test(req: IdRequest):
    return success(await RegistryController("skill").test(_body(req)))


# ---------------- 额度 ----------------

@router.post("/quota/get-summary", summary="额度总览")
async def quota_summary():
    return success(await QuotaController().summary())


@router.post("/quota/get-project-quotas", summary="项目额度")
async def quota_projects():
    return success(await QuotaController().project_quotas())


@router.post("/quota/get-model-quotas", summary="模型额度")
async def quota_models():
    return success(await QuotaController().model_quotas())


@router.post("/quota/update-model-quotas", summary="更新模型额度上限")
async def quota_update_models(req: UpdateModelQuotasRequest):
    await QuotaController().update_model_quotas(_body(req))
    return success(None)


@router.post("/quota/create-project", summary="新增额度项目")
async def quota_create_project(req: ProjectQuotaCreateRequest):
    return success(await QuotaController().create_project(_body(req)))


@router.post("/quota/update-project-quotas", summary="更新项目额度")
async def quota_update_projects(req: ProjectQuotaUpdateRequest):
    await QuotaController().update_project_quotas(_body(req))
    return success(None)


@router.post("/quota/delete-project", summary="删除额度项目")
async def quota_delete_project(req: IdRequest):
    await QuotaController().delete_project(_body(req))
    return success(None)


@router.post("/quota/get-alert-settings", summary="额度告警设置")
async def quota_alert_settings():
    return success(await QuotaController().alert_settings())


@router.post("/quota/update-alert-settings", summary="更新额度告警设置")
async def quota_update_alert_settings(req: UpdateAlertSettingsRequest):
    await QuotaController().update_alert_settings(_body(req))
    return success(None)


# ---------------- 操作日志 ----------------

@router.post("/chief/get-settings", summary="总管设置")
async def chief_get_settings():
    return success(await ChiefController().get_settings())


@router.post("/chief/update-settings", summary="更新总管设置")
async def chief_update_settings(req: dict[str, Any]):
    return success(await ChiefController().update_settings(req))


@router.post("/call/get-settings", summary="通话设置")
async def call_get_settings():
    return success(await ChiefController().get_call_settings())


@router.post("/call/update-settings", summary="更新通话设置")
async def call_update_settings(req: dict[str, Any]):
    return success(await ChiefController().update_call_settings(req))


@router.post("/logs/list", summary="操作日志")
async def logs_list(req: LogListRequest | None = None):
    return success(await LogController().list(_body(req)))
