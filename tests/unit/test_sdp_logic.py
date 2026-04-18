import pytest
from jksip.media.sdp import SdpSession, SdpOrigin, SdpConnection, SdpMedia, SdpAttribute
from jksip.media.parser import SdpParser
from jksip.media.negotiator import SdpNegotiator, SdpNegState

def test_sdp_creation_and_serialization():
    addr = "127.0.0.1"
    port = 1234
    sdp = SdpSession.create_simple_audio(addr, port, codec_name="opus")
    
    sdp_str = str(sdp)
    assert "v=0\r\n" in sdp_str
    assert f"c=IN IP4 {addr}\r\n" in sdp_str
    assert f"m=audio {port} RTP/AVP 111\r\n" in sdp_str
    assert "a=rtpmap:111 opus/48000/2\r\n" in sdp_str

def test_sdp_parsing():
    raw_sdp = (
        "v=0\r\n"
        "o=- 123456 123456 IN IP4 192.168.1.1\r\n"
        "s=test\r\n"
        "c=IN IP4 192.168.1.1\r\n"
        "t=0 0\r\n"
        "m=audio 4000 RTP/AVP 111 0\r\n"
        "a=rtpmap:111 opus/48000/2\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
    )
    
    parsed = SdpParser.parse(raw_sdp)
    assert parsed.origin.addr == "192.168.1.1"
    assert len(parsed.media) == 1
    assert parsed.media[0].port == 4000
    assert "111" in parsed.media[0].fmts
    assert "0" in parsed.media[0].fmts

def test_sdp_negotiation_opus_success():
    # Local offer with Opus and PCMU
    local_sdp = SdpSession.create_simple_audio("127.0.0.1", 1000, codec_name="opus")
    # Add PCMU as alternative
    local_sdp.media[0].fmts.append("0")
    local_sdp.media[0].attributes.append(SdpAttribute(name="rtpmap", value="0 PCMU/8000"))
    
    # Remote answer supporting only Opus
    remote_sdp = SdpSession.create_simple_audio("192.168.1.2", 2000, codec_name="opus")
    
    neg = SdpNegotiator()
    neg.set_local_offer(local_sdp)
    neg.set_remote_answer(remote_sdp)
    neg.negotiate()
    
    assert neg.state == SdpNegState.DONE
    # The negotiated local SDP should now only have Opus
    assert neg.active_local.media[0].fmts == ["111"]
    assert neg.active_local.media[0].port == 1000

def test_sdp_negotiation_mismatch():
    local_sdp = SdpSession.create_simple_audio("127.0.0.1", 1000, codec_name="opus")
    # Remote only supports PCMU
    remote_sdp = SdpSession.create_simple_audio("192.168.1.2", 2000, codec_name="pcmu", payload_type=0, clock_rate=8000)
    
    neg = SdpNegotiator()
    neg.set_local_offer(local_sdp)
    neg.set_remote_answer(remote_sdp)
    neg.negotiate()
    
    assert neg.state == SdpNegState.DONE
    # Media should be deactivated (port 0) due to mismatch
    assert neg.active_local.media[0].port == 0
