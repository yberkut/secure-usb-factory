from __future__ import annotations

import shlex
from dataclasses import dataclass
from typing import Callable, Sequence

LogSink = Callable[[str], None]


def format_command(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


@dataclass
class ExecutionContext:
    verbose: bool = False
    sink: LogSink | None = None

    def emit(self, message: str) -> None:
        if self.verbose and self.sink is not None:
            self.sink(message)

    def step(self, index: int, total: int, message: str) -> None:
        self.emit(f"[{index}/{total}] {message}")

    def info(self, message: str) -> None:
        self.emit(message)

    def command(self, cmd: Sequence[str]) -> None:
        self.emit(f"$ {format_command(cmd)}")


def make_context(verbose: bool = False, sink: LogSink | None = None) -> ExecutionContext:
    return ExecutionContext(verbose=verbose, sink=sink)
