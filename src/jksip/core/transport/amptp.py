import structlog
from typing import Optional, Any, Dict
from .base import SipTransport, UdpSipTransport

logger = structlog.get_logger(__name__)

class AmptpTransport(SipTransport):
    """
    Andromeda Proprietary Transport (AMTP).
    Wraps standard SIP packets in the proprietary Andromeda envelope.
    Implementation is based on reverse-engineering of libandromeda.so.
    """
    def __init__(self, udp_transport: UdpSipTransport, upper_callback: callable):
        super().__init__(udp_transport.local_addr)
        self.udp = udp_transport
        self.upper_callback = upper_callback # Typically endpoint.on_receive_msg
        self.info = f"AMTP over {udp_transport.info}"
        self.is_reliable = False
        
        # Intercept lower transport messages
        self.udp.on_msg_callback = self._on_udp_msg
        
        # Internal state
        self._seq_send = 0
        self._seq_recv = 0

    async def _on_udp_msg(self, data: bytes, addr: tuple[str, int], transport: Any):
        """ Callback from the actual UDP transport. """
        unwrapped_data, metadata = self.unwrap_packet(data)
        
        if not metadata:
            # Not an AMTP packet, drop or handle as raw SIP if needed
            logger.debug("amptp_rx_invalid_magic", addr=addr, data=data[:16].hex())
            return

        # Pass the unwrapped data up, pretending it came from this AMTP transport
        await self.upper_callback(unwrapped_data, addr, self)

    def wrap_packet(self, data: bytes) -> bytes:
        """
        Wraps a SIP packet with the AMTP header.
        Structure: [Magic(1)] [Seq(4, Little Endian)] [Payload]
        """
        import struct
        magic = b'\x01' 
        self._seq_send += 1
        header = magic + struct.pack("<I", self._seq_send)
        return header + data

    def unwrap_packet(self, data: bytes) -> tuple[bytes, Dict[str, Any]]:
        """
        Unwraps an AMTP packet and extracts the SIP payload.
        Andromeda AMTP Format: [Magic:1] [Seq:4]
        Total header size: 5 bytes.
        """
        import struct
        # Minimum AMTP header is 5 bytes
        if len(data) < 5 or data[0] != 0x01:
            return b"", {}
        
        try:
            # Logic: Magic (1 byte) + Seq (4 bytes, Little Endian)
            # Based on 'd' (0x64) leaking into SIP when only 1 byte was skipped or offset was wrong.
            seq = struct.unpack("<I", data[1:5])[0]
            
            # The payload follows the 5-byte header
            payload = data[5:]
            
            logger.debug("amptp_rx_success", seq=seq, size=len(payload), total=len(data))
            return payload, {"seq": seq}
        except Exception as e:
            logger.error("amptp_unwrap_error", error=str(e), hex=data.hex())
            return b"", {}

    async def send(self, remote_addr: tuple[str, int], data: bytes) -> None:
        """ Encapsulates the SIP data and sends it via the underlying UDP transport. """
        wrapped_data = self.wrap_packet(data)
        logger.debug("amptp_tx", addr=remote_addr, seq=self._seq_send, original_size=len(data))
        await self.udp.send(remote_addr, wrapped_data)

    def close(self) -> None:
        """ Closes the underlying transport. """
        self.udp.close()
