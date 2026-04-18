import structlog
from typing import Optional
from .negotiator import SdpNegotiator
from .sdp import SdpSession

logger = structlog.get_logger(__name__)

class MediaSession:
    """
    High-level controller for media negotiation within a SIP session.
    Equivalent to pjsua_call_media in PJSUA or part of pjsip_inv_session.
    
    Ties together the SDP negotiator and the actual media streams (RTP/RTCP).
    """
    def __init__(self, negotiator: Optional[SdpNegotiator] = None):
        self.negotiator = negotiator or SdpNegotiator()
        self.is_active = False

    def on_offer_received(self, offer: SdpSession):
        """UAS: Set received offer from remote."""
        self.negotiator.set_remote_offer(offer)

    def on_answer_received(self, answer: SdpSession):
        """UAC: Set received answer from remote."""
        self.negotiator.set_remote_answer(answer)
        self.negotiator.negotiate()

    def create_offer(self, local_sdp: SdpSession) -> SdpSession:
        """UAC: Set local offer and return for sending."""
        self.negotiator.set_local_offer(local_sdp)
        return local_sdp

    def create_answer(self, local_sdp: SdpSession) -> SdpSession:
        """UAS: Set local answer and return for sending."""
        self.negotiator.set_local_answer(local_sdp)
        self.negotiator.negotiate()
        return local_sdp

    @property
    def active_sdp(self) -> Optional[SdpSession]:
        return self.negotiator.active_local
