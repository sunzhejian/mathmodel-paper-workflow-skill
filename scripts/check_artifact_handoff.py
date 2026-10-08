"""Read-only file handoff check: candidate != published != delivery read-back.

Consumes a host-captured list response and local download/archive bytes. It does
not register paths, copy files, call an API, restore snapshots or verify science.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import sys
import zipfile


def digest(stream):
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        value.update(chunk)
    return value.hexdigest()


def relative(value):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("Artifact paths must be nonempty project-relative strings")
    value = value.replace("\\", "/")
    parts = PurePosixPath(value).parts
    if (PureWindowsPath(value).drive or value.startswith("/") or ":" in value
            or ".." in parts or any(x.endswith((" ", ".")) for x in parts)):
        raise ValueError("Artifact paths cannot escape the selected root or use ambiguous components")
    if not parts or any(x.lower() in {".git", ".env", ".ssh", ".aws", ".codex", "credentials"} for x in parts):
        raise ValueError("Repository internals or private files are not delivery artifacts")
    return "/".join(parts)


def file_record(root, name, expected):
    if root is None:
        return {"checked": False, "present": False, "hash_matches": False}
    base = Path(root).resolve()
    name = relative(name)
    target = base / name
    current = base
    for part in PurePosixPath(name).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Linked artifact paths are unsupported for handoff evidence")
    if not target.resolve().is_relative_to(base):
        raise ValueError("Artifact escaped the selected root")
    if not target.is_file():
        return {"checked": True, "present": False, "hash_matches": False}
    if target.stat().st_nlink != 1:
        raise ValueError("Hard-linked artifact files are unsupported for handoff evidence")
    with target.open("rb") as stream:
        actual = digest(stream)
    size = target.stat().st_size
    return {"checked": True, "present": True, "bytes": size, "sha256": actual,
            "hash_matches": size > 0 and actual == expected}


def check(contract, project_root, listing, *, candidate_root=None, download_root=None, archive=None):
    if (not isinstance(contract, dict) or set(contract) != {"schema_version", "artifacts"}
            or type(contract["schema_version"]) is not int or contract["schema_version"] != 1
            or not isinstance(contract["artifacts"], list) or not contract["artifacts"]):
        raise ValueError("Use schema_version 1 and a nonempty artifacts array")
    if not isinstance(listing, dict) or not isinstance(listing.get("files"), list):
        raise ValueError("Provide the actual host list response with a files array")
    indexed, listed_names = {}, set()
    for entry in listing["files"]:
        if not isinstance(entry, dict):
            raise ValueError("Host listing entries must be objects with path")
        name = relative(entry.get("path"))
        if name.casefold() in listed_names:
            raise ValueError("Host listing has duplicate or case-colliding paths")
        listed_names.add(name.casefold())
        indexed[name] = entry
    selected, seen = [], set()
    for item in contract["artifacts"]:
        if (not isinstance(item, dict) or set(item) - {"path", "sha256", "candidate_path", "archive_path", "download_path"}
                or not {"path", "sha256"} <= set(item)
                or not isinstance(item["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"])):
            raise ValueError("Every artifact needs path and lowercase producer SHA-256")
        name = relative(item["path"])
        if name.casefold() in seen:
            raise ValueError("Expected artifacts have duplicate or case-colliding paths")
        seen.add(name.casefold())
        selected.append((item, name))
    zipped = zipfile.ZipFile(archive) if archive else None
    try:
        members, member_names = {}, set()
        if zipped:
            for member in zipped.infolist():
                if member.is_dir():
                    continue
                name = relative(member.filename)
                if name.casefold() in member_names:
                    raise ValueError("Archive has duplicate or case-colliding members")
                member_names.add(name.casefold())
                members[name] = member
        records = []
        for item, name in selected:
            expected = item["sha256"]
            candidate = file_record(candidate_root, item.get("candidate_path", name), expected)
            current = file_record(project_root, name, expected)
            listed = indexed.get(name)
            list_matches = listed is not None and ("sha256" not in listed or listed["sha256"] == expected)
            downloaded = file_record(download_root, item.get("download_path", name), expected)
            archived = {"checked": zipped is not None, "present": False, "hash_matches": False}
            if zipped:
                member = members.get(relative(item.get("archive_path", name)))
                if member:
                    if member.file_size > 512 * 1024 * 1024:
                        raise ValueError("Selected archive member exceeds the 512 MiB read-back limit")
                    with zipped.open(member) as stream:
                        actual = digest(stream)
                    archived = {"checked": True, "present": True, "bytes": member.file_size,
                                "sha256": actual, "hash_matches": member.file_size > 0 and actual == expected}
            channels = ([downloaded] if download_root is not None else []) + ([archived] if zipped else [])
            readback = bool(channels) and all(channel["hash_matches"] for channel in channels)
            ready = current["hash_matches"] and list_matches and readback
            status = ("handoff_verified" if ready else "candidate_only" if candidate["hash_matches"] and not current["present"]
                      else "host_registration_missing" if current["hash_matches"] and not list_matches
                      else "delivery_readback_missing" if current["hash_matches"] and list_matches and not readback
                      else "missing_or_stale")
            records.append({"path": name, "producer_sha256": expected, "candidate": candidate,
                            "current_project": current, "listed_by_host": listed is not None,
                            "host_listing_matches": list_matches, "download": downloaded,
                            "archive": archived, "status": status, "handoff_verified": ready})
    finally:
        if zipped:
            zipped.close()
    return {"schema_version": 1, "handoff_verified": all(x["handoff_verified"] for x in records),
            "artifacts": records, "scientific_correctness_verified": False,
            "scope": "Declared producer hashes, actual project files, host-captured listing and local download/archive read-back only; no registration, publication, model execution or scientific acceptance"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("contract", type=Path)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--listing", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path)
    parser.add_argument("--download-root", type=Path)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args()
    try:
        result = check(json.loads(args.contract.read_text(encoding="utf-8-sig")), args.project_root,
                       json.loads(args.listing.read_text(encoding="utf-8-sig")), candidate_root=args.candidate_root,
                       download_root=args.download_root, archive=args.archive)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["handoff_verified"] else 1
    except (ValueError, OSError, zipfile.BadZipFile, RuntimeError) as exc:
        print(json.dumps({"handoff_verified": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
