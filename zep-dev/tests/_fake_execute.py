from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import call

from zep_dev.shared import CommandResult

ExecuteHook = Callable[[tuple[str, ...], dict[str, object]], None]


@dataclass
class _Rule:
    prefix: tuple[str, ...]
    result: CommandResult
    raises: BaseException | None = None
    hook: ExecuteHook | None = None

    def matches(self, args: tuple[str, ...]) -> bool:
        return args[: len(self.prefix)] == self.prefix


@dataclass
class FakeExecute:
    _rules: list[_Rule] = field(default_factory=list)
    calls: list[Any] = field(default_factory=list)  # unittest.mock.call objects

    def on(
        self,
        *prefix: str,
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
        raises: BaseException | None = None,
        hook: ExecuteHook | None = None,
    ) -> FakeExecute:
        self._rules.append(
            _Rule(
                prefix=prefix,
                result=CommandResult(returncode, stdout, stderr),
                raises=raises,
                hook=hook,
            )
        )
        return self

    def calls_for(self, *prefix: str) -> list[Any]:
        return [c for c in self.calls if c.args[: len(prefix)] == prefix]

    def __call__(self, *args: str, **kwargs: object) -> CommandResult:
        self.calls.append(call(*args, **kwargs))
        for rule in self._rules:
            if rule.matches(args):
                result, raises, hook = rule.result, rule.raises, rule.hook
                break
        else:
            prefixes = [rule.prefix for rule in self._rules]
            raise AssertionError(
                f"No rule matched execute{args!r} with {kwargs!r}; "
                f"configured prefixes: {prefixes!r}"
            )
        if hook is not None:
            hook(args, kwargs)
        if raises is not None:
            raise raises
        if kwargs.get("check", True) and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                list(args),
                output=result.stdout,
                stderr=result.stderr,
            )
        return result
