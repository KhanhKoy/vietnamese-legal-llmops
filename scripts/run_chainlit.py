"""Start Chainlit without inheriting incompatible generic DEBUG values."""

from __future__ import annotations

import os
import sys


def main() -> None:
    # Chainlit maps its --debug flag to the generic DEBUG environment variable.
    # Some IDEs/terminals set DEBUG=release, which Click cannot parse as bool.
    if os.getenv("DEBUG", "").lower() not in {
        "",
        "0",
        "1",
        "false",
        "true",
        "no",
        "yes",
        "off",
        "on",
    }:
        os.environ["DEBUG"] = "false"

    from chainlit.cli import cli

    sys.argv = ["chainlit", "run", "app.py", *sys.argv[1:]]
    cli()


if __name__ == "__main__":
    main()
