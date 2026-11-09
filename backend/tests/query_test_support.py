from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.engine import Engine


def count_selects[T](engine: Engine, action: Callable[[], T]) -> tuple[T, int]:
    statements: list[str] = []

    def count(
        _connection: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _many: bool,
    ) -> None:
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(engine, "before_cursor_execute", count)
    try:
        result = action()
    finally:
        event.remove(engine, "before_cursor_execute", count)
    return result, len(statements)
