from enum import IntEnum

class SipStatusCode(IntEnum):
    # 1xx Informational
    TRYING = 100
    RINGING = 180
    CALL_BEING_FORWARDED = 181
    QUEUED = 182
    PROGRESS = 183

    # 2xx Success
    OK = 200
    ACCEPTED = 202

    # 3xx Redirection
    MULTIPLE_CHOICES = 300
    MOVED_PERMANENTLY = 301
    MOVED_TEMPORARILY = 302
    USE_PROXY = 305
    ALTERNATIVE_SERVICE = 380

    # 4xx Client Error
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    PAYMENT_REQUIRED = 402
    FORBIDDEN = 403
    NOT_FOUND = 404
    METHOD_NOT_ALLOWED = 405
    NOT_ACCEPTABLE = 406
    PROXY_AUTHENTICATION_REQUIRED = 407
    REQUEST_TIMEOUT = 408
    GONE = 410
    REQUEST_ENTITY_TOO_LARGE = 413
    REQUEST_URI_TOO_LONG = 414
    UNSUPPORTED_MEDIA_TYPE = 415
    UNSUPPORTED_URI_SCHEME = 416
    BAD_EXTENSION = 420
    EXTENSION_REQUIRED = 421
    SESSION_TIMER_TOO_SMALL = 422
    INTERVAL_TOO_BRIEF = 423
    TEMPORARILY_UNAVAILABLE = 480
    CALL_TSX_DOES_NOT_EXIST = 481
    LOOP_DETECTED = 482
    TOO_MANY_HOPS = 483
    ADDRESS_INCOMPLETE = 484
    AMBIGUOUS = 485
    BUSY_HERE = 486
    REQUEST_TERMINATED = 487
    NOT_ACCEPTABLE_HERE = 488
    BAD_EVENT = 489
    REQUEST_UPDATED = 490
    REQUEST_PENDING = 491
    UNDECIPHERABLE = 493

    # 5xx Server Error
    INTERNAL_SERVER_ERROR = 500
    NOT_IMPLEMENTED = 501
    BAD_GATEWAY = 502
    SERVICE_UNAVAILABLE = 503
    SERVER_TIMEOUT = 504
    VERSION_NOT_SUPPORTED = 505
    MESSAGE_TOO_LARGE = 513
    PRECONDITION_FAILURE = 580

    # 6xx Global Failure
    BUSY_EVERYWHERE = 600
    DECLINE = 603
    DOES_NOT_EXIST_ANYWHERE = 604
    NOT_ACCEPTABLE_ANYWHERE = 606

class JkSipError(Exception):
    """Base class for all py-jksip errors."""
    pass

class SipStatusError(JkSipError):
    """Exception raised for non-2xx SIP responses."""
    def __init__(self, status_code: int, reason: str = ""):
        self.status_code = status_code
        self.reason = reason
        super().__init__(f"SIP {status_code} {reason}")

class SipSyntaxError(JkSipError):
    """Raised when SIP message parsing fails."""
    pass

class SipTransportError(JkSipError):
    """Raised on network I/O errors."""
    pass
