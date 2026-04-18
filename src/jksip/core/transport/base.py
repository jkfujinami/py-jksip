import asyncio
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List
import structlog

logger = structlog.get_logger(__name__)

class SipTransport(ABC):
    """
    Abstract Interface for SIP Transport (UDP, TCP, TLS, AMTP).
    Following the Liskov Substitution Principle.
    """
    def __init__(self, local_addr: tuple[str, int]):
        self.local_addr = local_addr
        self.is_reliable = False  # Set to True for TCP/TLS
        self.user_data: Any = None # Equivalent to pjsip_transport.data
        self.info: str = ""

    @abstractmethod
    async def send(self, remote_addr: tuple[str, int], data: bytes) -> None:
        """Sends raw data to a remote address."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Closes the transport."""
        pass

class UdpSipProtocol(asyncio.DatagramProtocol):
    """
    Asyncio Protocol for UDP-based SIP transport.
    """
    def __init__(self, owner: 'UdpSipTransport'):
        self.owner = owner
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:
        self.transport = transport
        logger.info("udp_transport_up", local_addr=transport.get_extra_info('sockname'))

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        logger.debug("udp_rx", addr=addr, size=len(data))
        # Dynamically call the current callback from the owner transport.
        # This allows AmptpTransport to override the callback after initialization.
        if self.owner.on_msg_callback:
            asyncio.create_task(self.owner.on_msg_callback(data, addr, self))

    def error_received(self, exc: Exception) -> None:
        logger.error("udp_error", error=str(exc))

class UdpSipTransport(SipTransport):
    """
    Concrete implementation of UDP Transport.
    """
    def __init__(self, local_addr: tuple[str, int], on_msg_callback: callable):
        super().__init__(local_addr)
        self.on_msg_callback = on_msg_callback
        self._protocol: Optional[UdpSipProtocol] = None
        self._transport: Optional[asyncio.DatagramTransport] = None
        self.info = f"UDP at {local_addr[0]}:{local_addr[1]}"

    async def start(self):
        loop = asyncio.get_running_loop()
        # Pass 'self' as the owner to allow dynamic callback resolution
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: UdpSipProtocol(self),
            local_addr=self.local_addr
        )

    async def send(self, remote_addr: tuple[str, int], data: bytes) -> None:
        if self._transport:
            self._transport.sendto(data, remote_addr)
            logger.debug("udp_tx", addr=remote_addr, size=len(data))
        else:
            logger.error("udp_send_failed_no_transport")

    def close(self) -> None:
        if self._transport:
            self._transport.close()
            logger.info("udp_transport_down")

class TransportManager:
    """
    Manages multiple SIP transports. Equivalent to pjsip_tpmgr.
    Enforces the Open/Closed Principle.
    """
    def __init__(self):
        self.transports: List[SipTransport] = []
        self._transports_by_type: Dict[str, SipTransport] = {}

    def register_transport(self, tp_type: str, transport: SipTransport):
        """ Registers a transport for a specific type (e.g. 'udp', 'amptp'). """
        self.transports.append(transport)
        self._transports_by_type[tp_type.lower()] = transport
        logger.info("transport_registered", type=tp_type, info=transport.info)

    def get_transport(self, tp_type: str) -> Optional[SipTransport]:
        """ Retrieves a transport by its type. """
        return self._transports_by_type.get(tp_type.lower())

    def find_transport_for_addr(self, remote_addr: tuple[str, int], reliable: bool = False) -> Optional[SipTransport]:
        """ Finds a suitable transport for the given destination. """
        # Basic logic: prefer reliable if requested, otherwise return the first available
        for tp in self.transports:
            if tp.is_reliable == reliable:
                return tp
        return self.transports[0] if self.transports else None
