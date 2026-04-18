import asyncio
import pytest
import structlog
from jksip.pjsua.core import pjsua_create, pjsua_init, pjsua_start, pjsua_transport_create, pjsua_transport_config_default
from jksip.pjsua.acc import pjsua_acc_add
from jksip.pjsua.data import PjsuaAccConfig, PjsuaTransportConfig, PJSIP_TRANSPORT_AMPTP, AuthCred, pjsua_var
from jksip.sip.message import SipResponse
from jksip.sip.parser import SipParser
from typing import Dict, Any

logger = structlog.get_logger(__name__)

class MockAmptpRegistrar:
    """
    Simulates a SIP Registrar that uses AMTP transport.
    """
    def __init__(self, host="127.0.0.1", port=5061):
        self.host = host
        self.port = port
        self.transport = None
        self.received_requests = []
        self._auth_done = False

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        pass

    def datagram_received(self, data, addr):
        # 1. Unwrap AMTP (5 bytes: Magic 1 + Seq 4)
        import struct
        if len(data) < 5: return
        magic = data[0]
        seq = struct.unpack("<I", data[1:5])[0]
        payload = data[5:]
        
        req = SipParser.parse(payload)
        self.received_requests.append(req)
        logger.info("mock_server_rx", method=req.method, seq=seq)

        # 2. Respond
        if not self._auth_done:
            # Send 401 Unauthorized with Digest challenge
            resp = SipResponse(status_code=401, reason="Unauthorized")
            # Mirror Via and CSeq for transaction matching
            via = req.get_header("Via")
            if via: resp.add_header("Via", via)
            cseq = req.get_header("CSeq")
            if cseq: resp.add_header("CSeq", cseq)
            
            resp.add_header("WWW-Authenticate", 'Digest realm="jksip", nonce="xyz123", qop="auth", algorithm="MD5"')
            resp.add_header("Content-Length", "0")
            self._send_amptp(str(resp).encode(), addr)
            self._auth_done = True
        else:
            # Check for Authorization header
            auth_hdr = req.get_header("Authorization")
            if auth_hdr and 'response="' in auth_hdr:
                resp = SipResponse(status_code=200, reason="OK")
                # Mirror Via and CSeq
                via = req.get_header("Via")
                if via: resp.add_header("Via", via)
                cseq = req.get_header("CSeq")
                if cseq: resp.add_header("CSeq", cseq)
                
                resp.add_header("Expires", "3600")
                resp.add_header("Content-Length", "0")
                self._send_amptp(str(resp).encode(), addr)
            else:
                resp = SipResponse(status_code=403, reason="Forbidden")
                via = req.get_header("Via")
                if via:
                    resp.add_header("Via", via)
                self._send_amptp(str(resp).encode(), addr)

    def _send_amptp(self, payload, addr):
        import struct
        # Wrap in AMTP (5 bytes: Magic 1 + Seq 4, Little-Endian)
        header = b'\x01' + struct.pack("<I", 101)
        self.transport.sendto(header + payload, addr)

def test_amptp_authenticated_registration():
    """
    Synchronous wrapper for the async test to avoid pytest-asyncio dependency issues.
    """
    asyncio.run(_async_test_amptp_authenticated_registration())

async def _async_test_amptp_authenticated_registration():
    # Setup Mock Server
    loop = asyncio.get_running_loop()
    mock_server = MockAmptpRegistrar()
    listen = loop.create_datagram_endpoint(lambda: mock_server, local_addr=("127.0.0.1", 5061))
    transport, protocol = await listen
    
    try:
        # 1. Initialize PJSUA
        pjsua_create()
        pjsua_init()
        
        # 2. Create AMTP Transport
        tp_cfg = PjsuaTransportConfig(port=5060, bound_addr="127.0.0.1")
        await pjsua_transport_create(PJSIP_TRANSPORT_AMPTP, tp_cfg)
        
        pjsua_start()

        # 3. Add Account (initiates REGISTER)
        acc_cfg = PjsuaAccConfig(
            id="sip:alice@jksip",
            reg_uri="sip:127.0.0.1:5061;transport=amptp",
            register_on_acc_add=True
        )
        acc_cfg.cred_info.append(AuthCred(realm="jksip", username="alice", data="password"))
        
        acc_id = pjsua_acc_add(acc_cfg)
        
        # 4. Wait for registration to complete (handle 401 and then 200)
        # Using state polling for robustness
        import time
        start_time = time.time()
        timeout = 5.0
        success = False
        
        while time.time() - start_time < timeout:
            acc = pjsua_var.accounts[acc_id]
            if acc.regc.is_registered:
                success = True
                break
            await asyncio.sleep(0.1)
            
        assert success is True, "Registration timed out"
        assert len(mock_server.received_requests) >= 2
        
        # Verify first request had no auth, second had auth
        assert mock_server.received_requests[0].get_header("Authorization") is None
        assert "response=" in mock_server.received_requests[1].get_header("Authorization")

    finally:
        transport.close()
        from jksip.pjsua.core import pjsua_destroy
        pjsua_destroy()
