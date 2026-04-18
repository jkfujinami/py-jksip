import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from jksip.sip.message import SipRequest, SipResponse
from jksip.sip.transaction.manager import TransactionManager
from jksip.sip.transaction.base import TransactionState
from jksip.core.timer import TimerService
from jksip.core.transport import SipTransport

class MockTransport(SipTransport):
    def __init__(self):
        super().__init__(("127.0.0.1", 5060))
        self.send_mock = AsyncMock()
    async def send(self, remote_addr: tuple[str, int], data: bytes) -> None:
        await self.send_mock(remote_addr, data)
    def close(self): pass

async def test_uac_flow():
    # Setup
    timer_service = TimerService()
    transport = MockTransport()
    manager = TransactionManager(timer_service, transport)
    
    # 1. Create a Request
    req = SipRequest(method="INVITE", uri="sip:alice@example.com")
    req.add_header("Via", "SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-uac123")
    req.add_header("CSeq", "1 INVITE")
    
    # 2. Start UAC Transaction
    remote_addr = ("192.168.1.1", 5060)
    uac = await manager.create_uac(req, remote_addr)
    
    assert uac.state == TransactionState.CALLING
    transport.send_mock.assert_called_once()
    print(f"UAC Created in state: {uac.state}")
    
    # 3. Simulate receiving a 180 Ringing
    res_180 = SipResponse(status_code=180, reason="Ringing")
    res_180.add_header("Via", "SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-uac123")
    res_180.add_header("CSeq", "1 INVITE")
    
    await manager.on_incoming_message(res_180, remote_addr)
    assert uac.state == TransactionState.PROCEEDING
    print(f"UAC moved to: {uac.state} after 180")
    
    # 4. Simulate 200 OK
    res_200 = SipResponse(status_code=200, reason="OK")
    res_200.add_header("Via", "SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-uac123")
    res_200.add_header("CSeq", "1 INVITE")
    
    await manager.on_incoming_message(res_200, remote_addr)
    # INVITE 2xx transitions to TERMINATED in our model
    assert uac.state == TransactionState.TERMINATED
    print(f"UAC moved to: {uac.state} after 200 OK")

if __name__ == "__main__":
    asyncio.run(test_uac_flow())
    print("Transaction Integration Test PASSED")
