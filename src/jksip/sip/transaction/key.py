from typing import Optional
from ..message import SipMessage, SipRequest, SipResponse

class TransactionKey:
    """
    Utility to generate unique keys for SIP transactions.
    Follows RFC 3261 rules (z9hG4bK branch matching).
    """

    @staticmethod
    def generate_uac_key(request: SipRequest) -> str:
        """
        Equivalent to create_tsx_key_3261 in pjsip/sip_transaction.c
        """
        branch = request.get_header_param("Via", "branch")
        if not branch or not branch.startswith("z9hG4bK"):
            # Fallback to legacy RFC 2543 (Simplified)
            return f"c${request.method}${id(request)}"
            
        # PJSIP Rule: Add method except when INVITE or ACK
        key = "c$"
        if request.method not in ("INVITE", "ACK"):
            key += f"{request.method}$"
        
        key += branch
        return key

    @staticmethod
    def generate_uas_key(request: SipRequest) -> str:
        """
        Equivalent to create_tsx_key_3261 in pjsip/sip_transaction.c
        """
        branch = request.get_header_param("Via", "branch")
        if not branch or not branch.startswith("z9hG4bK"):
            return f"s${request.method}${id(request)}"
            
        key = "s$"
        if request.method not in ("INVITE", "ACK"):
            key += f"{request.method}$"
        
        key += branch
        return key

    @staticmethod
    def match_response_to_uac(response: SipResponse) -> str:
        """
        Finds the matching UAC transaction key for a response.
        Parsed from CSeq method.
        """
        branch = response.get_header_param("Via", "branch")
        cseq = response.get_header("CSeq")
        method = ""
        if cseq:
            parts = cseq.split()
            if len(parts) >= 2:
                method = parts[1]
        
        if not branch or not branch.startswith("z9hG4bK"):
            return "" # Fallback logic needed for 2543
            
        key = "c$"
        if method not in ("INVITE", "ACK"):
            key += f"{method}$"
        
        key += branch
        return key
