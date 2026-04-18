import structlog
from enum import Enum, auto
from typing import Optional, Callable, Dict, Any
from .dialog import SipDialog, DialogState
from ..message import SipRequest, SipResponse
from ..media.sdp import SdpSession
from ..media.parser import SdpParser
from ..media.negotiator import SdpNegotiator

logger = structlog.get_logger(__name__)

class InviteState(Enum):
    """
    SIP INVITE Session States (RFC 3261).
    Equivalent to pjsip_inv_state.
    """
    NULL = auto()
    CALLING = auto()
    INCOMING = auto()
    EARLY = auto()
    CONNECTING = auto()
    CONFIRMED = auto()
    DISCONNECTED = auto()

class InviteSession:
    """
    High-level INVITE session management.
    Handles the state machine for a SIP call and manages SDP negotiation.
    """
    def __init__(self, dialog: SipDialog, negotiator: Optional[SdpNegotiator] = None):
        self.dialog = dialog
        self.state = InviteState.NULL
        self.negotiator = negotiator or SdpNegotiator()
        self.on_state_changed: Optional[Callable[["InviteSession", InviteState], None]] = None
        self._invite_tsx = None

    def set_state(self, new_state: InviteState):
        """Transition state and notify."""
        if self.state != new_state:
            logger.info("inv_state_changed", old=self.state, new=new_state, call_id=self.dialog.call_id)
            self.state = new_state
            if self.on_state_changed:
                self.on_state_changed(self, new_state)

    async def initiate_call(self, remote_addr: tuple[str, int], local_sdp: Optional[SdpSession] = None):
        """
        Starts an outgoing call (UAC).
        """
        if self.state != InviteState.NULL:
            raise RuntimeError("Session already initialized")

        # 1. Create the INVITE request via Dialog
        invite_req = self.dialog.create_request("INVITE")
        
        # 2. Add SDP if provided
        if local_sdp:
            self.negotiator.set_local_offer(local_sdp)
            sdp_str = str(local_sdp)
            invite_req.body = sdp_str.encode()
            invite_req.add_header("Content-Type", "application/sdp")
            invite_req.add_header("Content-Length", str(len(invite_req.body)))
        
        # 3. Update state to CALLING
        self.set_state(InviteState.CALLING)
        
        # 4. Store remote addr for future ACK/BYE
        self._remote_addr = remote_addr
        
        # 5. Send via Dialog's Transaction Manager
        self._invite_tsx = await self.dialog.send_request(invite_req, remote_addr)
        return self._invite_tsx

    async def handle_response(self, response: SipResponse):
        """
        Processes an incoming response related to the INVITE.
        """
        # Update underlying dialog state
        self.dialog.on_response(response)
        
        # Process SDP in response if any
        content_type = response.get_header("Content-Type")
        if content_type == "application/sdp" and response.body:
             try:
                 remote_sdp = SdpParser.parse(response.body.decode())
                 if self.negotiator.state == self.negotiator.state.LOCAL_OFFER:
                     self.negotiator.set_remote_answer(remote_sdp)
                     self.negotiator.negotiate()
             except Exception as e:
                 logger.error("sdp_parse_failed", error=str(e))
        
        status = response.status_code
        
        if self.state == InviteState.CALLING:
            if 101 <= status <= 199:
                self.set_state(InviteState.EARLY)
            elif 200 <= status <= 299:
                await self._on_call_answered(response)
            elif status >= 300:
                self.set_state(InviteState.DISCONNECTED)
                
        elif self.state == InviteState.EARLY:
            if 200 <= status <= 299:
                await self._on_call_answered(response)
            elif status >= 300:
                self.set_state(InviteState.DISCONNECTED)

    async def _on_call_answered(self, response: SipResponse):
        """
        Handles 2xx response to INVITE.
        Moves to CONNECTING and sends ACK.
        """
        self.set_state(InviteState.CONNECTING)
        
        # Send ACK - RFC 3261: ACK for 2xx is a new transaction but same dialog
        ack_req = self.dialog.create_request("ACK")
        # In a real scenario, we should use the Contact header from the 200 OK
        # for the Request-URI and target address.
        await self.dialog.send_request(ack_req, self._remote_addr)
        
        self.set_state(InviteState.CONFIRMED)

    async def terminate(self):
        """
        Ends the session. Sends BYE or CANCEL.
        """
        if self.state == InviteState.CALLING:
            # Send CANCEL
            cancel_req = self.dialog.create_request("CANCEL")
            await self.dialog.send_request(cancel_req, self.dialog.tsx_manager._transport.local_addr) # Placeholder
            self.set_state(InviteState.DISCONNECTED)
            
        elif self.state in [InviteState.EARLY, InviteState.CONNECTING, InviteState.CONFIRMED]:
            # Send BYE
            bye_req = self.dialog.create_request("BYE")
            await self.dialog.send_request(bye_req, self.dialog.tsx_manager._transport.local_addr) # Placeholder
            self.set_state(InviteState.DISCONNECTED)
