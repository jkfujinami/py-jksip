import asyncio
import structlog
from typing import Optional, Callable, Any
from .message import SipRequest, SipResponse
from ..core.timer import TimerEntry

logger = structlog.get_logger(__name__)

class SipRegc:
    """
    SIP Client Registration Session (RFC 3261).
    Equivalent to pjsip_regc in pjsip-ua.
    """
    def __init__(self, endpoint: Any, target_uri: str, aor_uri: str, 
                 callback: Optional[Callable] = None,
                 authenticator: Optional[Any] = None):
        self.endpoint = endpoint
        self.target_uri = target_uri
        self.aor_uri = aor_uri
        self.callback = callback
        self.authenticator = authenticator
        
        self.is_registered = False
        self.expires = 3600
        self.last_status = 0
        self.last_reason = ""
        self.call_id = "" 
        self.cseq = 1
        self._auth_retry_count = 0
        self._last_request: Optional[SipRequest] = None
        
        # Timer for auto-refresh
        self._refresh_timer: Optional[TimerEntry] = None
        self._auto_reg = True

    def _generate_call_id(self) -> str:
        """Generates a unique Call-ID for this registration session."""
        import uuid
        return str(uuid.uuid4())

    def create_register(self, expires: Optional[int] = None) -> SipRequest:
        """ Creates a REGISTER request based on current session state. """
        if expires is not None:
            self.expires = expires
            
        if not self.call_id:
            self.call_id = self._generate_call_id()

        req = SipRequest(method="REGISTER", uri=self.target_uri)
        
        # Add Via header - Sent-by and Branch will be populated by Endpoint/Transaction layer
        req.add_header("Via", "SIP/2.0/UDP 0.0.0.0;branch=z9hG4bKtemplate")
        
        req.add_header("To", f"<{self.aor_uri}>")
        req.add_header("From", f"<{self.aor_uri}>;tag={self._generate_tag()}")
        req.add_header("Call-ID", self.call_id)
        # Note: CSeq increment happens at the time of sending in pjsip_regc_send
        req.add_header("CSeq", f"{self.cseq} REGISTER")
        req.add_header("Contact", f"<{self.aor_uri}>") 
        req.add_header("Expires", str(self.expires))
        req.add_header("Allow", "INVITE, ACK, CANCEL, OPTIONS, BYE, REFER, NOTIFY, MESSAGE, SUBSCRIBE, INFO")
        req.add_header("Content-Length", "0")
        
        self._last_request = req
        return req

    def _generate_tag(self) -> str:
        import secrets
        return secrets.token_hex(4)

    async def process_response(self, response: SipResponse):
        """ Handles responses from the transaction layer. """
        self.last_status = response.status_code
        self.last_reason = response.reason
        
        # Handle 401/407 Challenges
        if response.status_code in (401, 407) and self.authenticator and self._auth_retry_count < 2:
            self._auth_retry_count += 1
            logger.info("regc_auth_challenge", status=response.status_code, retry=self._auth_retry_count)
            
            # Implementation of pjsip_auth_clt_reinit_req callback
            auth_req = self.authenticator.reinit_request(self._last_request, response)
            if auth_req:
                # REGISTER refresh/retry must increment CSeq (sip_reg.c:1229)
                self.cseq += 1
                auth_req.replace_header("CSeq", f"{self.cseq} REGISTER")
                self._last_request = auth_req
                
                # Re-send via endpoint
                await self.endpoint.send_request(auth_req, self.process_response)
                return

        if 200 <= response.status_code < 300:
            self.is_registered = True
            self._auth_retry_count = 0 # Reset on success
            # Extract actual expires from response (Check Header or Contact parameter)
            exp_hdr = response.get_header("Expires")
            if exp_hdr:
                self.expires = int(exp_hdr)
            else:
                # PJSIP behavior: check Contact header expires parameter
                contact = response.get_header("Contact")
                if contact and "expires=" in contact:
                    try:
                        import re
                        m = re.search(r"expires=(\d+)", contact)
                        if m: self.expires = int(m.group(1))
                    except: pass
            
            logger.info("regc_registered", aor=self.aor_uri, expires=self.expires)
            
            if self._auto_reg:
                self._schedule_refresh()
        else:
            self.is_registered = False
            logger.warn("regc_failed", aor=self.aor_uri, status=response.status_code, reason=response.reason)
            
        if self.callback:
            self.callback(self, response)

    def _schedule_refresh(self):
        """ Schedules the next registration refresh before the current one expires. """
        # PJSIP logic: refresh at 90% of expires. 
        # For small expires (tests), we must not floor at 10s.
        refresh_delay_sec = int(self.expires * 0.9)
        if self.expires > 100:
             # For larger expires, we can use a more conservative margin
             refresh_delay_sec = max(10, self.expires - 15)
            
        # Ensure at least 1 second delay
        refresh_delay_sec = max(1, refresh_delay_sec)
            
        logger.debug("regc_schedule_refresh", aor=self.aor_uri, in_seconds=refresh_delay_sec)
        
        timer_id = f"regc_refresh_{self.call_id}"
        self.endpoint.timer_service.schedule(
            entry_id=timer_id,
            delay_ms=refresh_delay_sec * 1000,
            callback=self._on_refresh_timeout
        )

    async def _on_refresh_timeout(self):
        """ Called by timer service when it's time to re-register. """
        if not self.is_registered:
            return
            
        logger.info("regc_refresh_triggered", aor=self.aor_uri)
        # REGISTER refresh must increment CSeq (sip_reg.c:1229)
        self.cseq += 1
        req = self.create_register()
        await self.endpoint.send_request(req, self.process_response)

    def destroy(self):
        """ Cleanup timers and session state. """
        if self._refresh_timer:
            self.endpoint.timer_service.cancel(self._refresh_timer)
            self._refresh_timer = None
        self.is_registered = False
