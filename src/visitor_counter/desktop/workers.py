from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, Signal, Slot


class WorkerSignals(QObject):
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class FunctionWorker(QRunnable):
    def __init__(self, function: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
        super().__init__()
        self.function = function
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.function(*self.args, **self.kwargs)
            try:
                self.signals.result.emit(result)
            except RuntimeError:
                return
        except Exception as exc:  # noqa: BLE001 - surfaced as a controlled GUI error
            try:
                self.signals.error.emit(str(exc))
            except RuntimeError:
                return
        finally:
            try:
                self.signals.finished.emit()
            except RuntimeError:
                pass
