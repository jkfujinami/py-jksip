import uuid
import random
import structlog
from typing import List, Optional
from enum import Enum, auto

from .party import DialogParty
from ..message import SipRequest, SipResponse
from ..transaction.manager import TransactionManager

logger = structlog.get_logger(__name__)

class DialogState(Enum):
    NULL = auto()
    EARLY = auto()
    ESTABLISHED = auto()
    TERMINATED = auto()

class SipDialog:
    """
    Manages a SIP Dialog (RFC 3261).
    Tracks Call-ID, local/remote parties, and route sets.
    """
    def __init__(
        self, 
        call_id: str, 
        local_party: DialogParty, 
        remote_party: DialogParty,
        tsx_manager: TransactionManager
    ):
        self.call_id = call_id
        self.local_party = local_party
        self.remote_party = remote_party
        self.tsx_manager = tsx_manager
        self.state = DialogState.NULL
        self.route_set: List[str] = []
        self.target_uri: str = remote_party.uri

    @classmethod
    def create_uac(
        cls, 
        tsx_manager: TransactionManager,
        local_uri: str,
        remote_uri: str,
        call_id: Optional[str] = None
    ) -> "SipDialog":
        """
        Creates a new UAC (caller) dialog.
        """
        call_id = call_id or str(uuid.uuid4())
        local_tag = str(uuid.uuid4().hex[:8])
        
        # PJSIP: Randomize local CSeq
        local_cseq = random.randint(1, 32767)
        
        local_party = DialogParty(
            uri=local_uri, 
            tag=local_tag, 
            cseq=local_cseq,
            first_cseq=local_cseq
        )
        remote_party = DialogParty(uri=remote_uri)
        
        logger.info("uac_dialog_created", call_id=call_id, local_tag=local_tag)
        return cls(call_id, local_party, remote_party, tsx_manager)

    @classmethod
    def create_uas(
        cls, 
        tsx_manager: TransactionManager,
        request: SipRequest,
        local_uri: Optional[str] = None
    ) -> "SipDialog":
        """
        Creates a new UAS (callee) dialog from an incoming INVITE/SUBSCRIBE.
        """
        call_id = request.get_header("Call-ID")
        remote_uri = request.get_header("From") # URI with tag
        remote_tag = request.get_header_param("From", "tag")
        
        # PJSIP: Remote CSeq from request
        cseq_val = request.get_header("CSeq")
        remote_cseq = int(cseq_val.split()[0]) if cseq_val else 0
        
        local_uri = local_uri or request.get_header("To")
        local_tag = str(uuid.uuid4().hex[:8])
        local_cseq = random.randint(1, 32767)
        
        local_party = DialogParty(uri=local_uri, tag=local_tag, cseq=local_cseq)
        remote_party = DialogParty(uri=remote_uri, tag=remote_tag, cseq=remote_cseq)
        
        dlg = cls(call_id, local_party, remote_party, tsx_manager)
        dlg.state = DialogState.EARLY
        
        # TODO: Process Record-Route for route_set
        
        logger.info("uas_dialog_created", call_id=call_id, local_tag=local_tag, remote_tag=remote_tag)
        return dlg

    def create_request(self, method: str) -> SipRequest:
        """
        Creates a mid-dialog request with updated CSeq and proper headers.
        """
        # Increment local CSeq
        cseq = self.local_party.increment_cseq()
        
        req = SipRequest(method=method, uri=self.target_uri)
        req.add_header("Call-ID", self.call_id)
        
        # From/To headers (with tags)
        from_val = f"<{self.local_party.uri}>;tag={self.local_party.tag}"
        to_val = f"<{self.remote_party.uri}>"
        if self.remote_party.tag:
            to_val += f";tag={self.remote_party.tag}"
            
        req.add_header("From", from_val)
        req.add_header("To", to_val)
        req.add_header("CSeq", f"{cseq} {method}")
        
        # Add Route headers if route_set exists
        for route in self.route_set:
            req.add_header("Route", route)
            
        return req

    async def send_request(self, request: SipRequest, remote_addr: tuple[str, int]):
        """
        Sends a request statefully through the transaction manager.
        """
        return await self.tsx_manager.create_uac(request, remote_addr)

    def on_response(self, response: SipResponse):
        """
        Updates dialog state based on response.
        """
        remote_tag = response.get_header_param("To", "tag")
        if remote_tag and not self.remote_party.tag:
            self.remote_party.tag = remote_tag
            logger.info("dialog_remote_tag_set", tag=remote_tag, call_id=self.call_id)

        if 101 <= response.status_code <= 199:
            self.state = DialogState.EARLY
        elif 200 <= response.status_code <= 299:
            self.state = DialogState.ESTABLISHED
        elif response.status_code >= 300:
            if self.state != DialogState.ESTABLISHED:
                self.state = DialogState.TERMINATED
