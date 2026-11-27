"""总管 API：Phase 1 会话闭环与 Phase 2 Harness² 单步递归。"""
import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import AliasChoices, BaseModel, Field
from starlette.responses import StreamingResponse

from admin.auth import require_admin_user
from common import success, text
from chief.chief_controller import ChiefController
from chief.voice_api import stream_synthesized_speech, transcribe_audio

router = APIRouter(
    prefix="/front/chief",
    tags=["前台-总管"],
    dependencies=[Depends(require_admin_user)],
)


class SessionCreateRequest(BaseModel):
    title: str | None = None
    project_id: str | None = Field(
        None, validation_alias=AliasChoices("project_id", "projectId")
    )


class SessionGetRequest(BaseModel):
    session_id: str = Field(
        ..., validation_alias=AliasChoices("session_id", "sessionId")
    )


class ChiefSendRequest(BaseModel):
    session_id: str | None = Field(
        None, validation_alias=AliasChoices("session_id", "sessionId")
    )
    message: str = ""
    title: str | None = None
    expert_id: str | None = Field(
        None, validation_alias=AliasChoices("expert_id", "expertId")
    )
    attachments: list[dict[str, Any]] | None = None
    recursion_mode: str | None = Field(
        None, validation_alias=AliasChoices("recursion_mode", "recursionMode")
    )
    recursion_k: int | None = Field(
        1, validation_alias=AliasChoices("recursion_k", "recursionK")
    )


class RunRequest(BaseModel):
    run_id: str = Field(..., validation_alias=AliasChoices("run_id", "runId"))


class HarnessListRequest(BaseModel):
    domain: str | None = None


class VoiceTTSRequest(BaseModel):
    text: str
    voice_id: str = Field("stella", validation_alias=AliasChoices("voice_id", "voiceId"))


def _body(request: BaseModel | None) -> dict[str, Any]:
    return request.model_dump(exclude_unset=True) if request is not None else {}


@router.post("/sessions/list", summary="总管会话列表")
async def list_sessions(req: dict[str, Any] | None = None):
    return success(await ChiefController().list_sessions(req))


@router.post("/sessions/create", summary="新建总管会话")
async def create_session(req: SessionCreateRequest | None = None):
    return success(await ChiefController().create_session(_body(req)))


@router.post("/projects/list", summary="项目卡片列表")
async def list_projects():
    return success(await ChiefController().list_projects())


@router.post("/experts/list", summary="项目可绑定专家列表")
async def list_experts():
    return success(await ChiefController().list_experts())


@router.post("/workspace/get", summary="项目工作台五栏数据")
async def get_workspace(req: dict[str, Any] | None = None):
    return success(await ChiefController().get_workspace(req or {}))


@router.post("/workspace/projects/create", summary="新建工作台项目")
async def create_workspace_project(req: dict[str, Any]):
    return success(await ChiefController().create_project(req))


@router.post("/workspace/projects/update", summary="修改工作台项目")
async def update_workspace_project(req: dict[str, Any]):
    return success(await ChiefController().update_project(req))


@router.post("/workspace/projects/archive", summary="归档工作台项目")
async def archive_workspace_project(req: dict[str, Any]):
    await ChiefController().set_project_archived(req, True)
    return success(None)


@router.post("/workspace/projects/restore", summary="恢复工作台项目")
async def restore_workspace_project(req: dict[str, Any]):
    await ChiefController().set_project_archived(req, False)
    return success(None)


@router.post("/workspace/projects/duplicate", summary="复制工作台项目")
async def duplicate_workspace_project(req: dict[str, Any]):
    return success(await ChiefController().duplicate_project(req))


@router.post("/workspace/projects/delete", summary="删除工作台项目")
async def delete_workspace_project(req: dict[str, Any]):
    await ChiefController().delete_project(req)
    return success(None)


@router.post("/workspace/projects/document/save", summary="保存项目需求或方案")
async def save_project_document(req: dict[str, Any]):
    return success(await ChiefController().save_project_document(req))


@router.post("/workspace/projects/document/generate", summary="专家生成项目需求或方案")
async def generate_project_document(req: dict[str, Any]):
    return success(await ChiefController().generate_project_document(req))


@router.post("/workspace/projects/document/confirm", summary="确认项目需求或方案")
async def confirm_project_document(req: dict[str, Any]):
    return success(await ChiefController().confirm_project_document(req))


