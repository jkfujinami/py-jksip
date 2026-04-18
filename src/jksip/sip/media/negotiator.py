import structlog
from enum import Enum, auto
from typing import Optional, List, Dict
from .sdp import SdpSession, SdpMedia, SdpAttr

logger = structlog.get_logger(__name__)

class SdpNegState(Enum):
    NULL = auto()
    LOCAL_OFFER = auto()
    REMOTE_OFFER = auto()
    WAIT_NEGO = auto()
    DONE = auto()

class SdpNegotiator:
    """
    SDP Offer/Answer Negotiator (RFC 3264).
    Equivalent to pjmedia_sdp_neg in PJMEDIA.
    """
    def __init__(self):
        self.state = SdpNegState.NULL
        self.active_local: Optional[SdpSession] = None
        self.active_remote: Optional[SdpSession] = None
        self.neg_local: Optional[SdpSession] = None
        self.neg_remote: Optional[SdpSession] = None

    def set_local_offer(self, sdp: SdpSession):
        """UAC: Set our local offer."""
        self.neg_local = sdp
        self.state = SdpNegState.LOCAL_OFFER
        logger.info("sdp_neg_local_offer_set")

    def set_remote_answer(self, sdp: SdpSession):
        """UAC: Set received remote answer."""
        if self.state != SdpNegState.LOCAL_OFFER:
             raise RuntimeError(f"Invalid state for remote answer: {self.state}")
        self.neg_remote = sdp
        self.state = SdpNegState.WAIT_NEGO
        logger.info("sdp_neg_remote_answer_set")

    def set_remote_offer(self, sdp: SdpSession):
        """UAS: Set received remote offer."""
        self.neg_remote = sdp
        self.state = SdpNegState.REMOTE_OFFER
        logger.info("sdp_neg_remote_offer_set")

    def set_local_answer(self, sdp: SdpSession):
        """UAS: Set our local response to the offer."""
        if self.state != SdpNegState.REMOTE_OFFER:
             raise RuntimeError(f"Invalid state for local answer: {self.state}")
        self.neg_local = sdp
        self.state = SdpNegState.WAIT_NEGO
        logger.info("sdp_neg_local_answer_set")

    def negotiate(self) -> bool:
        """
        Performs RFC 3264 negotiation between neg_local and neg_remote.
        Updates active_local and active_remote.
        """
        if self.state != SdpNegState.WAIT_NEGO:
            return False

        offer = self.neg_remote if self.neg_remote and self.neg_local else self.neg_local # logic simplified for demo
        # In RFC 3264, the "offer" is the first one sent.
        
        # Real logic: match media lines by index
        negotiated_local = self.neg_local.model_copy(deep=True)
        negotiated_remote = self.neg_remote.model_copy(deep=True)
        
        success = False
        for i in range(min(len(negotiated_local.media), len(negotiated_remote.media))):
            lm = negotiated_local.media[i]
            rm = negotiated_remote.media[i]
            
            if lm.media_type != rm.media_type:
                lm.port = 0
                rm.port = 0
                continue
            
            # Find common formats (PTs)
            common_pts = [pt for pt in lm.formats if pt in rm.formats]
            
            if not common_pts:
                # Dynamic payload matching would go here
                # For now, just deactivate if no exact match
                lm.port = 0
                rm.port = 0
                continue
                
            lm.formats = common_pts
            rm.formats = common_pts
            success = True
            
        if success:
            self.active_local = negotiated_local
            self.active_remote = negotiated_remote
            self.state = SdpNegState.DONE
            logger.info("sdp_negotiation_success")
            return True
        else:
            self.state = SdpNegState.DONE
            logger.warning("sdp_negotiation_failed_no_common_media")
            return False
