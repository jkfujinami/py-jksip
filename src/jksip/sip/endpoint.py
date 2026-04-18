import structlog
import asyncio
from typing import Optional, List, Any, Dict
from ..core.timer import TimerService
from ..core.transport import SipTransport
from .transaction.manager import TransactionManager
from .ua.manager import DialogManager
from .ua.invite import InviteSession
from .ua.dialog import SipDialog
from .parser import SipParser
from .message import SipRequest, SipResponse

logger = structlog.get_logger(__name__)

class SipEndpoint:
    """
    The central orchestration class for the jksip library.
    Equivalent to pjsip_endpoint in PJSIP.
    
    Coordinates transport, transactions, dialogs, and media.
    """
    def __init__(self, timer_service: Optional[TimerService] = None):
        from ..core.transport import TransportManager
        
        self.timer_service = timer_service or TimerService()
        self.transport_manager = TransportManager()
        self.transports: List[SipTransport] = []
        self.tsx_manager: Optional[TransactionManager] = None
        self.dialog_manager = DialogManager()
        self.is_running = False

    def add_transport(self, transport: SipTransport):
        """Adds a transport (e.g., UDP listener) to the endpoint."""
        self.transport_manager.register_transport("unknown", transport) # Register in manager
        self.transports.append(transport)
        # For our port, we use a single transaction manager tied to the primary transport.
        # In a full PJSIP port, the Tpmgr would handle multi-transport routing.
        if self.tsx_manager is None:
            self.tsx_manager = TransactionManager(self.timer_service, transport)
        
        logger.info("transport_added", local_addr=transport.local_addr)

    async def run(self):
        """Starts the endpoint event loop."""
        self.is_running = True
        logger.info("endpoint_started")
        while self.is_running:
            # Main event loop (Timer processing is async in our core.timer)
            await asyncio.sleep(1)

    async def on_incoming_data(self, data: bytes, remote_addr: tuple[str, int]):
        """
        Entry point for raw data from transport.
        Parses the message and dispatches it through the stack.
        """
        try:
            message = SipParser.parse(data)
        except Exception as e:
            logger.error("sip_parse_failed", error=str(e), remote_addr=remote_addr)
            return

        # 1. Dispatch to Transaction Manager
        if self.tsx_manager:
            await self.tsx_manager.on_incoming_message(message, remote_addr)
        
        # 2. Dispatch to Dialog Manager for mid-dialog routing
        dlg = self.dialog_manager.match_message(message)
        if dlg:
            if isinstance(message, SipResponse):
                dlg.on_response(message)
            # Future: add request handling to SipDialog
        
        logger.debug("message_dispatched", type=type(message), call_id=message.get_header("Call-ID"))

    def create_uac_invite(self, local_uri: str, remote_uri: str) -> InviteSession:
        """
        High-level API to start a new INVITE session.
        """
        if not self.tsx_manager:
            raise RuntimeError("No transport/transaction manager initialized")
            
        dlg = SipDialog.create_uac(self.tsx_manager, local_uri, remote_uri)
        self.dialog_manager.register_dialog(dlg)
        
        inv_session = InviteSession(dlg)
        return inv_session

    async def send_request(self, request: SipRequest, 
                           callback: Optional[callable] = None,
                           transport: Optional[SipTransport] = None) -> None:
        """
        Sends an out-of-dialog SIP request.
        Utilizes TransactionManager to handle retransmissions.
        """
        if not self.tsx_manager:
             # Try to use the first available transport if not strictly tied
             if self.transports:
                 self.add_transport(self.transports[0])
             else:
                raise RuntimeError("No transport available to send request")

        logger.info("endpoint_send_request", method=request.method, uri=request.uri)
        
        # Determine the transport for address population
        tp = transport or (self.tsx_manager._transport if self.tsx_manager else None)
        if tp:
            # Update Via header with actual sent-by address
            ip, port = tp.local_addr
            branch = request.get_header_param("Via", "branch") or f"z9hG4bK{id(request)}"
            # Update the first Via header (sent-by part)
            # Format: Via: SIP/2.0/UDP {ip}:{port};branch={branch}
            # Note: We assume UDP for now, could be dynamic based on tp.info or type
            request.replace_header("Via", f"SIP/2.0/UDP {ip}:{port};branch={branch}")
            logger.debug("via_header_updated", local_addr=f"{ip}:{port}", branch=branch)

        # In a real PJSIP, we would find the transport based on the request URI.
        # For our port, we use the assigned tsx_manager.
        await self.tsx_manager.send_request(request, callback)

    async def on_receive_msg(self, data: bytes, addr: tuple[str, int], transport: Any):
        """
        Callback used by transports when raw data is received.
        Wraps on_incoming_data with the correct context.
        """
        # Note: Unwrapping is now handled internally by transport decorators (e.g., AmptpTransport)
        # to ensure correct sequence and atomicity.
        await self.on_incoming_data(data, addr)

    def stop(self):
         self.is_running = False
         logger.info("endpoint_stopped")