@router.post("/workspace/projects/task-plan/save", summary="保存任务分解")
async def save_project_task_plan(req: dict[str, Any]):
    return success(await ChiefController().save_project_task_plan(req))


@router.post("/workspace/projects/task-plan/generate", summary="生成任务分解")
async def generate_project_task_plan(req: dict[str, Any]):
    return success(await ChiefController().generate_project_task_plan(req))


@router.post("/workspace/projects/task-plan/confirm", summary="确认任务分解")
async def confirm_project_task_plan(req: dict[str, Any]):
    return success(await ChiefController().confirm_project_task_plan(req))


@router.post("/workspace/projects/execute", summary="创建并自动执行项目任务")
async def execute_project(req: dict[str, Any]):
    return success(await ChiefController().execute_project(req))


@router.post("/workspace/projects/complete", summary="完成项目")
async def complete_project(req: dict[str, Any]):
    return success(await ChiefController().complete_project(req))


@router.post("/workspace/workflow/command", summary="通过固定会话内容推进项目流程")
async def project_workflow_command(req: dict[str, Any]):
    return success(await ChiefController().project_workflow_command(req))


@router.post("/workspace/milestones/create", summary="新建任务包")
async def create_milestone(req: dict[str, Any]):
    return success(await ChiefController().create_milestone(req))


@router.post("/workspace/milestones/update", summary="修改任务包")
async def update_milestone(req: dict[str, Any]):
    return success(await ChiefController().update_milestone(req))


@router.post("/workspace/milestones/delete", summary="删除任务包")
async def delete_milestone(req: dict[str, Any]):
    await ChiefController().delete_milestone(req)
    return success(None)


@router.post("/workspace/tasks/create", summary="新建任务")
async def create_task(req: dict[str, Any]):
    return success(await ChiefController().create_task(req))


@router.post("/workspace/tasks/update", summary="修改任务")
async def update_task(req: dict[str, Any]):
    return success(await ChiefController().update_task(req))


@router.post("/workspace/tasks/delete", summary="删除任务")
async def delete_task(req: dict[str, Any]):
    await ChiefController().delete_task(req)
    return success(None)


@router.post("/workspace/tasks/confirm-spec", summary="确认任务需求")
async def confirm_task_spec(req: dict[str, Any]):
    return success(await ChiefController().confirm_task_spec(req))


@router.post("/workspace/tasks/start-execution", summary="任务开始执行")
async def start_task_execution(req: dict[str, Any]):
    return success(await ChiefController().start_task_execution(req))


@router.post("/workspace/deliverables/from-message", summary="专家回复设为成果草稿")
async def set_deliverable_draft(req: dict[str, Any]):
    return success(await ChiefController().set_deliverable_draft(req))


@router.post("/workspace/deliverables/save-draft", summary="保存成果草稿")
async def save_deliverable_draft(req: dict[str, Any]):
    return success(await ChiefController().save_deliverable_draft(req))


@router.post("/workspace/deliverables/confirm", summary="确认成果版本")
async def confirm_deliverable(req: dict[str, Any]):
    return success(await ChiefController().confirm_deliverable(req))


@router.post("/workspace/deliverables/adjust", summary="从确定版本开始调整")
async def adjust_deliverable(req: dict[str, Any]):
    return success(await ChiefController().start_deliverable_adjustment(req))


@router.post("/workspace/documents/create", summary="从消息生成独立文档")
async def create_document(req: dict[str, Any]):
    return success(await ChiefController().create_document(req))


@router.post("/workspace/documents/update", summary="保存独立文档")
async def update_document(req: dict[str, Any]):
    return success(await ChiefController().update_document(req))


@router.post("/workspace/documents/delete", summary="删除独立文档")
async def delete_document(req: dict[str, Any]):
    await ChiefController().delete_document(req)
    return success(None)


@router.post("/workspace/documents/attach", summary="将文档加入会话上下文")
async def attach_document(req: dict[str, Any]):
    return success(await ChiefController().attach_document_to_session(req))


@router.post("/workspace/tasks/complete", summary="完成任务")
async def complete_task(req: dict[str, Any]):
    return success(await ChiefController().complete_task_delivery(req))


@router.post("/workspace/attachments/add", summary="关联任务附件")
async def add_task_attachment(req: dict[str, Any]):
    return success(await ChiefController().add_task_attachment(req))


