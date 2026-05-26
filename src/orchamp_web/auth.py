"""
HTTP Basic Auth dependency for beta access control.
"""

import hmac
import os
from typing import Annotated

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_security = HTTPBasic(auto_error=False)


def require_basic_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_security)],
) -> None:
    """
    Enforce HTTP Basic Auth if ORCHAMP_BETA_PASSWORD is set.

    If the env var is not set, all requests pass through (useful for
    development).
    """

    expected_password = os.environ.get("ORCHAMP_BETA_PASSWORD")

    if not expected_password:
        return

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )

    password_matches = hmac.compare_digest(
        credentials.password.encode("utf-8"),
        expected_password.encode("utf-8"),
    )

    if not password_matches:
        raise HTTPException(
            status_code=401,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Basic"},
        )
