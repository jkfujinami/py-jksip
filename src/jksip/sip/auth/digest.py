import hashlib
import structlog
from typing import Optional, Any
from abc import ABC, abstractmethod
from ..message import SipRequest, SipResponse

logger = structlog.get_logger(__name__)

def md5_hex(data: str) -> str:
    """Calculates MD5 hash and returns hex string."""
    return hashlib.md5(data.encode('utf-8')).hexdigest()

class SipAuthenticator(ABC):
    """
    Abstract interface for SIP Authentication handlers.
    Following the Open/Closed Principle.
    """
    @abstractmethod
    def reinit_request(self, old_request: SipRequest, response: SipResponse) -> Optional[SipRequest]:
        """ Reinitializes a request with authentication credentials based on a challenge. """
        pass

class DigestAuthenticator(SipAuthenticator):
    """
    Standard HTTP Digest Authentication for SIP.
    Mirroring PJSIP's pjsip_auth_clt_reinit_req logic.
    """
    def __init__(self, cred_info: list):
        self.cred_info = cred_info # List of AuthCred
        self._nc = 0

    def _find_credential(self, realm: str) -> Optional[Any]:
        """Finds the best matching credential for the given realm."""
        wildcard_cred = None
        for cred in self.cred_info:
            if cred.realm == realm:
                return cred
            if cred.realm == "*":
                wildcard_cred = cred
        return wildcard_cred

    def reinit_request(self, old_request: SipRequest, response: SipResponse) -> Optional[SipRequest]:
        """
        Implementation of pjsip_auth_clt_reinit_req.
        Clones the old request, adds Authorization header, and clears Via branch.
        """
        auth_params = response.get_auth_params("WWW-Authenticate")
        if not auth_params:
            auth_params = response.get_auth_params("Proxy-Authenticate")
            
        if not auth_params:
            logger.error("auth_no_challenge_found")
            return None

        # 1. Create a clone of the original request
        new_req = old_request.copy()
        
        # 2. Find credential to be used for the challenge
        realm = auth_params.get("realm", "*")
        cred = self._find_credential(realm)
        if not cred:
            logger.warn("auth_no_cred_found", realm=realm)
            return None

        # 3. Reset Via branch (PJSIP behavior: pjsip_auth_clt_reinit_req clears branch)
        new_req.replace_header_param("Via", "branch", None)

        # 4. Calculate Digest
        nonce = auth_params.get("nonce", "")
        qop = auth_params.get("qop")
        algorithm = auth_params.get("algorithm", "MD5")
        uri = new_req.uri

        ha1 = md5_hex(f"{cred.username}:{realm}:{cred.data}")
        ha2 = md5_hex(f"{new_req.method}:{uri}")
        
        auth_header_val = f'Digest username="{cred.username}", realm="{realm}", nonce="{nonce}", uri="{uri}"'
        
        if qop == "auth":
            self._nc += 1
            nc_str = f"{self._nc:08x}"
            cnonce = "0a4f113b" # Static placeholder for testing, should be random in production
            response_hash = md5_hex(f"{ha1}:{nonce}:{nc_str}:{cnonce}:auth:{ha2}")
            auth_header_val += f', qop=auth, nc={nc_str}, cnonce="{cnonce}", response="{response_hash}"'
        else:
            response_hash = md5_hex(f"{ha1}:{nonce}:{ha2}")
            auth_header_val += f', response="{response_hash}"'

        if algorithm:
            auth_header_val += f', algorithm={algorithm}'

        # 4. Add the Authorization header
        hdr_name = "Authorization" if response.status_code == 401 else "Proxy-Authorization"
        new_req.replace_header(hdr_name, auth_header_val)
        
        return new_req