@router.post("/workspace/attachments/delete", summary="删除任务附件")
async def delete_task_attachment(req: dict[str, Any]):
    await ChiefController().delete_task_attachment(req)
    return success(None)


@router.post("/sessions/get", summary="获取总管会话")
async def get_session(req: SessionGetRequest):
    return success(await ChiefController().get_session(_body(req)))


@router.post("/sessions/delete", summary="删除总管会话")
async def delete_session(req: SessionGetRequest):
    await ChiefController().delete_session(_body(req))
    return success(None)


@router.post("/sessions/archive", summary="归档总管会话")
async def archive_session(req: SessionGetRequest):
    await ChiefController().archive_session(_body(req))
    return success(None)


@router.post("/sessions/restore", summary="恢复归档会话")
async def restore_session(req: SessionGetRequest):
    await ChiefController().restore_session(_body(req))
    return success(None)


@router.post("/messages/send", summary="发送总管消息并执行 Harness²")
async def send_message(req: ChiefSendRequest):
    return success(await ChiefController().send_message(_body(req)))


@router.post("/messages/send/stream", summary="流式发送总管消息")
async def send_message_stream(req: ChiefSendRequest):
    body = _body(req)
    controller = ChiefController()
    task = asyncio.create_task(controller.send_message(body))
    session_id = text(body.get("session_id") or body.get("sessionId"))
    seen_events: set[tuple[str, int]] = set()

    async def events():
        while True:
            try:
                if session_id:
                    runs = await controller.store.list_runs(session_id)
                    if runs:
                        run_id = runs[0]["id"]
                        for event in await controller.store.list_events(run_id):
                            key = (run_id, int(event["seq"]))
                            if key in seen_events:
                                continue
                            seen_events.add(key)
                            data = json.dumps(
                                {"runId": run_id, **event},
                                ensure_ascii=False,
                                default=str,
                            )
                            yield f"event: progress\ndata: {data}\n\n"
                if task.done():
                    final = await task
                    payload = json.dumps(final, ensure_ascii=False, default=str)
                    yield f"event: final\ndata: {payload}\n\n"
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(0.25)
            except Exception as exc:  # noqa: BLE001 - 通过 SSE 返回可读错误
                payload = json.dumps(
                    {"message": f"{exc.__class__.__name__}: {exc}"},
                    ensure_ascii=False,
                )
                yield f"event: error\ndata: {payload}\n\n"
                return

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/messages/send/voice/stream", summary="总管语音快速通道")
async def send_voice_stream(req: ChiefSendRequest):
    controller = ChiefController()

    async def events():
        try:
            async for item in controller.send_voice_events(_body(req)):
                event_name = text(item.get("type")) or "message"
                payload = json.dumps(item, ensure_ascii=False, default=str)
                yield f"event: {event_name}\ndata: {payload}\n\n"
        except Exception as exc:  # noqa: BLE001 - SSE 需返回可读错误
            payload = json.dumps(
                {
                    "type": "error",
                    "message": f"{exc.__class__.__name__}: {exc}",
                },
                ensure_ascii=False,
            )
            yield f"event: error\ndata: {payload}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/voice/transcribe", summary="DeepSeek 语音识别")
async def voice_transcribe(file: UploadFile = File(...)):
    content = await file.read()
    result = await transcribe_audio(
        content,
        file.filename or "speech.wav",
        file.content_type or "audio/wav",
    )
    return success(result)


@router.post("/voice/synthesize", summary="DeepSeek 语音合成")
async def voice_synthesize(req: VoiceTTSRequest):
    return StreamingResponse(
        stream_synthesized_speech(req.text, req.voice_id),
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/runs/get", summary="获取总管运行、候选与事件")
async def get_run(req: RunRequest):
    return success(await ChiefController().get_run(_body(req)))


@router.post("/runs/approve", summary="采纳候选 Harness 并完成运行")
async def approve_run(req: RunRequest):
    return success(await ChiefController().approve_run(_body(req)))


@router.post("/runs/reject", summary="拒绝候选 Harness")
async def reject_run(req: RunRequest):
    return success(await ChiefController().reject_run(_body(req)))


@router.post("/harness/list", summary="Harness 版本列表")
async def list_harness(req: HarnessListRequest | None = None):
    return success(await ChiefController().list_harnesses(_body(req)))
