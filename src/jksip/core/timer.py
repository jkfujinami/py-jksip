import asyncio
from typing import Callable, Any, Optional
from dataclasses import dataclass, field
import structlog

logger = structlog.get_logger(__name__)

@dataclass
class TimerEntry:
    """Represents a registered timer entry."""
    id: str
    delay: float
    callback: Callable[..., Any]
    args: tuple = field(default_factory=tuple)
    handle: Optional[asyncio.TimerHandle] = None

class TimerService:
    """
    Manages timers for SIP transactions and retransmissions.
    Wraps asyncio's event loop to provide a consistent interface.
    """
    def __init__(self):
        self._timers: dict[str, TimerEntry] = {}

    def schedule(self, entry_id: str, delay_ms: int, callback: Callable[..., Any], *args, **kwargs) -> None:
        """
        Schedules a callback to be run after delay_ms.
        If entry_id already exists, it is cancelled and rescheduled.
        """
        self.cancel(entry_id)
        
        delay_sec = delay_ms / 1000.0
        loop = asyncio.get_running_loop()
        
        handle = loop.call_later(delay_sec, self._run_callback, entry_id)
        
        self._timers[entry_id] = TimerEntry(
            id=entry_id,
            delay=delay_sec,
            callback=callback,
            args=args,
            handle=handle
        )
        logger.debug("timer_scheduled", id=entry_id, delay_ms=delay_ms, callback=callback.__name__)

    def cancel(self, entry_id: str) -> None:
        """Cancels a scheduled timer."""
        if entry_id in self._timers:
            entry = self._timers.pop(entry_id)
            if entry.handle:
                entry.handle.cancel()
            logger.debug("timer_cancelled", id=entry_id)

    def _run_callback(self, entry_id: str) -> None:
        """Internal method to execute the callback and clean up."""
        if entry_id in self._timers:
            entry = self._timers.pop(entry_id)
            try:
                # To handle both sync and async callbacks if needed, 
                # but PJSIP logic is typically synchronous state changes.
                if asyncio.iscoroutinefunction(entry.callback):
                    asyncio.create_task(entry.callback(*entry.args))
                else:
                    entry.callback(*entry.args)
            except Exception as e:
                logger.error("timer_callback_error", id=entry_id, error=str(e))
