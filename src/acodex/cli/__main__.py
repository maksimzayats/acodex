from __future__ import annotations

from acodex.cli.app import app
from acodex.ioc.container import get_cli_container


@app.callback()
def configure_cli_dependencies() -> None:
    get_cli_container()


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
