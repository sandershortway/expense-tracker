import argparse
import sys

import uvicorn

from findash.core.settings import get_settings
from findash.investments.database import upgrade_database


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="findash", description="Start the financial dashboard API."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)

    try:
        upgrade_database(get_settings().investments_database_url)
    except Exception as error:
        print(f"error: database migration failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    uvicorn.run("findash.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
