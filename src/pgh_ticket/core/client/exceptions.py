"""Portal client exception hierarchy."""

from __future__ import annotations


class PortalError(Exception):
    """Base for all portal client errors."""

    def __init__(
        self,
        message: str,
        identifier: str,
        operation: str,
        proxy: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.identifier = identifier
        self.operation = operation
        self.proxy = proxy
        self.cause = cause
        super().__init__(message)


class ProxyExhaustedError(PortalError):
    """All retry attempts exhausted — every proxy in the pool failed."""

    def __init__(
        self,
        message: str,
        identifier: str,
        operation: str,
        attempts: int,
        proxy: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        self.attempts = attempts
        super().__init__(message, identifier=identifier, operation=operation, proxy=proxy, cause=cause)

    @classmethod
    def from_request(
        cls,
        identifier: str,
        operation: str,
        attempts: int,
        proxy: str | None = None,
        cause: Exception | None = None,
    ) -> ProxyExhaustedError:
        return cls(
            f"{operation} failed for {identifier} after {attempts} attempts on {proxy or 'direct'}",
            identifier=identifier,
            operation=operation,
            attempts=attempts,
            proxy=proxy,
            cause=cause,
        )


class ProxyRotateError(PortalError):
    """No proxy available to rotate to."""

    def __init__(
        self,
        identifier: str,
        operation: str,
        proxy: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            f"no proxy available for {operation} on {identifier}",
            identifier=identifier,
            operation=operation,
            proxy=proxy,
            cause=cause,
        )
