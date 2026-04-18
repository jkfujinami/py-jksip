from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class SdpOrigin(BaseModel):
    """ o=<username> <sess-id> <sess-version> <nettype> <addrtype> <unicast-address> """
    username: str = "-"
    sess_id: int = 0
    sess_version: int = 0
    net_type: str = "IN"
    addr_type: str = "IP4"
    addr: str

    def __str__(self) -> str:
        return f"o={self.username} {self.sess_id} {self.sess_version} {self.net_type} {self.addr_type} {self.addr}\r\n"

class SdpConnection(BaseModel):
    """ c=<nettype> <addrtype> <connection-address> """
    net_type: str = "IN"
    addr_type: str = "IP4"
    addr: str

    def __str__(self) -> str:
        return f"c={self.net_type} {self.addr_type} {self.addr}\r\n"

class SdpAttribute(BaseModel):
    """ a=<name>[:<value>] """
    name: str
    value: Optional[str] = None

    def __str__(self) -> str:
        if self.value:
            return f"a={self.name}:{self.value}\r\n"
        return f"a={self.name}\r\n"

class SdpMedia(BaseModel):
    """ m=<media> <port> <proto> <fmt> ... """
    media: str = "audio"
    port: int = 0
    proto: str = "RTP/AVP"
    fmts: List[str] = Field(default_factory=list)
    conn: Optional[SdpConnection] = None
    attributes: List[SdpAttribute] = Field(default_factory=list)

    def __str__(self) -> str:
        fmts_str = " ".join(self.fmts)
        res = f"m={self.media} {self.port} {self.proto} {fmts_str}\r\n"
        if self.conn:
            res += str(self.conn)
        for attr in self.attributes:
            res += str(attr)
        return res

class SdpSession(BaseModel):
    """
    Represents an SDP Session (RFC 4566).
    Equivalent to pjmedia_sdp_session in PJSIP.
    """
    version: int = 0
    origin: SdpOrigin
    name: str = "jksip"
    conn: Optional[SdpConnection] = None
    times: str = "t=0 0\r\n"
    attributes: List[SdpAttribute] = Field(default_factory=list)
    media: List[SdpMedia] = Field(default_factory=list)

    def __str__(self) -> str:
        res = f"v={self.version}\r\n"
        res += str(self.origin)
        res += f"s={self.name}\r\n"
        if self.conn:
            res += str(self.conn)
        res += self.times
        for attr in self.attributes:
            res += str(attr)
        for m in self.media:
            res += str(m)
        return res

    @classmethod
    def create_simple_audio(cls, addr: str, port: int, payload_type: int = 111, codec_name: str = "opus", clock_rate: int = 48000) -> 'SdpSession':
        """ Utility to create a basic audio offer (Opus by default). """
        import time
        sess_id = int(time.time())
        origin = SdpOrigin(addr=addr, sess_id=sess_id, sess_version=sess_id)
        conn = SdpConnection(addr=addr)
        
        media = SdpMedia(port=port, fmts=[str(payload_type)])
        media.attributes.append(SdpAttribute(name="rtpmap", value=f"{payload_type} {codec_name}/{clock_rate}/2"))
        
        if codec_name == "opus":
             # Typical Opus fmtrpam according to RFC 7587
             media.attributes.append(SdpAttribute(name="fmtp", value=f"{payload_type} useinbandfec=1; usedtx=1"))

        return cls(origin=origin, conn=conn, media=[media])
