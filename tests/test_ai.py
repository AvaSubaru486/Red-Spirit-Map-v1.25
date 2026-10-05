"""AI routes stay event-scoped and never expose provider secrets."""
from __future__ import annotations

import asyncio

from app import ai


def test_status_never_returns_api_key():
    result = asyncio.run(ai.ai_status())
    assert "api_key" not in result
    assert result['provider'] == 'local'


def test_remote_configuration_is_removed():
    import pytest
    from pydantic import ValidationError
    from fastapi import HTTPException
    with pytest.raises(ValidationError):
        ai.AIConfigRequest(provider='remote')
    with pytest.raises(HTTPException):
        ai._normalise_base_url('https://example.com/v1')


def test_unrelated_event_question_is_refused(monkeypatch):
    called = False

    def unexpected_call(_messages):
        nonlocal called
        called = True
        raise AssertionError("out-of-scope questions must not call the model")

    monkeypatch.setattr(ai, "_call_openai_compatible", unexpected_call)
    result = asyncio.run(ai.event_chat(ai.EventChatRequest(
        event_id="e1921_party_foundation", question="请介绍长征的路线")))
    assert result["refused"] is True
    assert called is False


def test_event_chat_uses_selected_event_and_parses_compatible_response(monkeypatch):
    captured = {}

    def fake_call(messages):
        captured["messages"] = messages
        return {"choices": [{"message": {"content": "这是当前事件的资料性回答。"}}]}

    monkeypatch.setattr(ai, "_call_openai_compatible", fake_call)
    previous = (ai.settings.provider, ai.settings.model)
    try:
        ai.settings.provider = "local"
        ai.settings.model = "test-model"
        result = asyncio.run(ai.event_chat(ai.EventChatRequest(
            event_id="e1921_party_foundation", question="这个事件的背景是什么")))
        assert result["refused"] is False
        assert result["answer"] == "这是当前事件的资料性回答。"
        assert "中国共产党第一次全国代表大会" in captured["messages"][0]["content"]
    finally:
        ai.settings.provider, ai.settings.model = previous
