import argparse

import uvicorn


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="findash", description="Start the financial dashboard API."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    uvicorn.run("findash.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
