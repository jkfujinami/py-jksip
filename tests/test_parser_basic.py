from jksip.sip.parser import SipParser
from jksip.sip.message import SipRequest, SipResponse

def test_parse_request():
    raw_invite = (
        b"INVITE sip:user@example.com SIP/2.0\r\n"
        b"Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-123\r\n"
        b"From: <sip:alice@example.com>;tag=abc\r\n"
        b"To: <sip:bob@example.com>\r\n"
        b"Call-ID: call-001\r\n"
        b"CSeq: 1 INVITE\r\n"
        b"Content-Length: 0\r\n"
        b"\r\n"
    )
    parser = SipParser()
    msg = parser.parse(raw_invite)
    
    assert isinstance(msg, SipRequest)
    assert msg.method == "INVITE"
    assert msg.uri == "sip:user@example.com"
    assert msg.get_header("Call-ID") == "call-001"
    assert msg.get_header("From") == "<sip:alice@example.com>;tag=abc"

def test_parse_response():
    raw_ok = (
        b"SIP/2.0 200 OK\r\n"
        b"Via: SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-123\r\n"
        b"From: <sip:alice@example.com>;tag=abc\r\n"
        b"To: <sip:bob@example.com>;tag=def\r\n"
        b"Call-ID: call-001\r\n"
        b"CSeq: 1 INVITE\r\n"
        b"Content-Length: 0\r\n"
        b"\r\n"
    )
    parser = SipParser()
    msg = parser.parse(raw_ok)
    
    assert isinstance(msg, SipResponse)
    assert msg.status_code == 200
    assert msg.reason == "OK"
    assert msg.get_header("CSeq") == "1 INVITE"

if __name__ == "__main__":
    try:
        test_parse_request()
        print("Request parsing test PASSED")
        test_parse_response()
        print("Response parsing test PASSED")
    except Exception as e:
        print(f"Test FAILED: {e}")
        import traceback
        traceback.print_exc()
