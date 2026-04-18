import structlog
from typing import Optional, Any
from .data import pjsua_var, PjsuaCall
from ..sip.ua.invite import InviteSession
from ..sip.ua.dialog import SipDialog

logger = structlog.get_logger(__name__)

def pjsua_call_make_call2(acc_id: int, 
                         dst_uri: str, 
                         call_setting: Optional[Any] = None,
                         user_data: Any = None,
                         msg_data: Any = None) -> int:
    """
    Initiates an outgoing call.
    Equivalent to pjsua_call_make_call2() in pjsua_call.c.
    
    Returns the call ID (index).
    """
    if pjsua_var.endpoint is None:
        logger.error("pjsua_call_not_initialized")
        return -1

    # Verify account
    acc = pjsua_var.accounts[acc_id]
    if acc is None:
        logger.error("pjsua_invalid_account", acc_id=acc_id)
        return -1

    # Find free slot
    call_id = -1
    for i in range(len(pjsua_var.calls)):
        if pjsua_var.calls[i] is None:
            call_id = i
            break
            
    if call_id == -1:
        logger.error("pjsua_call_no_slot")
        return -1

    # Create Dialog and Invite Session
    # Using account ID as local URI
    local_uri = acc.cfg.id
    dialog = pjsua_var.endpoint.dialog_manager.create_uac_dialog(
        local_uri=local_uri,
        remote_uri=dst_uri,
        call_id=None # Auto-generate
    )
    
    inv_session = InviteSession(
        dialog=dialog,
        transport=None, # Will be set by transaction
        transaction_mgr=pjsua_var.endpoint.transaction_manager
    )
    
    call = PjsuaCall(index=call_id, invite_sess=inv_session)
    call.user_data = user_data
    pjsua_var.calls[call_id] = call
    
    logger.info("pjsua_call_made", call_id=call_id, dst=dst_uri)
    return call_id

def pjsua_call_get_count() -> int:
    return sum(1 for c in pjsua_var.calls if c is not None)

def pjsua_call_hangup(call_id: int, status_code: int = 603) -> int:
    """Hangs up a call."""
    call = pjsua_var.calls[call_id]
    if call:
        # In real implementation, this triggers invite_sess.terminate()
        pjsua_var.calls[call_id] = None
        logger.info("pjsua_call_hungup", call_id=call_id)
        return 0
    return -1
