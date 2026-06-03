"""
Command-line helpers for the web application.
"""

import getpass
import sys

from orchamp_web.auth import make_password_hasher


def hash_password_main() -> None:
    """
    Generate an Argon2 password hash for ``ORCHAMP_BETA_PASSWORD_HASH``.

    Prompts for the password interactively so it never lands in shell history.
    Prints the hash to stdout.
    """

    password = getpass.getpass("Beta password: ")
    if password != getpass.getpass("Confirm password: "):
        print("Passwords did not match.", file=sys.stderr)
        sys.exit(1)

    print(make_password_hasher().hash(password))
