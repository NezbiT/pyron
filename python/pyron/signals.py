"""Fine-grained hooks. Lifespan and middleware stay separate."""

from __future__ import annotations

import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

Listener = Callable[..., Any]


class Signals:
    """Name → listeners. `dispatch` awaits coroutines and ignores extra kwargs."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = defaultdict(list)

    def on(self, name: str, fn: Listener) -> Listener:
        self._listeners[name].append(fn)
        return fn

    def names(self) -> list[str]:
        return sorted(self._listeners)

    async def dispatch(self, name: str, **kwargs: Any) -> None:
        for fn in list(self._listeners.get(name, ())):
            result = fn(**_accepted(fn, kwargs))
            if inspect.isawaitable(result):
                await result


def _accepted(fn: Callable[..., Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return kwargs
    if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()):
        return kwargs
    return {key: value for key, value in kwargs.items() if key in sig.parameters}
