import structlog
from enum import Enum, auto
from typing import Optional, List
from .sdp import SdpSession, SdpAttribute

logger = structlog.get_logger(__name__)

class SdpNegState(Enum):
    """
    SDP Negotiator States (RFC 3264).
    Equivalent to pjmedia_sdp_neg_state.
    """
    NULL = auto()
    LOCAL_OFFER = auto()
    REMOTE_OFFER = auto()
    WAIT_NEGO = auto()
    DONE = auto()

class SdpNegotiator:
    """
    Handles SDP Offer/Answer negotiation (RFC 3264).
    Mirroring the state machine in PJSIP's sdp_neg.c.
    """
    def __init__(self):
        self.state = SdpNegState.NULL
        self.active_local: Optional[SdpSession] = None
        self.active_remote: Optional[SdpSession] = None
        self.neg_local: Optional[SdpSession] = None
        self.neg_remote: Optional[SdpSession] = None

    def set_local_offer(self, sdp: SdpSession):
        """ Equivalent to pjmedia_sdp_neg_create_w_local_offer / modify_local_offer. """
        self.neg_local = sdp
        self.state = SdpNegState.LOCAL_OFFER
        logger.debug("sdp_neg_local_offer_set", state=self.state)

    def set_remote_answer(self, sdp: SdpSession):
        """ Equivalent to pjmedia_sdp_neg_set_remote_answer. """
        if self.state != SdpNegState.LOCAL_OFFER:
            raise RuntimeError(f"Cannot set remote answer in state {self.state}")
        
        self.neg_remote = sdp
        self.state = SdpNegState.WAIT_NEGO
        logger.debug("sdp_neg_remote_answer_set", state=self.state)

    def negotiate(self):
        """ 
        Performs the actual negotiation between local and remote SDPs.
        Equivalent to pjmedia_sdp_neg_negotiate inside sdp_neg.c.
        """
        if self.state != SdpNegState.WAIT_NEGO:
            logger.warning("sdp_neg_wrong_state_for_negotiation", state=self.state)
            return

        # Basic negotiation logic (Matching media and codecs)
        # For now, we take the intersection of formats for each media stream.
        # Focus on Opus (payload 111) as requested.
        
        if not self.neg_local or not self.neg_remote:
            return

        # Simple intersection logic mirroring native sdp_neg.c's codec matching
        for i, local_m in enumerate(self.neg_local.media):
            if i >= len(self.neg_remote.media):
                local_m.port = 0 # Deactivate media according to RFC 3264
                continue
                
            remote_m = self.neg_remote.media[i]
            # Match formats
            common_fmts = [f for f in local_m.fmts if f in remote_m.fmts]
            
            if not common_fmts:
                # No common codec found. For now, we might need to fail or 
                # keep it for future resolution, but PJSIP would disable the stream.
                local_m.port = 0
            else:
                # Negotiated formats found. Update local media to reflect choice.
                # Usually we pick the first common one or follow prefer_remote_codec_order.
                local_m.fmts = [common_fmts[0]]
                # Sync connection info if needed (c= line)
                if not local_m.conn and self.neg_local.conn:
                    local_m.conn = self.neg_local.conn

        self.active_local = self.neg_local
        self.active_remote = self.neg_remote
        self.state = SdpNegState.DONE
        logger.info("sdp_negotiation_done", result="success")
