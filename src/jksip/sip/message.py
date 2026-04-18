from typing import List, Optional, Union, Any, Dict
from pydantic import BaseModel, Field

class SipHeader(BaseModel):
    """
    Represents a single SIP header field.
    """
    name: str
    value: str

    def __str__(self) -> str:
        return f"{self.name}: {self.value}"

def pjsip_generic_string_hdr_create(pool: Optional[Any], hname: str, hvalue: str) -> SipHeader:
    """
    Creates a generic string header.
    Equivalent to pjsip_generic_string_hdr_create in native PJSIP.
    """
    return SipHeader(name=hname, value=hvalue)

class SipMessage(BaseModel):
    """
    Base class for SIP Requests and Responses.
    Contains common elements like headers and body.
    """
    headers: List[SipHeader] = Field(default_factory=list)
    body: Optional[bytes] = None

    def get_header(self, name: str) -> Optional[str]:
        """Returns the value of the first header with the given name."""
        name_lower = name.lower()
        for h in self.headers:
            if h.name.lower() == name_lower:
                return h.value
        return None

    def add_header(self, name: str, value: str) -> None:
        """Adds a new header to the message."""
        self.headers.append(SipHeader(name=name, value=value))

    def remove_header(self, name: str) -> None:
        """Removes all headers with the given name."""
        name_lower = name.lower()
        self.headers = [h for h in self.headers if h.name.lower() != name_lower]

    def replace_header(self, name: str, value: str) -> None:
        """
        Replaces the first occurrence of the header with the given name.
        If it doesn't exist, adds a new one.
        """
        name_lower = name.lower()
        for i, h in enumerate(self.headers):
            if h.name.lower() == name_lower:
                self.headers[i] = SipHeader(name=name, value=value)
                return
        self.add_header(name, value)

    def get_header_param(self, name: str, param: str) -> Optional[str]:
        """Excerpts a parameter value from a header (e.g., 'branch' from 'Via')."""
        value = self.get_header(name)
        if not value:
            return None
        
        parts = value.split(";")
        for p in parts[1:]:
            p = p.strip()
            if "=" in p:
                k, v = p.split("=", 1)
                if k.strip().lower() == param.lower():
                    return v.strip()
            elif p.lower() == param.lower():
                 return "" # Flag parameter
        return None

    def get_auth_params(self, name: str) -> Dict[str, str]:
        """
        Parses an authentication header (WWW-Authenticate or Proxy-Authenticate)
        and returns its parameters as a dictionary.
        Recognizes 'Digest' scheme and strips quotes from values.
        """
        import re
        value = self.get_header(name)
        if not value:
            return {}
        
        # Expecting: Scheme param="value", param2=value2, ...
        # Step 1: Strip scheme (e.g., 'Digest ')
        if " " in value:
            scheme, params_str = value.split(" ", 1)
        else:
            return {}

        # Step 2: Extract key-value pairs using regex to handle quoted strings with commas
        # Reference: RFC 2617 / PJSIP sip_auth_parser
        pattern = re.compile(r'(\w+)\s*=\s*("([^"]*)"|([^,]*))')
        params = {}
        for match in pattern.finditer(params_str):
            key = match.group(1).lower()
            val = match.group(3) if match.group(3) is not None else match.group(4)
            params[key] = val.strip()
            
        return params

    def copy(self) -> 'SipMessage':
        """Creates a deep copy of the message."""
        import copy
        return copy.deepcopy(self)

    def replace_header_param(self, name: str, param: str, value: Optional[str]) -> None:
        """
        Updates or removes a parameter in a header.
        If value is None, the parameter is removed.
        """
        hdr_val = self.get_header(name)
        if not hdr_val:
            return
        
        parts = [p.strip() for p in hdr_val.split(";")]
        new_parts = [parts[0]] # The main value
        
        param_lower = param.lower()
        found = False
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                if k.strip().lower() == param_lower:
                    if value is not None:
                        new_parts.append(f"{k.strip()}={value}")
                        found = True
                else:
                    new_parts.append(p)
            else:
                if p.lower() == param_lower:
                    if value is not None:
                        # Re-add flag or update with value
                        new_parts.append(f"{p}={value}" if value != "" else p)
                        found = True
                else:
                    new_parts.append(p)
        
        if not found and value is not None:
            new_parts.append(f"{param}={value}" if value != "" else param)
            
        self.replace_header(name, "; ".join(new_parts))

class SipRequest(SipMessage):
    """
    Represents a SIP Request message.
    """
    method: str
    uri: str
    version: str = "SIP/2.0"

    def __str__(self) -> str:
        start_line = f"{self.method} {self.uri} {self.version}"
        headers = "\r\n".join(str(h) for h in self.headers)
        res = f"{start_line}\r\n{headers}\r\n\r\n"
        if self.body:
            res += self.body.decode(errors='ignore')
        return res

class SipResponse(SipMessage):
    """
    Represents a SIP Response message.
    """
    status_code: int
    reason: str
    version: str = "SIP/2.0"

    def __str__(self) -> str:
        start_line = f"{self.version} {self.status_code} {self.reason}"
        headers = "\r\n".join(str(h) for h in self.headers)
        res = f"{start_line}\r\n{headers}\r\n\r\n"
        if self.body:
            res += self.body.decode(errors='ignore')
        return res
