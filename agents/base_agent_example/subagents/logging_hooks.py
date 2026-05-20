from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("categorizador.pipeline")


def _extract_text_preview(user_content: Any) -> str:
    if user_content is None:
        return ""

    parts = getattr(user_content, "parts", None)
    if not parts:
        return ""

    texts: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if isinstance(text, str) and text.strip():
            texts.append(text.strip())

    preview = " ".join(texts)
    if len(preview) > 220:
        return f"{preview[:220]}..."
    return preview


def log_before_agent(callback_context: Any = None, **_: Any):
    context = callback_context
    if context is None:
        return None
    session_id = getattr(getattr(context, "session", None), "id", "")
    logger.info(
        "PIPELINE_STEP_START agent=%s user_id=%s session_id=%s invocation_id=%s message_preview=%s",
        getattr(context, "agent_name", ""),
        getattr(context, "user_id", ""),
        session_id,
        getattr(context, "invocation_id", ""),
        _extract_text_preview(getattr(context, "user_content", None)),
    )
    return None


def log_after_agent(callback_context: Any = None, **_: Any):
    context = callback_context
    if context is None:
        return None
    session_id = getattr(getattr(context, "session", None), "id", "")
    state = getattr(context, "state", None)
    state_size = 0
    if state is not None:
        keys_method = getattr(state, "keys", None)
        if callable(keys_method):
            state_size = len(list(keys_method()))
        else:
            try:
                state_size = len(state)
            except Exception:
                state_size = 0
    logger.info(
        "PIPELINE_STEP_END agent=%s user_id=%s session_id=%s invocation_id=%s state_keys=%s",
        getattr(context, "agent_name", ""),
        getattr(context, "user_id", ""),
        session_id,
        getattr(context, "invocation_id", ""),
        state_size,
    )
    return None


def log_before_tool(*args: Any, **kwargs: Any):
    tool = kwargs.get("tool") or (args[0] if len(args) > 0 else None)
    tool_args = kwargs.get("args") or (args[1] if len(args) > 1 else {})
    context = kwargs.get("context") or (args[2] if len(args) > 2 else None)

    session_id = getattr(getattr(context, "session", None), "id", "")
    logger.info(
        "PIPELINE_TOOL_START agent=%s tool=%s session_id=%s args=%s",
        getattr(context, "agent_name", ""),
        getattr(tool, "name", ""),
        session_id,
        str(tool_args)[:500],
    )
    return None


def log_after_tool(*args: Any, **kwargs: Any):
    tool = kwargs.get("tool") or (args[0] if len(args) > 0 else None)
    tool_args = kwargs.get("args") or (args[1] if len(args) > 1 else {})
    context = kwargs.get("context") or (args[2] if len(args) > 2 else None)
    tool_response = kwargs.get("tool_response") or (args[3] if len(args) > 3 else {})

    session_id = getattr(getattr(context, "session", None), "id", "")
    logger.info(
        "PIPELINE_TOOL_END agent=%s tool=%s session_id=%s args=%s response=%s",
        getattr(context, "agent_name", ""),
        getattr(tool, "name", ""),
        session_id,
        str(tool_args)[:250],
        str(tool_response)[:800],
    )
    return None
