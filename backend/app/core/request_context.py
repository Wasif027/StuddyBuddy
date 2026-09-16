"""Request-scoped context: the caller's own LLM API key, if they set one.

Set once in ``deps.get_current_user`` (the only place that decrypts it) and
read by the few call sites that construct an LLM/embedding client, so a
user's own key transparently takes over their traffic without threading an
extra parameter through every function in between.
"""

from __future__ import annotations

from contextvars import ContextVar

_user_llm_key: ContextVar[str | None] = ContextVar("user_llm_key", default=None)


def set_user_llm_key(key: str | None) -> None:
    _user_llm_key.set(key)


def get_user_llm_key() -> str | None:
    return _user_llm_key.get()
