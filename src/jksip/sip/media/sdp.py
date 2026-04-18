from typing import List, Optional
from pydantic import BaseModel, Field

class SdpAttr(BaseModel):
    """Generic SDP attribute (a= line)."""
    name: str
    value: Optional[str] = None

    def __str__(self) -> str:
        if self.value:
            return f"a={self.name}:{self.value}"
        return f"a={self.name}"

class SdpConnection(BaseModel):
    """SDP connection info (c= line)."""
    net_type: str = "IN"
    addr_type: str = "IP4"
    address: str

    def __str__(self) -> str:
        return f"c={self.net_type} {self.addr_type} {self.address}"

class SdpOrigin(BaseModel):
    """SDP origin info (o= line)."""
    username: str = "-"
    session_id: int
    session_version: int
    net_type: str = "IN"
    addr_type: str = "IP4"
    address: str

    def __str__(self) -> str:
        return f"o={self.username} {self.session_id} {self.session_version} {self.net_type} {self.addr_type} {self.address}"

class SdpMedia(BaseModel):
    """SDP media description (m= line and its context)."""
    media_type: str # e.g., "audio", "video"
    port: int
    transport: str = "RTP/AVP"
    formats: List[str] # List of payload types
    connection: Optional[SdpConnection] = None
    attributes: List[SdpAttr] = Field(default_factory=list)

    def __str__(self) -> str:
        m_line = f"m={self.media_type} {self.port} {self.transport} {' '.join(self.formats)}"
        lines = [m_line]
        if self.connection:
            lines.append(str(self.connection))
        for attr in self.attributes:
            lines.append(str(attr))
        return "\r\n".join(lines)

class SdpSession(BaseModel):
    """
    Represents a full SDP session description (RFC 4566).
    Equivalent to pjmedia_sdp_session in PJMEDIA.
    """
    version: int = 0
    origin: SdpOrigin
    session_name: str = "jksip"
    connection: Optional[SdpConnection] = None
    attributes: List[SdpAttr] = Field(default_factory=list)
    media: List[SdpMedia] = Field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"v={self.version}",
            str(self.origin),
            f"s={self.session_name}"
        ]
        if self.connection:
            lines.append(str(self.connection))
        
        # Session-level attributes
        for attr in self.attributes:
            lines.append(str(attr))
            
        # Time section (t= line is mandatory in RFC 4566)
        lines.append("t=0 0")
        
        # Media sections
        for m in self.media:
            lines.append(str(m))
            
        return "\r\n".join(lines) + "\r\n"
