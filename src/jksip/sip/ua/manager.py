import structlog
from typing import Dict, List, Optional
from .dialog import SipDialog
from ..message import SipMessage, SipRequest, SipResponse

logger = structlog.get_logger(__name__)

class DialogManager:
    """
    Registry for SIP Dialogs.
    Equivalent to PJSIP's UA layer (mod-ua).
    
    Manages dialog sets (grouped by Call-ID and local-tag)
    to handle forked responses and route mid-dialog messages.
    """
    def __init__(self):
        # Map local_tag -> List of Dialogs (Dialog Set)
        self._dialog_sets: Dict[str, List[SipDialog]] = {}

    def register_dialog(self, dialog: SipDialog):
        """Adds a dialog to the registry."""
        local_tag = dialog.local_party.tag
        if not local_tag:
            logger.warning("register_dialog_failed_missing_local_tag", call_id=dialog.call_id)
            return

        if local_tag not in self._dialog_sets:
            self._dialog_sets[local_tag] = []
        
        self._dialog_sets[local_tag].append(dialog)
        logger.info("dialog_registered", call_id=dialog.call_id, local_tag=local_tag)

    def find_dialog(
        self, 
        call_id: str, 
        local_tag: str, 
        remote_tag: Optional[str] = None
    ) -> Optional[SipDialog]:
        """
        Finds a dialog based on the RFC 3261 triplet.
        Matching logic:
        1. Find dialog set by local_tag.
        2. Filter by Call-ID.
        3. Match remote_tag.
        """
        dlg_set = self._dialog_sets.get(local_tag)
        if not dlg_set:
            return None

        for dlg in dlg_set:
            if dlg.call_id == call_id:
                # remote_tag matching
                if not remote_tag:
                    # Initial request or early dialog with no remote tag yet
                    return dlg
                if dlg.remote_party.tag == remote_tag:
                    return dlg
        
        return None

    def match_message(self, message: SipMessage) -> Optional[SipDialog]:
        """
        Analyzes a message to find a matching dialog.
        """
        call_id = message.get_header("Call-ID")
        if not call_id:
            return None

        if isinstance(message, SipRequest):
            # Incoming Request: To tag is our local-tag, From tag is remote-tag
            local_tag = message.get_header_param("To", "tag")
            remote_tag = message.get_header_param("From", "tag")
        else:
            # Incoming Response: From tag is our local-tag, To tag is remote-tag
            local_tag = message.get_header_param("From", "tag")
            remote_tag = message.get_header_param("To", "tag")

        if not local_tag:
            # New dialog requests (INVITE/SUBSCRIBE) don't have a To tag yet.
            return None

        return self.find_dialog(call_id, local_tag, remote_tag)

    def unregister_dialog(self, dialog: SipDialog):
        """Removes a dialog from the registry."""
        local_tag = dialog.local_party.tag
        if local_tag in self._dialog_sets:
            if dialog in self._dialog_sets[local_tag]:
                self._dialog_sets[local_tag].remove(dialog)
                if not self._dialog_sets[local_tag]:
                    del self._dialog_sets[local_tag]
                logger.info("dialog_unregistered", call_id=dialog.call_id)
