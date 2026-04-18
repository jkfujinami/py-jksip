import structlog
from typing import Dict, Optional, Any
from .base import SipTransaction, SipEvent, EventType, TransactionState
from .key import TransactionKey
from .uac import UacTransaction
from .uas import UasTransaction
from ..message import SipMessage, SipRequest, SipResponse
from ...core.timer import TimerService
from ...core.transport import SipTransport

logger = structlog.get_logger(__name__)

class TransactionManager:
    """
    Registry for SIP Transactions.
    Equivalent to PJSIP's transaction layer module.
    
    Responsibilities:
    - Creating and registering UAC transactions.
    - Matching incoming messages to existing transactions.
    - Creating UAS transactions for new incoming requests.
    - Routing events to the correct transaction instance.
    """
    def __init__(self, timer_service: TimerService, transport: SipTransport):
        self._timer_service = timer_service
        self._transport = transport
        self._transactions: Dict[str, SipTransaction] = {}

    async def create_uac(self, request: SipRequest, 
                         remote_addr: tuple[str, int],
                         callback: Optional[callable] = None) -> UacTransaction:
        """
        Creates, registers, and initiates a UAC transaction.
        """
        key = TransactionKey.generate_uac_key(request)
        if key in self._transactions:
            logger.warning("uac_transaction_collision", key=key)
            
        tsx = UacTransaction(key, self._timer_service, self._transport, remote_addr, callback)
        self._transactions[key] = tsx
        
        # Initial stimulus: Send the request (dispatch MESSAGE event to transition from NULL)
        event = SipEvent(type=EventType.MESSAGE, message=request)
        await tsx.process_event(event)
        
        return tsx

    async def send_request(self, request: SipRequest, 
                           callback: Optional[callable] = None,
                           destination: Optional[tuple[str, int]] = None) -> None:
        """
        High-level helper to send an out-of-dialog request.
        """
        dest = destination
        if not dest:
            # Simple dest resolution from URI (Assume direct IP for tests)
            # In real PJSIP, this uses resolver and tpmgr
            import re
            # Extract host and port from sip:host:port
            # Match: sip:(user@)?(host)(:port)?
            match = re.search(r'sip:(?:[^@]+@)?([^;:]+)(?::(\d+))?', request.uri)
            if match:
                host = match.group(1)
                port = int(match.group(2)) if match.group(2) else 5060
                dest = (host, port)
            else:
                dest = ("127.0.0.1", 5060)

        await self.create_uac(request, dest, callback)

    async def on_incoming_message(self, message: SipMessage, remote_addr: tuple[str, int]) -> None:
        """
        Main entry point for messages received from the transport layer.
        Matches the message to a transaction and dispatches it.
        """
        key: Optional[str] = None
        
        if isinstance(message, SipRequest):
            key = TransactionKey.generate_uas_key(message)
        elif isinstance(message, SipResponse):
            key = TransactionKey.match_response_to_uac(message)
        
        if not key:
            logger.warning("unkeyable_message_received", type=type(message))
            return

        tsx = self._transactions.get(key)
        
        if tsx:
            # Existing transaction found (Retransmission or Response/ACK)
            event = SipEvent(type=EventType.MESSAGE, message=message)
            await tsx.process_event(event)
            
            # Cleanup if terminated
            if tsx.state == TransactionState.TERMINATED:
                self.unregister_transaction(key)
        
        elif isinstance(message, SipRequest):
            # New UAS transaction (if not ACK)
            if message.method == "ACK":
                logger.debug("ignoring_straggler_ack", key=key)
                return
                
            logger.info("creating_new_uas_transaction", key=key)
            new_uas = UasTransaction(key, self._timer_service, self._transport, remote_addr)
            self._transactions[key] = new_uas
            
            # Initial stimulus
            event = SipEvent(type=EventType.MESSAGE, message=message)
            await new_uas.process_event(event)
        
        else:
            logger.debug("no_transaction_found_for_response", key=key)

    def unregister_transaction(self, key: str) -> None:
        """Removes a transaction from the registry."""
        if key in self._transactions:
            logger.info("unregistering_transaction", key=key)
            del self._transactions[key]

    async def on_timer_event(self, key: str, timer_id: str) -> None:
        """
        Routes timer callbacks back to the specific transaction.
        """
        tsx = self._transactions.get(key)
        if tsx:
            event = SipEvent(type=EventType.TIMER, timer_id=timer_id)
            await tsx.process_event(event)
            
            # Cleanup if terminated
            if tsx.state == TransactionState.TERMINATED:
                self.unregister_transaction(key)
