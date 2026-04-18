from typing import List, Optional, Any, Callable
from pydantic import BaseModel, Field
from ..sip.endpoint import SipEndpoint

# Constants matching native PJSIP defaults
PJSUA_MAX_ACC = 32
PJSUA_MAX_CALLS = 32
PJSUA_MAX_TRANSPORTS = 8

class PjsuaConfig(BaseModel):
    """UA configuration equivalent to pjsua_config."""
    user_agent: str = "py-jksip"
    max_calls: int = PJSUA_MAX_CALLS
    thread_cnt: int = 1

class PjsuaLoggingConfig(BaseModel):
    """Logging configuration equivalent to pjsua_logging_config."""
    msg_logging: bool = True
    level: int = 5
    console_level: int = 4
    cb: Optional[Callable[[int, str, int], None]] = None

# Transport Types (Matching pjsip_transport_type_e)
PJSIP_TRANSPORT_UNSPECIFIED = 0
PJSIP_TRANSPORT_UDP = 1
PJSIP_TRANSPORT_TCP = 2
PJSIP_TRANSPORT_TLS = 3
PJSIP_TRANSPORT_AMPTP = 128 # Proprietary Andromeda type

class PjsuaTransportConfig(BaseModel):
    """Transport configuration equivalent to pjsua_transport_config."""
    port: int = 0
    bound_addr: str = ""
    public_addr: str = ""
    # Add other fields as needed for Andromeda

class AuthCred(BaseModel):
    """Authentication credentials equivalent to pjsip_cred_info."""
    realm: str = "*"
    username: str = ""
    data_type: int = 0 # 0 for plain text password
    data: str = "" # password

class PjsuaAccConfig(BaseModel):
    """Account configuration equivalent to pjsua_acc_config."""
    id: str = "" # e.g. "sip:alice@example.com"
    reg_uri: str = "" # e.g. "sip:example.com"
    register_on_acc_add: bool = True
    publish_enabled: bool = False
    
    # Credentials and Proxies
    cred_count: int = 0
    cred_info: List[AuthCred] = Field(default_factory=list)
    proxy_count: int = 0
    proxy: List[str] = Field(default_factory=list)

class PjsuaAccount:
    """
    Representation of an account in the PJSUA layer.
    Equivalent to pjsua_acc in pjsua_internal.h.
    """
    def __init__(self, index: int, cfg: PjsuaAccConfig):
        self.index = index
        self.cfg = cfg
        self.is_valid = True
        self.regc: Optional[Any] = None # Will be SipRegc
        self.status: int = 0
        self.status_text: str = ""

class PjsuaCall:
    """
    Representation of a call in the PJSUA layer.
    Equivalent to pjsua_call in pjsua_internal.h.
    """
    def __init__(self, index: int, invite_sess: Any):
        self.index = index
        self.invite_sess = invite_sess
        self.user_data: Any = None
        self.last_status: int = 0
        self.last_text: str = ""

class PjsuaData:
    """
    Global singleton state holder for the PJSUA layer.
    Equivalent to the 'pjsua_var' variable in pjsua_core.c.
    """
    def __init__(self):
        self.state: str = "NULL"
        self.endpoint: Optional[SipEndpoint] = None
        
        # Registries using fixed-size slots for C-compatible indexing
        self.accounts: List[Optional[PjsuaAccount]] = [None] * PJSUA_MAX_ACC
        self.calls: List[Optional[PjsuaCall]] = [None] * PJSUA_MAX_CALLS
        self.transports: List[Optional[Any]] = [None] * PJSUA_MAX_TRANSPORTS
        
        # Current configs
        self.ua_cfg: PjsuaConfig = PjsuaConfig()
        self.log_cfg: PjsuaLoggingConfig = PjsuaLoggingConfig()
        
        # Callbacks (Andromeda relies heavily on these)
        self.on_call_state: Optional[Callable] = None
        self.on_incoming_call: Optional[Callable] = None
        self.on_reg_state: Optional[Callable] = None

# The global singleton instance
pjsua_var = PjsuaData()
