from typing import Dict, Any, List
from .sdp import SdpSession, SdpOrigin, SdpConnection, SdpMedia, SdpAttribute
from ..core.exceptions import SipSyntaxError

class SdpParser:
    """
    Parser for SDP (Session Description Protocol) RFC 4566.
    Mirroring the line-by-line parsing logic of PJSIP's sdp.c.
    """
    @classmethod
    def parse(cls, sdp_text: str) -> SdpSession:
        lines = sdp_text.replace("\r\n", "\n").split("\n")
        
        # PJSIP style: session-level first, then media segments
        session_data: Dict[str, Any] = {
            "attributes": [],
            "media": []
        }
        
        current_media: Optional[Dict[str, Any]] = None
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if len(line) < 3 or line[1] != "=":
                continue
                
            line_type = line[0]
            value = line[2:]
            
            if line_type == "v":
                session_data["version"] = int(value)
            elif line_type == "o":
                parts = value.split()
                if len(parts) >= 6:
                    session_data["origin"] = SdpOrigin(
                        username=parts[0],
                        sess_id=int(parts[1]),
                        sess_version=int(parts[2]),
                        net_type=parts[3],
                        addr_type=parts[4],
                        addr=parts[5]
                    )
            elif line_type == "s":
                session_data["name"] = value
            elif line_type == "c":
                parts = value.split()
                if len(parts) >= 3:
                    conn = SdpConnection(net_type=parts[0], addr_type=parts[1], addr=parts[2])
                    if current_media is not None:
                        current_media["conn"] = conn
                    else:
                        session_data["conn"] = conn
            elif line_type == "t":
                session_data["times"] = line + "\r\n"
            elif line_type == "m":
                parts = value.split()
                if len(parts) >= 4:
                    current_media = {
                        "media": parts[0],
                        "port": int(parts[1]),
                        "proto": parts[2],
                        "fmts": parts[3:],
                        "attributes": [],
                        "conn": None
                    }
                    session_data["media"].append(current_media)
            elif line_type == "a":
                attr_parts = value.split(":", 1)
                attr_name = attr_parts[0]
                attr_value = attr_parts[1] if len(attr_parts) > 1 else None
                attr = SdpAttribute(name=attr_name, value=attr_value)
                
                if current_media is not None:
                    current_media["attributes"].append(attr)
                else:
                    session_data["attributes"].append(attr)
                    
        # Construct final objects
        media_objects = []
        for m in session_data["media"]:
            media_objects.append(SdpMedia(**m))
            
        session_data["media"] = media_objects
        return SdpSession(**session_data)
