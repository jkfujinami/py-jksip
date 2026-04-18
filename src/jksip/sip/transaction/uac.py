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

class UacTransaction(SipTransaction):
    """
    SIP UAC Transaction state machine.
    Responsible for sending a request and handling responses.
    """
    def __init__(
        self, 
        key: str, 
        timer_service: TimerService, 
        transport: SipTransport,
        remote_addr: tuple[str, int],
        callback: Optional[callable] = None
    ):
        super().__init__(key, timer_service)
        self._transport = transport
        self._remote_addr = remote_addr
        self._retransmit_interval = T1
        self.callback = callback

    async def process_event(self, event: SipEvent) -> None:
        """
        Processes an event based on the current state.
        Dispatches to state-specific handlers.
        """
        if self.state == TransactionState.NULL:
            await self._on_state_null(event)
        elif self.state == TransactionState.CALLING:
            await self._on_state_calling(event)
        elif self.state == TransactionState.TRYING:
            await self._on_state_trying(event)
        elif self.state == TransactionState.PROCEEDING:
            await self._on_state_proceeding(event)
        elif self.state == TransactionState.COMPLETED:
            await self._on_state_completed(event)
        else:
            logger.warning("uac_unhandled_state", state=self.state, event=event.type)

    async def _on_state_null(self, event: SipEvent) -> None:
        """
        Initial state. Expects a MESSAGE event (the request to be sent).
        Transitions to CALLING (INVITE) or TRYING (non-INVITE).
        """
        if event.type != EventType.MESSAGE or not isinstance(event.message, SipRequest):
            logger.error("uac_null_invalid_event", type=event.type)
            return

        self.request = event.message
        logger.info("uac_sending_request", method=self.request.method, key=self.key)

        # 1. Send the message
        await self._transport.send(self._remote_addr, str(self.request).encode())

        # 2. Start Timer B (Transaction Timeout)
        timeout_ms = 64 * T1  # Timer B default
        self._timer_service.schedule(
            f"{self.key}_timer_b", 
            timeout_ms, 
            self._on_timer_b
        )

        # 3. Start Timer A (Retransmit) if unreliable
        if not self._transport.is_reliable:
            self._timer_service.schedule(
                f"{self.key}_timer_a", 
                self._retransmit_interval, 
                self._on_timer_a
            )

        # 4. Transition State
        if self.request.method == "INVITE":
            self.set_state(TransactionState.CALLING)
        else:
            self.set_state(TransactionState.TRYING)

    def _on_timer_a(self) -> None:
        """Handler for Timer A (Retransmission)."""
        # Event will be injected back into the process_event loop in the next step
        # For now, this is a placeholder to fulfill the PJSIP architectual equivalent.
        logger.debug("uac_timer_a_fired", key=self.key)

    def _on_timer_b(self) -> None:
        """Handler for Timer B (Timeout)."""
        logger.warning("uac_timer_b_fired", key=self.key)
        # TODO: Trigger timeout error event

    async def _on_state_calling(self, event: SipEvent) -> None:
        """
        In CALLING state, we wait for a response.
        Incoming responses or retransmission timers drive this.
        """
        if event.type == EventType.MESSAGE and isinstance(event.message, SipResponse):
            response = event.message
            self.last_response = response
            
            if 100 <= response.status_code <= 199:
                self.set_state(TransactionState.PROCEEDING)
                self._timer_service.cancel(f"{self.key}_timer_a")
            elif 200 <= response.status_code <= 699:
                self.set_state(TransactionState.COMPLETED)
                self._timer_service.cancel(f"{self.key}_timer_a")
                self._timer_service.cancel(f"{self.key}_timer_b")
                
            if self.callback:
                await self.callback(response)
        
        elif event.type == EventType.TIMER:
            if event.timer_id == f"{self.key}_timer_a":
                # Double the interval (capped at T2) and retransmit
                self._retransmit_interval = min(self._retransmit_interval * 2, T2)
                logger.info("uac_retransmitting", key=self.key, next_interval=self._retransmit_interval)
                await self._transport.send(self._remote_addr, str(self.request).encode())
                self._timer_service.schedule(
                    f"{self.key}_timer_a", 
                    self._retransmit_interval, 
                    self._on_timer_a
                )

    async def _on_state_trying(self, event: SipEvent) -> None:
        """
        TRYING state for non-INVITE transactions.
        """
        if event.type == EventType.MESSAGE and isinstance(event.message, SipResponse):
            response = event.message
            self.last_response = response
            
            if 100 <= response.status_code <= 199:
                self.set_state(TransactionState.PROCEEDING)
            elif 200 <= response.status_code <= 699:
                self._enter_completed_state()
                
            if self.callback:
                await self.callback(response)
        
        elif event.type == EventType.TIMER:
             await self._handle_retransmit_timer(event)

    async def _on_state_proceeding(self, event: SipEvent) -> None:
        """
        Wait for a final response after a provisional one.
        """
        if event.type == EventType.MESSAGE and isinstance(event.message, SipResponse):
            response = event.message
            self.last_response = response
            
            if 200 <= response.status_code <= 699:
                if self.request.method == "INVITE" and 200 <= response.status_code <= 299:
                     # 2xx for INVITE terminates transaction immediately (ACK handled by TU)
                    self.set_state(TransactionState.TERMINATED)
                else:
                    self._enter_completed_state()
                    
                if self.callback:
                    await self.callback(response)
        
        elif event.type == EventType.TIMER:
            # PJSIP: In PROCEEDING state, non-INVITE transactions still retransmit request 
            # if unreliable transport is used until final response.
            if self.request.method != "INVITE":
                await self._handle_retransmit_timer(event)

    def _enter_completed_state(self) -> None:
        """Helper to transition to COMPLETED and schedule cleanup timers."""
        self.set_state(TransactionState.COMPLETED)
        self._timer_service.cancel(f"{self.key}_timer_a")
        self._timer_service.cancel(f"{self.key}_timer_b")
        
        # Schedule Timer D (INVITE) or Timer K (non-INVITE)
        wait_ms = T4 if self.request.method != "INVITE" else 32000 # Timer D default 32s
        self._timer_service.schedule(f"{self.key}_timer_cleanup", wait_ms, self._on_timer_cleanup)

    async def _on_state_completed(self, event: SipEvent) -> None:
        """
        COMPLETED state - waiting for retransmitted responses to be absorbed.
        """
        if event.type == EventType.TIMER and event.timer_id == f"{self.key}_timer_cleanup":
            self.set_state(TransactionState.TERMINATED)

    def _on_timer_cleanup(self) -> None:
        """Cleanup timer fired (Timer D or K)."""
        # Inject event into process_event in advanced implementation
        logger.info("uac_cleanup_timer_fired", key=self.key)

    async def _handle_retransmit_timer(self, event: SipEvent) -> None:
        """Common logic for Timer A retransmission."""
        if event.timer_id == f"{self.key}_timer_a":
            self._retransmit_interval = min(self._retransmit_interval * 2, T2)
            logger.info("uac_retransmitting", key=self.key, next_interval=self._retransmit_interval)
            await self._transport.send(self._remote_addr, str(self.request).encode())
            self._timer_service.schedule(
                f"{self.key}_timer_a", 
                self._retransmit_interval, 
                self._on_timer_a
            )
