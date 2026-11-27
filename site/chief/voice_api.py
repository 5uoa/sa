"""DeepSeek ASR / TTS 服务代理。"""
from typing import AsyncIterator

import httpx

import db
from admin import secret
from common import ApiProblem, text

DEFAULT_ASR_URL = "https://api.deepseek.com/v1/tools/asr"
DEFAULT_TTS_URL = "https://api.deepseek.com/v1/tools/tts"


async def _deepseek_api_key() -> str:
    row = await db.fetchrow(
        """
        SELECT api_key_enc
          FROM ai_model
         WHERE is_deleted = false
           AND enabled = true
           AND (
               endpoint ILIKE '%api.deepseek.com%'
               OR model_key ILIKE '%deepseek%'
               OR name ILIKE '%deepseek%'
           )
         ORDER BY priority ASC, id ASC
         LIMIT 1
        """
    )
    api_key = secret.decrypt(str((row or {}).get("api_key_enc") or ""))
    if not api_key:
        raise ApiProblem(503, "未配置可用的 DeepSeek API Key。")
    return api_key


async def _voice_endpoints() -> tuple[str, str]:
    row = await db.fetchrow(
        """
        SELECT asr_url AS "asrUrl", tts_url AS "ttsUrl"
          FROM call_setting
         WHERE id = 1
         LIMIT 1
        """
    )
    return (
        text((row or {}).get("asrUrl")) or DEFAULT_ASR_URL,
        text((row or {}).get("ttsUrl")) or DEFAULT_TTS_URL,
    )


async def transcribe_audio(
    content: bytes, filename: str, content_type: str
) -> dict:
    if not content:
        raise ApiProblem(400, "音频文件为空。")
    if len(content) > 8 * 1024 * 1024:
        raise ApiProblem(413, "音频文件不能超过 8 MiB。")
    api_key = await _deepseek_api_key()
    asr_url, _ = await _voice_endpoints()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                asr_url,
                headers={"Authorization": f"Bearer {api_key}"},
                files={
                    "file": (
                        filename or "speech.wav",
                        content,
                        content_type or "audio/wav",
                    )
                },
            )
    except httpx.HTTPError as exc:
        raise ApiProblem(503, f"DeepSeek ASR 连接失败：{exc.__class__.__name__}")
    if response.status_code >= 400:
        raise ApiProblem(
            response.status_code,
            f"DeepSeek ASR 失败：{response.text[:300]}",
        )
    payload = response.json()
    transcript = text(payload.get("text"))
    if not transcript:
        raise ApiProblem(400, "DeepSeek ASR 未返回转写文本。")
    return {
        "text": transcript,
        "requestId": text(payload.get("request_id")),
        "durationMs": int(payload.get("duration_ms") or 0),
    }


async def stream_synthesized_speech(
    content: str, voice_id: str
) -> AsyncIterator[bytes]:
    value = content.strip()
    if not value:
        raise ApiProblem(400, "朗读文本不能为空。")
    if len(value) > 10000:
        value = value[:10000]
    api_key = await _deepseek_api_key()
    _, tts_url = await _voice_endpoints()
    payload = {
        "text": value,
        "voice_id": voice_id if voice_id in {"stella", "tide"} else "stella",
        "format": "wav",
        "filter_markdown": True,
    }
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream(
                "POST",
                tts_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise ApiProblem(
                        response.status_code,
                        f"DeepSeek TTS 失败：{body[:300]}",
                    )
                async for chunk in response.aiter_bytes():
                    if chunk:
                        yield chunk
    except ApiProblem:
        raise
    except httpx.HTTPError as exc:
        raise ApiProblem(503, f"DeepSeek TTS 连接失败：{exc.__class__.__name__}")
