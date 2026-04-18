import asyncio
import structlog
from jksip.sip.endpoint import SipEndpoint
from jksip.core.transport import SipTransport
from jksip.sip.media.sdp import SdpSession, SdpOrigin, SdpMedia
from jksip.sip.parser import SipParser

# Configure logging
structlog.configure()

class MockTransport(SipTransport):
    def __init__(self):
        super().__init__(("127.0.0.1", 5060))
        self.sent_data = []

    async def send(self, remote_addr: tuple[str, int], data: bytes) -> None:
        self.sent_data.append(data)
        print(f"\n--- SENT TO {remote_addr} ---\n{data.decode()}\n-------------------------")

    def close(self): pass

async def smoke_test():
    print("Initializing jksip Smoke Test...")
    
    # 1. Setup Endpoint
    endpoint = SipEndpoint()
    transport = MockTransport()
    endpoint.add_transport(transport)
    
    # 2. Create Invite Session
    # local_uri = "sip:bob@127.0.0.1"
    # remote_uri = "sip:alice@127.0.0.1"
    inv_session = endpoint.create_uac_invite("sip:bob@127.0.0.1", "sip:alice@192.168.1.100")
    
    # 3. Create a simple SDP
    origin = SdpOrigin(session_id=123, session_version=456, address="127.0.0.1")
    sdp = SdpSession(origin=origin, address="127.0.0.1")
    sdp.media.append(SdpMedia(media_type="audio", port=10000, formats=["0", "101"]))
    
    # 4. Initiate Call
    print("Initiating call...")
    await inv_session.initiate_call(("192.168.1.100", 5060), local_sdp=sdp)
    
    # 5. Verify results
    assert len(transport.sent_data) > 0
    raw_invite = transport.sent_data[0]
    
    # Parse back to verify
    parsed_invite = SipParser.parse(raw_invite)
    assert parsed_invite.method == "INVITE"
    assert parsed_invite.get_header("Content-Type") == "application/sdp"
    assert b"m=audio 10000 RTP/AVP 0 101" in raw_invite
    
    print("\nSmoke Test PASSED: INVITE with SDP successfully generated and 'sent'.")

if __name__ == "__main__":
    asyncio.run(smoke_test())
