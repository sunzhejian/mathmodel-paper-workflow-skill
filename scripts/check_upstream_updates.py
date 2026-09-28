"""Compare pinned skill submodules with upstream HEAD without changing files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def inspect(root: Path, timeout: int = 20) -> dict:
    lock = json.loads((root / "examples/upstream-lock.json").read_text(encoding="utf-8"))
    results = []
    for source in lock["sources"]:
        name, url, pinned = source["name"], source["url"], source["commit"]
        try:
            proc = subprocess.run(["git", "ls-remote", url, "HEAD"], capture_output=True,
                                  text=True, encoding="utf-8", timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            results.append({"name": name, "url": url, "pinned": pinned,
                            "remote": None, "status": "error", "detail": str(exc)})
            continue
        fields = proc.stdout.strip().split()
        if proc.returncode or len(fields) != 2 or fields[1] != "HEAD":
            results.append({"name": name, "url": url, "pinned": pinned,
                            "remote": None, "status": "error",
                            "detail": proc.stderr.strip() or "invalid git ls-remote response"})
            continue
        remote = fields[0]
        results.append({"name": name, "url": url, "pinned": pinned,
                        "remote": remote, "status": "current" if remote == pinned else "update_available"})
    return {"checked": len(results), "updates": sum(r["status"] == "update_available" for r in results),
            "errors": sum(r["status"] == "error" for r in results), "sources": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--timeout", type=int, default=20,
                        help="Seconds to wait per remote (default: 20)")
    args = parser.parse_args()
    if args.timeout < 1 or args.timeout > 120:
        parser.error("--timeout must be between 1 and 120")
    try:
        result = inspect(args.root.resolve(), args.timeout)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Upstream check failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["errors"] else (10 if result["updates"] else 0)


if __name__ == "__main__":
    raise SystemExit(main())
