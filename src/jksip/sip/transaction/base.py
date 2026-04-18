from abc import ABC, abstractmethod
from enum import Enum, auto
from typing import Optional, Any
from dataclasses import dataclass

from ..message import SipMessage, SipRequest, SipResponse
from ...core.timer import TimerService

class TransactionState(Enum):
    """
    SIP Transaction States as defined in RFC 3261.
    """
    NULL = auto()
    CALLING = auto()
    TRYING = auto()
    PROCEEDING = auto()
    COMPLETED = auto()
    CONFIRMED = auto()
    TERMINATED = auto()
    DESTROYED = auto()

class EventType(Enum):
    """Types of stimuli that can drive a transaction."""
    MESSAGE = auto()
    TIMER = auto()
    TRANSPORT_ERROR = auto()

@dataclass
class SipEvent:
    """
    Encapsulates an event that is processed by a transaction.
    Equivalent to PJSIP's pjsip_event.
    """
    type: EventType
    message: Optional[SipMessage] = None
    timer_id: Optional[str] = None
    error: Optional[Exception] = None

class SipTransaction(ABC):
    """
    Abstract Base Class for SIP Transactions (UAC & UAS).
    Following the Dependency Inversion Principle by injecting TimerService.
    """
    def __init__(self, key: str, timer_service: TimerService):
        self.key = key
        self._timer_service = timer_service
        self.state = TransactionState.NULL
        self.last_response: Optional[SipResponse] = None
        self.request: Optional[SipRequest] = None

    @abstractmethod
    async def process_event(self, event: SipEvent) -> None:
        """
        Main entry point for transaction stimuli.
        Concrete subclasses (UAC/UAS) must implement the state machine here.
        """
        pass

    def set_state(self, new_state: TransactionState) -> None:
        """Helper to transition states with logging."""
        # TODO: Add logging here using structlog once initialized
        self.state = new_state

    def cancel_all_timers(self) -> None:
        """Helper to clean up all timers associated with this transaction key."""
        # Generic cancel based on prefixes or tracked timer IDs
        pass
