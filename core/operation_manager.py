from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Optional


@dataclass(frozen=True)
class OperationInfo:
    name: str
    started_at: datetime
    description: str = ""


class OperationManager:
    _lock = Lock()
    _current: Optional[OperationInfo] = None

    @classmethod
    def start(cls, name: str, description: str = "") -> bool:
        """
        Tenta iniciar uma operação exclusiva.
        Retorna True se conseguiu iniciar.
        Retorna False se já houver outra operação em andamento.
        """
        with cls._lock:
            if cls._current is not None:
                return False

            cls._current = OperationInfo(
                name=name,
                started_at=datetime.now(),
                description=description,
            )
            return True

    @classmethod
    def finish(cls) -> None:
        """Finaliza a operação atual."""
        with cls._lock:
            cls._current = None

    @classmethod
    def current(cls) -> Optional[OperationInfo]:
        """Retorna a operação em andamento, se existir."""
        with cls._lock:
            return cls._current

    @classmethod
    def is_running(cls) -> bool:
        """Indica se existe alguma operação exclusiva ativa."""
        with cls._lock:
            return cls._current is not None

    @classmethod
    def current_name(cls) -> str:
        """Nome da operação atual, ou string vazia."""
        current = cls.current()
        return current.name if current else ""

    @classmethod
    def current_description(cls) -> str:
        """Descrição da operação atual, ou string vazia."""
        current = cls.current()
        return current.description if current else ""

    @classmethod
    def elapsed_seconds(cls) -> int:
        """Tempo decorrido da operação atual em segundos."""
        current = cls.current()
        if current is None:
            return 0
        return int((datetime.now() - current.started_at).total_seconds())

    @classmethod
    def assert_available(cls) -> bool:
        """
        Conveniência para uso em UI:
        - True se pode iniciar outra operação
        - False se já houver uma em andamento
        """
        return not cls.is_running()
