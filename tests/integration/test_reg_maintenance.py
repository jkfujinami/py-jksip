import asyncio
import pytest
import structlog
from jksip.pjsua.core import pjsua_create, pjsua_init, pjsua_start, pjsua_transport_create, pjsua_transport_config_default
from jksip.pjsua.acc import pjsua_acc_add
from jksip.pjsua.data import PjsuaAccConfig, PjsuaTransportConfig, PJSIP_TRANSPORT_UDP, AuthCred, pjsua_var
from jksip.sip.message import SipResponse
from jksip.sip.parser import SipParser
import time

logger = structlog.get_logger(__name__)

class MockRegistrar:
    def __init__(self, host="127.0.0.1", port=5061):
        self.host = host
        self.port = port
        self.transport = None
        self.requests = []
        self.auth_count = 0

    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        pass

    def datagram_received(self, data, addr):
        req = SipParser.parse(data)
        self.requests.append(req)
        logger.info("mock_rx", method=req.method, cseq=req.get_header("CSeq"))

        # Mirror CSeq and Via
        via = req.get_header("Via")
        cseq = req.get_header("CSeq")

        if self.auth_count == 0:
            # Challenge first request
            resp = SipResponse(status_code=401, reason="Unauthorized")
            resp.add_header("WWW-Authenticate", 'Digest realm="test", nonce="123", qop="auth"')
            self.auth_count += 1
        else:
            # Accept second and subsequent (refresh) requests
            resp = SipResponse(status_code=200, reason="OK")
            # Set short expires to trigger fast refresh in test
            resp.add_header("Expires", "2")
        
        resp.add_header("Via", via)
        resp.add_header("CSeq", cseq)
        resp.add_header("Content-Length", "0")
        self.transport.sendto(str(resp).encode(), addr)

def test_registration_maintenance():
    asyncio.run(_async_test_maintenance())

async def _async_test_maintenance():
    loop = asyncio.get_running_loop()
    mock = MockRegistrar()
    listen = await loop.create_datagram_endpoint(lambda: mock, local_addr=("127.0.0.1", 5061))
    transport, protocol = listen
    
    try:
        pjsua_create()
        pjsua_init()
        tp_cfg = PjsuaTransportConfig(port=5060, bound_addr="127.0.0.1")
        await pjsua_transport_create(PJSIP_TRANSPORT_UDP, tp_cfg)
        pjsua_start()

        acc_cfg = PjsuaAccConfig(
            id="sip:bob@test",
            reg_uri="sip:127.0.0.1:5061",
            register_on_acc_add=True
        )
        acc_cfg.cred_info.append(AuthCred(realm="test", username="bob", data="password"))
        acc_id = await pjsua_acc_add(acc_cfg)

        # Wait for: 
        # 1. First REGISTER (401)
        # 2. Authenticated REGISTER (200 OK, expires=2)
        # 3. Refresh REGISTER (triggered at ~1.8s)
        
        start = time.time()
        while time.time() - start < 4.0:
            if len(mock.requests) >= 3:
                break
            await asyncio.sleep(0.1)

        # Verify refresh happened
        assert len(mock.requests) >= 3, f"Expected at least 3 requests, got {len(mock.requests)}"
        
        # Check CSeq sequence
        cseqs = [req.get_header("CSeq") for req in mock.requests]
        logger.info("test_results", cseq_flow=cseqs)
        
        assert "1 REGISTER" in cseqs[0]
        assert "2 REGISTER" in cseqs[1]
        assert "3 REGISTER" in cseqs[2]

    finally:
        transport.close()
        from jksip.pjsua.core import pjsua_destroy
        pjsua_destroy()

