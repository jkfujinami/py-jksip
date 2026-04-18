import asyncio
import structlog
from typing import Optional, List, Any
from .data import pjsua_var, PjsuaConfig, PjsuaLoggingConfig, PJSIP_TRANSPORT_UDP, PJSIP_TRANSPORT_AMPTP, PjsuaTransportConfig
from ..sip.endpoint import SipEndpoint

logger = structlog.get_logger(__name__)

def pjsua_create() -> int:
    """
    Initializes the PJSUA library.
    Equivalent to pjsua_create() in native PJSIP.
    """
    if pjsua_var.state != "NULL":
        return 0 # Already created
        
    pjsua_var.endpoint = SipEndpoint()
    pjsua_var.state = "CREATED"
    logger.info("pjsua_created")
    return 0 # PJ_SUCCESS

def pjsua_init(ua_config: Optional[PjsuaConfig] = None,
               log_config: Optional[PjsuaLoggingConfig] = None,
               media_config: Optional[Any] = None) -> int:
    """
    Initializes PJSUA with the specified configurations.
    Equivalent to pjsua_init() in native PJSIP.
    """
    if pjsua_var.state != "CREATED":
        logger.error("pjsua_init_invalid_state", state=pjsua_var.state)
        return -1 # PJ_EINVALIDSTATE
        
    if ua_config:
        pjsua_var.ua_cfg = ua_config
    if log_config:
        pjsua_var.log_cfg = log_config
        
    # Apply UA string to endpoint if specified
    if pjsua_var.ua_cfg.user_agent:
        # Note: In native PJSIP, this is copied during init
        pass

    pjsua_var.state = "INIT"
    logger.info("pjsua_initialized", ua=pjsua_var.ua_cfg.user_agent)
    return 0

async def pjsua_start_async() -> int:
    """Async version of start."""
    if pjsua_var.state != "INIT":
        return -1
        
    pjsua_var.state = "RUNNING"
    logger.info("pjsua_started")
    return 0

def pjsua_start() -> int:
    """
    Starts the PJSUA engine.
    In py-jksip, this marks the engine as running for the event loop.
    """
    # Note: Since we are in a pure asyncio environment, 
    # the actual loop is usually already running or will be started by the user.
    # We just transition state.
    pjsua_var.state = "RUNNING"
    logger.info("pjsua_started")
    return 0

def pjsua_transport_config_default(cfg: PjsuaTransportConfig) -> None:
    """Sets default values for transport configuration."""
    cfg.port = 5060
    cfg.bound_addr = ""
    cfg.public_addr = ""

async def pjsua_transport_create(tp_type: int,
                                 cfg: PjsuaTransportConfig,
                                 p_id: Optional[List[int]] = None) -> int:
    """
    Creates a SIP transport of the specified type.
    Equivalent to pjsua_transport_create() in native PJSIP.
    """
    from ..core.transport import UdpSipTransport
    from ..core.transport.amptp import AmptpTransport
    
    if pjsua_var.state == "NULL":
        return -1
        
    endpoint = pjsua_var.endpoint
    local_addr = (cfg.bound_addr if cfg.bound_addr else "0.0.0.0", cfg.port)
    
    tp_instance: Optional[Any] = None
    
    if tp_type == PJSIP_TRANSPORT_UDP:
        # Create standard UDP transport
        udp_tp = UdpSipTransport(local_addr, endpoint.on_receive_msg)
        await udp_tp.start()
        tp_instance = udp_tp
        endpoint.add_transport(tp_instance)
        endpoint.transport_manager.register_transport("udp", tp_instance)
        
    elif tp_type == PJSIP_TRANSPORT_AMPTP:
        # Create AMTP wrapped transport
        # The base UDP transport should NOT call endpoint directly. 
        # We pass a dummy async callback because AmptpTransport will override it.
        async def dummy_cb(*args): pass
        base_udp = UdpSipTransport(local_addr, dummy_cb)
        await base_udp.start()
        
        # Instantiate AMTP with endpoint callback
        tp_instance = AmptpTransport(base_udp, endpoint.on_receive_msg)
        
        endpoint.add_transport(tp_instance)
        endpoint.transport_manager.register_transport("amptp", tp_instance)
    else:
        logger.error("pjsua_transport_unsupported_type", type=tp_type)
        return -1
        
    # Register in global pjsua_var slots
    for i in range(len(pjsua_var.transports)):
        if pjsua_var.transports[i] is None:
            pjsua_var.transports[i] = tp_instance
            if p_id is not None:
                p_id[0] = i
            logger.info("pjsua_transport_created", id=i, type=tp_type)
            return 0
            
    return -1 # Out of slots

def pjsua_destroy() -> int:
    """Shutdown and cleanup."""
    pjsua_var.state = "NULL"
    pjsua_var.endpoint = None
    logger.info("pjsua_destroyed")
    return 0
