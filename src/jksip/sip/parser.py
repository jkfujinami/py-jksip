from typing import Optional
from dataclasses import dataclass
from ..core.exceptions import SipSyntaxError
from .message import SipRequest, SipResponse, SipHeader, SipMessage

@dataclass(frozen=True)
class ScannerState:
    """Stores the current state of the scanner for rollbacks."""
    curptr: int

class SipScanner:
    """
    Fast text scanning utility for SIP messages.
    Wraps a byte buffer in a memoryview for efficient navigation.
    """
    def __init__(self, buffer: bytes):
        self._buffer = memoryview(buffer)
        self._curptr = 0
        self._length = len(buffer)

    @property
    def is_eof(self) -> bool:
        return self._curptr >= self._length

    def peek(self) -> int:
        """Returns the character at the current position without advancing."""
        if self.is_eof:
            return 0
        return self._buffer[self._curptr]

    def get_char(self) -> int:
        """Returns the character at the current position and advances the pointer."""
        if self.is_eof:
            raise SipSyntaxError("Unexpected EOF")
        char = self._buffer[self._curptr]
        self._curptr += 1
        return char

    def skip_whitespace(self) -> None:
        """Skips spaces and tabs."""
        while not self.is_eof and self.peek() in b' \t':
            self._curptr += 1

    def skip_noise(self) -> None:
        """
        Skips anything that is not a letter/number or START_LINE character.
        Equivalent to PJ_SCAN_AUTOSKIP_WS_HEADER in PJSIP.
        Skips whitespace, newlines, and control characters (like NULL).
        """
        while not self.is_eof and (self.peek() <= 32 or self.peek() > 126):
            self._curptr += 1

    def get_until(self, until_chars: bytes) -> bytes:
        """
        Returns all characters until one of the characters in `until_chars` is found.
        The pointer is moved to the position of the matched character.
        """
        start = self._curptr
        while not self.is_eof and self.peek() not in until_chars:
            self._curptr += 1
        return self._buffer[start:self._curptr].tobytes()

    def get_token(self, token_chars: bytes) -> bytes:
        """
        Equivalent to pj_scan_get. Returns characters while they match `token_chars`.
        """
        start = self._curptr
        while not self.is_eof and self.peek() in token_chars:
            self._curptr += 1
        if start == self._curptr:
            raise SipSyntaxError(f"Expected token, found '{chr(self.peek())}'")
        return self._buffer[start:self._curptr].tobytes()

    def expect_char(self, char: int) -> None:
        """Consumes exactly one expected character."""
        if self.get_char() != char:
            raise SipSyntaxError(f"Expected '{chr(char)}' at position {self._curptr-1}")

    def save_state(self) -> ScannerState:
        return ScannerState(curptr=self._curptr)

    def restore_state(self, state: ScannerState) -> None:
        self._curptr = state.curptr

class SipParser:
    """
    High-level SIP message parser. Orchestrates the scanning process
    to produce SipRequest or SipResponse objects.
    """
    TOKEN = b'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.!%*_`\'~+'

    @classmethod
    def parse(cls, message_bytes: bytes) -> SipMessage:
        """Parses a complete SIP message."""
        scanner = SipScanner(message_bytes)
        
        # Skip leading noise (PJ_SCAN_AUTOSKIP_WS_HEADER parity)
        scanner.skip_noise()
        
        # Determine if it's a request or response by looking at the first word
        first_word_bytes = scanner.get_until(b' ')
        first_word = first_word_bytes.decode(errors='replace').strip()
        scanner.skip_whitespace()
        
        if first_word.startswith("SIP/2.0"):
            msg = cls._parse_response(scanner, first_word)
        else:
            msg = cls._parse_request(scanner, first_word)
            
        cls._parse_headers(scanner, msg)
        cls._parse_body(scanner, msg)
        
        return msg

    @classmethod
    def _parse_request(cls, scanner: SipScanner, method: str) -> SipRequest:
        """Parses Request-Line: Method SP Request-URI SP SIP-Version CRLF"""
        uri = scanner.get_until(b' ').decode(errors='replace')
        scanner.skip_whitespace()
        version = scanner.get_until(b'\r\n').decode(errors='replace')
        scanner.expect_char(ord('\r'))
        scanner.expect_char(ord('\n'))
        return SipRequest(method=method, uri=uri, version=version)

    @classmethod
    def _parse_response(cls, scanner: SipScanner, version: str) -> SipResponse:
        """Parses Status-Line: SIP-Version SP Status-Code SP Reason-Phrase CRLF"""
        status_code_bytes = scanner.get_token(b'0123456789')
        status_code = int(status_code_bytes)
        scanner.skip_whitespace()
        reason = scanner.get_until(b'\r\n').decode(errors='replace')
        scanner.expect_char(ord('\r'))
        scanner.expect_char(ord('\n'))
        return SipResponse(status_code=status_code, reason=reason, version=version)

    @classmethod
    def _parse_headers(cls, scanner: SipScanner, msg: SipMessage) -> None:
        """Parses headers until CRLF CRLF."""
        while not scanner.is_eof:
            # Check for empty line (end of headers)
            if scanner.peek() == ord('\r'):
                scanner.expect_char(ord('\r'))
                scanner.expect_char(ord('\n'))
                break
                
            name = scanner.get_until(b':').decode(errors='replace').strip()
            scanner.expect_char(ord(':'))
            scanner.skip_whitespace()
            value = scanner.get_until(b'\r\n').decode(errors='replace').strip()
            scanner.expect_char(ord('\r'))
            scanner.expect_char(ord('\n'))
            
            msg.add_header(name, value)

    @classmethod
    def _parse_body(cls, scanner: SipScanner, msg: SipMessage) -> None:
        """Handles the message body based on Content-Length."""
        content_length_str = msg.get_header("Content-Length")
        if content_length_str:
            content_length = int(content_length_str)
            # In a real transport, the body might not be fully available in this buffer
            # but for this parser-only logic, we take what's left.
            start = scanner._curptr
            msg.body = scanner._buffer[start : start + content_length].tobytes()
