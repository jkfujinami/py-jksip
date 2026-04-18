from jksip.sip.message import SipRequest, SipResponse, SipHeader
from jksip.sip.transaction.key import TransactionKey

def test_key_matching():
    # 1. Create a Request
    req = SipRequest(method="INVITE", uri="sip:bob@example.com")
    req.add_header("Via", "SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-abc123")
    req.add_header("CSeq", "1 INVITE")
    
    # Generate UAC key for the outgoing request
    uac_key = TransactionKey.generate_uac_key(req)
    # Generate UAS key for the incoming request
    uas_key = TransactionKey.generate_uas_key(req)
    
    print(f"UAC Key: {uac_key}")
    print(f"UAS Key: {uas_key}")
    
    assert uac_key == "c$INVITE$z9hG4bK-abc123"
    assert uas_key == "s$INVITE$z9hG4bK-abc123"
    
    # 2. Create a Response matching that request
    res = SipResponse(status_code=200, reason="OK")
    res.add_header("Via", "SIP/2.0/UDP 127.0.0.1:5060;branch=z9hG4bK-abc123")
    res.add_header("CSeq", "1 INVITE")
    
    # Match incoming response to the UAC transaction
    matched_key = TransactionKey.match_response_to_uac(res)
    print(f"Matched Key: {matched_key}")
    
    assert matched_key == uac_key

if __name__ == "__main__":
    try:
        test_key_matching()
        print("Transaction Key matching test PASSED")
    except Exception as e:
        print(f"Test FAILED: {e}")
        import traceback
        traceback.print_exc()
