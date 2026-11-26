"""Check staged Git blobs, or the full tracked tree with --all, before publishing."""
import argparse
import ipaddress
import re
import subprocess
import sys
from pathlib import PurePosixPath


PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "access token": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:ant-)?[A-Za-z0-9_-]{24,}|eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,})"),
    "credential literal": re.compile(rb"(?i)[\"']?(?:password|passwd|aihub_password|api_key|square_api_key|access_token|refresh_token|client_secret)[\"']?\s*[:=]\s*[\"']([^\"'\r\n]+)[\"']"),
    "password fallback": re.compile(rb"(?i)\.get\(\s*[\"']password[\"']\s*,\s*[\"']([^\"'\r\n]+)[\"']"),
    "personal home path": re.compile(rb"(?i)[A-Z]:[/\\]Users[/\\][^/\\\s\"']+"),
}
PLACEHOLDERS = {b"example", b"placeholder", b"changeme", b"your-password", b"your-api-key"}


def content_issues(path, content):
    """Return categories only, never the matched secret value."""
    name = PurePosixPath(path).name.lower()
    if (path.startswith("data/") or name in {"config.json", "auth.json", ".credentials.json", ".env"}
            or name.startswith(".env.") or name in {"id_rsa", "id_ed25519"}
            or name.endswith((".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".log"))):
        yield "private runtime file", 1
    for number, line in enumerate(content.splitlines(), 1):
        for category, pattern in PATTERNS.items():
            match = pattern.search(line)
            if match and (not match.lastindex or match[1].lower() not in PLACEHOLDERS):
                yield category, number
        for address in re.findall(rb"\b(?:\d{1,3}\.){3}\d{1,3}\b", line):
            try:
                ip = ipaddress.ip_address(address.decode())
            except ValueError:
                continue
            if any(ip in network for network in PRIVATE_NETWORKS):
                yield "private network address", number


PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in ((167772160, 8), (2886729728, 12), (3232235520, 16)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="check every tracked file in the index")
    args = parser.parse_args()
    command = ["git", "ls-files", "-z"] if args.all else ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"]
    paths = subprocess.check_output(command).split(b"\0")
    failed = False
    for raw_path in filter(None, paths):
        path = raw_path.decode("utf-8")
        content = subprocess.check_output(["git", "show", ":" + path])
        for category, line in content_issues(path, content):
            print(f"{path}:{line}: {category}")
            failed = True
    if failed:
        print("Remove private content from staged files before publishing. Review screenshots manually.")
    return int(failed)


if __name__ == "__main__":
    sys.exit(main())
