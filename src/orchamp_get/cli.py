import argparse
import json
import sys

import httpx2

from orchamp_get.html_transform import strip_and_anonymize_html
from orchamp_get.parser import parse_html


def cmd_fetch(url: str, *, anonymize: bool = False) -> int:
    """
    Fetch a standings page and output cleaned HTML.
    """

    try:
        response = httpx2.get(url)
        response.raise_for_status()
    except httpx2.HTTPError as e:
        print(f"Failed to fetch URL: {e}", file=sys.stderr)
        return 1

    html = strip_and_anonymize_html(html=response.text, anonymize=anonymize)
    print(html)
    return 0


def cmd_parse(file_path: str) -> int:
    """
    Parse a local HTML file and output championship state as JSON.
    """

    try:
        with open(file_path, encoding="utf-8") as f:
            html = f.read()
    except OSError as e:
        print(json.dumps({"error": f"Failed to read file: {e}"}), file=sys.stderr)
        return 1

    state = parse_html(html)
    print(json.dumps(state, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="orchamp-get",
        description="Fetch and parse league standings",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch",
        help="Fetch a standings page and output cleaned HTML",
    )
    fetch_parser.add_argument("url", help="URL of the standings page")
    fetch_parser.add_argument(
        "--anonymize",
        action="store_true",
        help="Anonymize team names and IDs",
    )

    parse_parser = subparsers.add_parser(
        "parse",
        help="Parse a local HTML file and output JSON",
    )
    parse_parser.add_argument("file", help="Path to the HTML file")

    args = parser.parse_args()

    if args.command == "fetch":
        return cmd_fetch(args.url, anonymize=args.anonymize)
    elif args.command == "parse":
        return cmd_parse(args.file)
    else:
        assert False, "Unreachable"


if __name__ == "__main__":
    sys.exit(main())
