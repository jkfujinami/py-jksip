import structlog
from typing import Optional, Final
from .base import SipTransaction, SipEvent, TransactionState, EventType
from ..message import SipRequest, SipResponse
from ...core.timer import TimerService
from ...core.transport import SipTransport

logger = structlog.get_logger(__name__)

# RFC 3261 Default Timers (ms)
T1: Final[int] = 500
T2: Final[int] = 4000
T4: Final[int] = 5000

class UasTransaction(SipTransaction):
    """
    SIP UAS Transaction state machine.
    Responsible for handling an incoming request and sending responses.
    
    State Transition Map (RFC 3261):
    - NULL -> Received Request -> TRYING (INVITE) or PROCEEDING (Non-INVITE)
    - TRYING -> Send 1xx -> PROCEEDING
    - PROCEEDING -> Send 2xx -> TERMINATED (INVITE) or COMPLETED (Non-INVITE)
    - PROCEEDING -> Send 3xx-6xx -> COMPLETED
    - COMPLETED -> Received ACK -> CONFIRMED (INVITE only)
    """
    def __init__(
        self, 
        key: str, 
        timer_service: TimerService, 
        transport: SipTransport,
        remote_addr: tuple[str, int]
    ):
        super().__init__(key, timer_service)
        self._transport = transport
        self._remote_addr = remote_addr
        self._last_tx_response: Optional[SipResponse] = None
        self._retransmit_interval = T1

    async def process_event(self, event: SipEvent) -> None:
        """
        Processes server-side events.
        """
        if self.state == TransactionState.NULL:
            await self._on_state_null(event)
        elif self.state == TransactionState.TRYING:
            await self._on_state_trying(event)
        elif self.state == TransactionState.PROCEEDING:
            await self._on_state_proceeding(event)
        elif self.state == TransactionState.COMPLETED:
            await self._on_state_completed(event)
        elif self.state == TransactionState.CONFIRMED:
            await self._on_state_confirmed(event)
        else:
            logger.warning("uas_unhandled_state", state=self.state, event=event.type)

    async def _on_state_null(self, event: SipEvent) -> None:
        """
        Initial state for UAS. Triggered by the reception of the first request.
        """
        if event.type != EventType.MESSAGE or not isinstance(event.message, SipRequest):
            logger.error("uas_null_invalid_event", type=event.type)
            return

        self.request = event.message
        logger.info("uas_request_received", method=self.request.method, key=self.key)

        # RFC 3261: UAS immediately moves to TRYING (INVITE) or PROCEEDING (Non-INVITE)
        if self.request.method == "INVITE":
            self.set_state(TransactionState.TRYING)
        else:
            self.set_state(TransactionState.PROCEEDING)

    async def send_response(self, response: SipResponse) -> None:
        """
        Public interface to send a response through this transaction.
        This triggers state transitions.
        """
        self._last_tx_response = response
        await self._transport.send(self._remote_addr, str(response).encode())

        if 100 <= response.status_code <= 199:
            self.set_state(TransactionState.PROCEEDING)
        elif 200 <= response.status_code <= 299:
            if self.request.method == "INVITE":
                # INVITE 2xx is handled specially by the UA (Dialog)
                self.set_state(TransactionState.TERMINATED)
            else:
                self._enter_completed_state()
        elif 300 <= response.status_code <= 699:
            self._enter_completed_state()

    async def _on_state_trying(self, event: SipEvent) -> None:
        """Waiting for TU to provide a response."""
        if event.type == EventType.MESSAGE and isinstance(event.message, SipRequest):
            # Retransmitted request: PJSIP/RFC doesn't retransmit 100 Trying automatically 
            # unless specifically told, but we can ignore or let TU handle.
            logger.debug("uas_ignoring_retransmitted_request_in_trying", key=self.key)

    async def _on_state_proceeding(self, event: SipEvent) -> None:
        """Provisional response already sent."""
        if event.type == EventType.MESSAGE and isinstance(event.message, SipRequest):
            # Retransmitted request: must retransmit the last provisional response
            if self._last_tx_response:
                logger.info("uas_retransmitting_provisional_response", key=self.key)
                await self._transport.send(self._remote_addr, str(self._last_tx_response).encode())

    def _enter_completed_state(self) -> None:
        """Transitions to COMPLETED and starts retransmission (Timer G/H/J)."""
        self.set_state(TransactionState.COMPLETED)
        
        # For non-INVITE, Timer J (cleanup) is 64*T1
        if self.request.method != "INVITE":
            timeout_ms = 64 * T1
            self._timer_service.schedule(f"{self.key}_timer_j", timeout_ms, self._on_timer_j)
            
            # Start Timer G (retransmit final response) if unreliable
            if not self._transport.is_reliable:
                self._timer_service.schedule(f"{self.key}_timer_g", T1, self._on_timer_g)

    async def _on_state_completed(self, event: SipEvent) -> None:
        """Waiting for ACK (INVITE) or just waiting for cleanup (Non-INVITE)."""
        if event.type == EventType.MESSAGE and isinstance(event.message, SipRequest):
            if event.message.method == "ACK" and self.request.method == "INVITE":
                self.set_state(TransactionState.CONFIRMED)
                self._timer_service.cancel(f"{self.key}_timer_i") # Timer I for INVITE
            else:
                # Retransmitted request: retransmit final response
                if self._last_tx_response:
                    await self._transport.send(self._remote_addr, str(self._last_tx_response).encode())

    async def _on_state_confirmed(self, event: SipEvent) -> None:
        """INVITE only: ACK received. Waiting for Timer I to terminate."""
        pass # Transitions to TERMINATED via timer

    def _on_timer_g(self) -> None:
        """Retransmit final response timer."""
        logger.debug("uas_timer_g_fired", key=self.key)

    def _on_timer_j(self) -> None:
        """Cleanup timer for non-INVITE."""
        logger.info("uas_timer_j_fired", key=self.key)

    def _on_timer_i(self) -> None:
        """Cleanup timer for INVITE."""
        logger.info("uas_timer_i_fired", key=self.key)
