import asyncio
import structlog
from .data import pjsua_var, PjsuaAccount, PjsuaAccConfig
from ..sip.regc import SipRegc

logger = structlog.get_logger(__name__)

async def pjsua_acc_add(acc_cfg: PjsuaAccConfig, is_default: bool = False) -> int:
    """
    Adds a new account to PJSUA and initiates registration if requested.
    Equivalent to pjsua_acc_add() in pjsua_acc.c.
    """
    # Find free slot
    acc_id = -1
    for i in range(len(pjsua_var.accounts)):
        if pjsua_var.accounts[i] is None:
            acc_id = i
            break
            
    if acc_id == -1:
        logger.error("pjsua_acc_add_no_slot")
        return -1
        
    acc = PjsuaAccount(index=acc_id, cfg=acc_cfg)
    pjsua_var.accounts[acc_id] = acc
    
    if is_default:
        pjsua_var.default_acc = acc_id
        
    # Initialize registration if requested
    if acc_cfg.register_on_acc_add and acc_cfg.reg_uri:
        # 1. Create SOLID DigestAuthenticator for this account
        from ..sip.auth.digest import DigestAuthenticator
        authenticator = DigestAuthenticator(acc_cfg.cred_info)
        
        # 2. Create and initialize SipRegc
        acc.regc = SipRegc(
            endpoint=pjsua_var.endpoint,
            target_uri=acc_cfg.reg_uri,
            aor_uri=acc_cfg.id,
            callback=pjsua_var.on_reg_state,
            authenticator=authenticator
        )
        
        # 3. Create and send initial REGISTER
        reg_req = acc.regc.create_register()
        
        # Note: In PJSUA, the registration is sent asynchronously via the endpoint.
        if pjsua_var.endpoint:
            await pjsua_var.endpoint.send_request(reg_req, acc.regc.process_response)
            logger.info("pjsua_acc_auto_register_sent", acc_id=acc_id, uri=acc_cfg.id)

    logger.info("pjsua_acc_added", acc_id=acc_id, uri=acc_cfg.id)
    return acc_id

def pjsua_acc_get_count() -> int:
    return sum(1 for a in pjsua_var.accounts if a is not None)

def pjsua_acc_is_valid(acc_id: int) -> bool:
    if 0 <= acc_id < len(pjsua_var.accounts):
        return pjsua_var.accounts[acc_id] is not None
    return False
