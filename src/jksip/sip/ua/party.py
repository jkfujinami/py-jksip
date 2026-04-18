from typing import Optional
from pydantic import BaseModel

class DialogParty(BaseModel):
    """
    Represents a participant in a SIP Dialog.
    Contains URI, tag, and CSeq sequencing information.
    Equivalent to pjsip_dlg_party in PJSIP.
    """
    uri: str
    tag: Optional[str] = None
    cseq: int = 0
    first_cseq: int = -1

    def increment_cseq(self) -> int:
        """Increments and returns the next CSeq number."""
        self.cseq += 1
        return self.cseq
