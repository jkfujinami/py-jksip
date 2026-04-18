import structlog
from typing import List, Optional
from .sdp import SdpSession, SdpMedia, SdpAttr, SdpOrigin, SdpConnection

logger = structlog.get_logger(__name__)

class SdpParser:
    """
    Parses raw SDP text into SdpSession object.
    Follows RFC 4566.
    """
    @classmethod
    def parse(cls, text: str) -> SdpSession:
        lines = text.strip().splitlines()
        
        session_data = {
            "attributes": [],
            "media": []
        }
        current_media: Optional[dict] = None
        
        for line in lines:
            if not line.strip() or "=" not in line:
                continue
                
            line_type, value = line.split("=", 1)
            line_type = line_type.strip()
            value = value.strip()
            
            if line_type == "v":
                session_data["version"] = int(value)
            elif line_type == "o":
                parts = value.split()
                session_data["origin"] = SdpOrigin(
                    username=parts[0],
                    session_id=int(parts[1]),
                    session_version=int(parts[2]),
                    net_type=parts[3],
                    addr_type=parts[4],
                    address=parts[5]
                )
            elif line_type == "s":
                session_data["session_name"] = value
            elif line_type == "c":
                parts = value.split()
                conn = SdpConnection(
                    net_type=parts[0],
                    addr_type=parts[1],
                    address=parts[2]
                )
                if current_media is not None:
                    current_media["connection"] = conn
                else:
                    session_data["connection"] = conn
            elif line_type == "a":
                name, *val_list = value.split(":", 1)
                attr = SdpAttr(name=name, value=val_list[0] if val_list else None)
                if current_media is not None:
                    current_media["attributes"].append(attr)
                else:
                    session_data["attributes"].append(attr)
            elif line_type == "m":
                parts = value.split()
                current_media = {
                    "media_type": parts[0],
                    "port": int(parts[1]),
                    "transport": parts[2],
                    "formats": parts[3:],
                    "attributes": []
                }
                session_data["media"].append(current_media)
            elif line_type == "t":
                # Currently ignore time, as we default it in SdpSession
                pass
                
        # Final conversion to Pydantic models
        media_models = []
        for m_data in session_data["media"]:
             media_models.append(SdpMedia(**m_data))
        
        session_data["media"] = media_models
        return SdpSession(**session_data)
