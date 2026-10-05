"""Event-scoped answers from models running on this computer."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request
from app.local_ai import OPENER, discover, start
urlopen = OPENER.open

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ai", tags=["ai"])


@dataclass
class AISettings:
    provider: Literal["local"] = "local"
    base_url: str = "http://127.0.0.1:18090/v1"
    model: str = "redmap-qwen-local"
    timeout: float = 180.0


settings = AISettings()


class AIConfigRequest(BaseModel):
    provider: Literal["local"] = "local"
    base_url: str | None = Field(default=None, max_length=500)
    model: str | None = Field(default=None, max_length=160)


class EventChatRequest(BaseModel):
    event_id: str = Field(min_length=1, max_length=160)
    question: str = Field(min_length=1, max_length=1200)
    history: list[dict[str, str]] = Field(default_factory=list, max_length=8)


def _normalise_base_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise HTTPException(422, "base_url 不能为空")
    if not re.match(r"^https?://[^\s]+$", value, flags=re.I):
        raise HTTPException(422, "base_url 必须是 http(s) 地址")
    from urllib.parse import urlparse
    if urlparse(value).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(422, "只允许本机模型接口")
    return value.rstrip("/")


def _event(event_id: str) -> dict[str, Any]:
    # Lazy import avoids app.main ↔ app.ai import cycles during application boot.
    from app.main import load_data

    for item in load_data("events.json", []):
        if item.get("id") == event_id:
            return item
    raise HTTPException(404, "未找到该历史事件")


def _question_in_scope(event: dict[str, Any], question: str) -> bool:
    """Conservatively allow questions about the selected event only.

    Generic historical questions (原因、影响、经过、意义等) are useful even
    when they do not repeat the event title.  Explicit references to another
    event or an ``other/unrelated`` request are rejected before the model call.
    """
    text = re.sub(r"\s+", "", question).lower()
    unrelated = ("蛋糕", "菜谱", "编程", "天气", "股票", "旅游", "笑话", "ignore previous", "忽略指令", "忽略以上", "python", "javascript")
    if any(word in text for word in unrelated):
        return False
    if any(word in text for word in ("其他事件", "另一个事件", "无关问题", "换个事件", "别的事件")):
        return False
    from app.main import load_data

    theme_labels = {"long_march": "长征", "anti_japanese": "抗日战争", "revolution": "革命", "founding": "建党"}
    selected_terms = {
        str(event.get("title", "")), str(event.get("province", "")),
        str(event.get("city", "")), str(event.get("district", "")),
        *(str(value) for value in event.get("people", [])),
        *(str(value) for value in event.get("tags", [])),
        *(str(value) for value in event.get("themes", [])),
        *(theme_labels.get(str(value), "") for value in event.get("themes", [])),
    }
    selected_terms = {term.lower() for term in selected_terms if len(term) >= 2}
    other_titles = {
        str(item.get("title", "")).lower()
        for item in load_data("events.json", [])
        if item.get("id") != event.get("id") and item.get("title")
    }
    if any(title in text for title in other_titles if len(title) >= 3):
        return False
    all_events = load_data("events.json", [])
    selected_people = {str(value).lower() for value in event.get("people", [])}
    known_people = {
        str(value).lower()
        for item in all_events
        for value in item.get("people", [])
        if len(str(value)) >= 2
    }
    if any(person in text and person not in selected_people for person in known_people):
        return False
    topic_labels = ("长征", "抗日战争", "解放战争", "抗美援朝", "西安事变", "遵义会议", "五卅运动")
    selected_title = str(event.get("title", ""))
    selected_topics = {label for label in topic_labels if label in selected_title}
    selected_topics.update(theme_labels.get(str(value), "") for value in event.get("themes", []))
    if any(label in text and label not in selected_topics for label in topic_labels):
        return False
    # Questions with an explicit event term must contain a selected context term.
    explicit = any(word in text for word in ("这个事件", "该事件", "此事件", "这场", "这次", "该战役", "这场战役"))
    if explicit:
        return True
    if any(term in text for term in selected_terms):
        return True
    generic = ("原因", "背景", "经过", "过程", "结果", "影响", "意义", "贡献", "领导", "地点", "时间", "谁", "为什么", "怎么", "多少")
    # Reject generic non-history requests before they reach a local model.
    return any(word in text for word in generic)


def _context(event: dict[str, Any]) -> str:
    fields = [
        f"标题：{event.get('title', '')}", f"年份：{event.get('year', '')}",
        f"时期：{event.get('period', '')}",
        f"地点：{event.get('province', '')} {event.get('city', '')} {event.get('district', '')}",
        f"关联人物：{'、'.join(event.get('people', []))}",
        f"摘要：{event.get('summary', '')}", f"资料正文：{event.get('story', '')}",
        f"标签：{'、'.join(event.get('tags', []))}",
        f"资料来源标识：{'、'.join(str(value) for value in event.get('source_ids', []))}",
        f"资料来源定位：{event.get('source_locator', '')}",
    ]
    return "\n".join(fields)


def _completion_url(base_url: str) -> str:
    return base_url.rstrip("/") + "/chat/completions"


def _call_openai_compatible(messages: list[dict[str, str]]) -> dict[str, Any]:
    payload = json.dumps({
        "model": settings.model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 700,
        "stream": False,
    }, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    request = Request(_completion_url(settings.base_url), data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=settings.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        # Do not include request headers or the key in an error message.
        detail = "AI 服务请求失败"
        try:
            body = json.loads(exc.read().decode("utf-8"))
            detail = str(body.get("error", {}).get("message", detail))[:300]
        except Exception:
            pass
        raise RuntimeError(detail) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("无法连接本地模型，请点击本地 AI 识别并启动") from exc


def _extract_answer(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("AI 服务返回了空答案")
    message = choices[0].get("message") or {}
    content = message.get("content", "")
    if isinstance(content, list):
        content = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
    answer = str(content).strip()
    if not answer:
        raise RuntimeError("AI 服务返回了空答案")
    return answer[:8000]


@router.get("/status")
async def ai_status() -> dict[str, Any]:
    result = await asyncio.to_thread(discover)
    if result["reachable"]:
        settings.base_url, settings.model = result["base_url"], result["model"]
    return result


@router.post("/local-start")
async def local_start() -> dict[str, Any]:
    return await asyncio.to_thread(start)


def _probe_local() -> None:
    request = Request(settings.base_url.rstrip("/") + "/models", method="GET")
    with urlopen(request, timeout=1.5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    ids = [str(item.get("id")) for item in payload.get("data", []) if item.get("id")]
    if ids and settings.model not in ids:
        settings.model = ids[0]


@router.post("/config")
async def update_config(payload: AIConfigRequest) -> dict[str, Any]:
    settings.provider = payload.provider
    if payload.base_url is not None:
        settings.base_url = _normalise_base_url(payload.base_url)
    elif payload.provider == "local":
        settings.base_url = "http://127.0.0.1:1234/v1"
    if payload.model is not None and payload.model.strip():
        settings.model = payload.model.strip()
    return await ai_status()


@router.post("/event-chat")
async def event_chat(payload: EventChatRequest) -> dict[str, Any]:
    await ai_status()
    event = _event(payload.event_id)
    question = payload.question.strip()
    if not _question_in_scope(event, question):
        return {
            "event_id": payload.event_id,
            "refused": True,
            "answer": "我只能回答当前选中事件的历史细节，请围绕该事件的背景、经过、人物、影响或资料来源提问。",
        }
    history: list[dict[str, str]] = []
    for item in payload.history[-6:]:
        role, content = item.get("role"), item.get("content", "")
        if role in {"user", "assistant"} and isinstance(content, str):
            history.append({"role": role, "content": content[:1200]})
    messages = [
        {"role": "system", "content": "你是红色精神历史地图的事件讲解助手。只能依据给定事件资料回答，不能扩展到其他事件；资料没有写明时要明确说资料未提供，不得编造。使用简洁、准确的中文。\n\n当前事件资料：\n" + _context(event)},
        *history,
        {"role": "user", "content": question},
    ]
    try:
        response = await asyncio.to_thread(_call_openai_compatible, messages)
        answer = _extract_answer(response)
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc
    return {"event_id": payload.event_id, "refused": False, "answer": answer, "provider": settings.provider, "model": settings.model,
            "sources": [{"id": value} for value in event.get("source_ids", [])],
            "source_locator": event.get("source_locator")}
