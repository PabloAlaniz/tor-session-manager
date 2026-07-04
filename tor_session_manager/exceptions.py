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


class AllIPCheckersFailedError(IPFetchError):
    """Raised when every configured IP checker endpoint fails."""
    pass


class BlockedResponseError(TorSessionError):
    """Raised when a request stays blocked after exhausting exit rotations."""

    def __init__(self, message, reason=None, response=None):
        super().__init__(message)
        self.reason = reason
        self.response = response
