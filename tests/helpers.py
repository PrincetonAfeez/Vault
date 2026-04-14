from __future__ import annotations

import builtins
from collections.abc import Iterator
from contextlib import contextmanager


@contextmanager
def scripted_input(lines: list[str]) -> Iterator[None]:
    it = iter(lines)

    def fake_input(prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration as exc:
            raise AssertionError(f"Unexpected extra input() call: {prompt!r}") from exc

    old = builtins.input
    builtins.input = fake_input  # type: ignore[method-assign]
    try:
        yield
    finally:
        builtins.input = old
