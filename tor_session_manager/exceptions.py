"""
Custom exceptions for Tor Session Manager.
"""


class TorSessionError(Exception):
    """Base exception for Tor Session Manager."""
    pass


class TorConnectionError(TorSessionError):
    """Raised when unable to connect to Tor controller."""
    pass


class TorNotReadyError(TorSessionError):
    """Raised when Tor is not fully bootstrapped."""
    pass


class IPFetchError(TorSessionError):
    """Raised when unable to determine public IP."""
    pass
