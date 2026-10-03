"""Restricted local MCP tools for a separately prepared Typst project.

Line-delimited JSON-RPC on stdin/stdout; diagnostics never go to stdout. This
server can inspect local rules, apply a declared font profile, export a local
draw.io source and compile it. It does not solve models or validate paper science.
Workspace and executable paths are supplied by the host, never by the model.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import difflib
import hashlib
import html
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import stat
import subprocess
import sys
import tempfile
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zlib

from PIL import Image
import pymupdf

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import rendering_guard as guard
import summary_guard
import check_formula_integrity as formula_guard

PROJECT_ROOT = SCRIPT_DIR.parent
PROTOCOL_VERSION = "2025-06-18"
MAX_TEXT_BYTES = 4 * 1024 * 1024
MAX_RPC_BYTES = 1024 * 1024
TEXT_SUFFIXES = {".md", ".txt", ".json", ".jsonl", ".yaml", ".yml", ".typ", ".tex",
                 ".csv", ".tsv", ".svg", ".drawio", ".xml", ".log", ".bib"}
PRIVATE_PARTS = {"qa", ".git", ".ssh", ".aws", ".azure", ".gnupg", ".codex"}
IMAGE_CALL = re.compile(r'(?<![\w-])image\s*\(\s*"(?P<path>(?:[^"\\]|\\.)*)"')
IMPORT_CALL = re.compile(r'#(?:import|include)\s+"(?P<path>(?:[^"\\]|\\.)*)"')
SECRET_ASSIGNMENT = re.compile(
    r'(?im)(?:["\']?)(?:[\w-]*(?:api[_-]?key|secret|password|access[_-]?token|'
    r'refresh[_-]?token|authorization)[\w-]*)(?:["\']?)\s*[:=]\s*["\']?([^\s,;"\']+)')


class ToolError(ValueError):
    """An actionable, bounded tool failure, returned to the calling model."""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relative_parts(value: str) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ToolError("A nonempty relative file path is required")
    value = value.replace("\\", "/")
    windows = PureWindowsPath(value)
    posix = PurePosixPath(value)
    if windows.drive or windows.root or posix.is_absolute() or ":" in value:
        raise ToolError("Absolute paths, drives, schemes and alternate streams are forbidden")
    if ".." in posix.parts:
        raise ToolError("Parent traversal is forbidden")
    parts = tuple(p for p in posix.parts if p != ".")
    if not parts:
        raise ToolError("A file path is required")
    if any(p.endswith((" ", ".")) for p in parts):
        raise ToolError("Ambiguous Windows path components are forbidden")
    return parts


def private_path(parts: tuple[str, ...]) -> bool:
    for part in parts:
        p = part.lower()
        if p in PRIVATE_PARTS or p == ".env" or p.startswith(".env."):
            return True
        if re.search(r'(?:^|[._-])(?:credentials?|secrets?|tokens?|passwords?|api[_-]?keys?)(?:[._-]|$)', p):
            return True
    return False


def _is_link(path: Path) -> bool:
    info = path.lstat()
    return (stat.S_ISLNK(info.st_mode) or
            bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)))


def confined(root: Path, value: str, *, existing: bool = True, private: bool = True) -> Path:
    parts = relative_parts(value)
    if private and private_path(parts):
        raise ToolError("Private credentials, repository internals and qa paths are unavailable")
    current = root
    for part in parts:
        current = current / part
        if current.exists() or current.is_symlink():
            if _is_link(current):
                raise ToolError("Symlinks, junctions and other reparse points are forbidden")
    resolved = current.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ToolError("Path escapes the configured root") from exc
    if existing and not resolved.is_file():
        raise ToolError("Requested file does not exist")
    if resolved.exists() and resolved.is_file() and resolved.stat().st_nlink > 1:
        raise ToolError("Hard-linked files are forbidden")
    return resolved


def clean_comments(source: str) -> str:
    """Keep offsets while hiding Typst comments; preserve quoted strings."""
    out = list(source)
    i = 0
    quoted = False
    while i < len(source):
        if quoted:
            if source[i] == "\\":
                i += 2
                continue
            if source[i] == '"':
                quoted = False
        elif source[i] == '"':
            quoted = True
        elif source[i] == "`":
            length = 1
            while i + length < len(source) and source[i + length] == "`":
                length += 1
            end = source.find("`" * length, i + length)
            end = len(source) if end < 0 else end + length
            for n in range(i, end):
                if out[n] != "\n":
                    out[n] = " "
            i = end
            continue
        elif source.startswith("//", i):
            end = source.find("\n", i)
            end = len(source) if end < 0 else end
            out[i:end] = " " * (end - i)
            i = end
            continue
        elif source.startswith("/*", i):
            start = i
            depth = 1
            i += 2
            while i < len(source) and depth:
                if source.startswith("/*", i):
                    depth += 1
                    i += 2
                elif source.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            for n in range(start, i):
                if out[n] != "\n":
                    out[n] = " "
            continue
        i += 1
    return "".join(out)


def code_spans(source: str) -> list[tuple[int, int]]:
    """Recognize ordinary # expressions, including multiline function calls.

    This deliberately supports literal local images. Dynamic image/import
    expressions cannot be certified by this restricted server.
    """
    spans = []
    i = 0
    while i < len(source):
        if source[i] != "#" or i + 1 >= len(source) or not (source[i + 1].isalpha() or source[i + 1] in "({"):
            i += 1
            continue
        start = i
        i += 1
        depth = 0
        quoted = False
        while i < len(source):
            c = source[i]
            if quoted:
                if c == "\\":
                    i += 2
                    continue
                if c == '"':
                    quoted = False
            elif c == '"':
                quoted = True
            elif c in "({[":
                depth += 1
            elif c in ")}]":
                depth -= 1
                if depth < 0:
                    break
            elif c == "\n" and depth == 0:
                break
            i += 1
        spans.append((start, i))
        i += 1
    return spans


def image_calls(source: str) -> tuple[list[re.Match], list[str]]:
    cleaned = clean_comments(source)
    spans = code_spans(cleaned)
    in_code = lambda pos: any(start <= pos < end for start, end in spans)
    calls = [m for m in IMAGE_CALL.finditer(cleaned) if in_code(m.start())]
    literal_starts = {m.start() for m in calls}
    unresolved = ["Dynamic or unsupported image expression at source offset " + str(m.start())
                  for m in re.finditer(r'(?<![\w-])image\s*\(', cleaned)
                  if in_code(m.start()) and m.start() not in literal_starts]
    masked = guard._visible_code(cleaned)
    unresolved.extend("Image function alias or unsupported image member at source offset " + str(match.start())
                      for match in re.finditer(r'(?<![\w-])image(?![\w-])', masked)
                      if in_code(match.start()) and not re.match(r'image\s*\(', masked[match.start():]))
    unresolved.extend("Dynamic eval is not certified by the local literal-asset scanner"
                      for match in re.finditer(r'(?<![\w-])eval\s*\(', masked) if in_code(match.start()))
    return calls, unresolved


def decode_literal(value: str) -> str:
    try:
        result = json.loads('"' + value + '"')
    except json.JSONDecodeError as exc:
        raise ToolError("Only ordinary literal local image/import paths are supported") from exc
    if not isinstance(result, str):
        raise ToolError("Invalid path literal")
    return result


def graph_signature(data: str) -> list:
    """Compare editable cells/labels/edges/geometry, ignoring export metadata."""
    root = ET.fromstring(data)
    if root.tag == "mxGraphModel":
        graphs = [root]
    elif root.tag == "mxfile":
        graphs = []
        for diagram in root.findall("diagram"):
            model = diagram.find("mxGraphModel")
            if model is None:
                payload = (diagram.text or "").strip()
                if payload.startswith("<"):
                    model = ET.fromstring(payload)
                else:
                    inflater = zlib.decompressobj(-15)
                    decoded = inflater.decompress(base64.b64decode(payload, validate=True), MAX_TEXT_BYTES + 1)
                    if len(decoded) > MAX_TEXT_BYTES or inflater.unconsumed_tail:
                        raise ToolError("Compressed diagram exceeds the size limit")
                    model = ET.fromstring(unquote(decoded.decode("utf-8")))
            if model.tag != "mxGraphModel":
                raise ToolError("Unsupported diagram payload")
            graphs.append(model)
    else:
        raise ToolError("A draw.io mxfile or mxGraphModel is required")
    if not graphs:
        raise ToolError("The editable source contains no diagram")
    def canonical(node):
        return [node.tag, sorted(node.attrib.items()), (node.text or "").strip(),
                [canonical(child) for child in node]]
    signatures = []
    for graph in graphs:
        graph_root = graph.find("root")
        if graph_root is None:
            raise ToolError("Diagram has no cell root")
        signatures.append(sorted([canonical(node) for node in graph_root], key=lambda item: json.dumps(item)))
    return signatures


def frozen_bindings(root: Path) -> list[dict]:
    target = root / "asset-bindings.json"
    if not target.exists():
        return []
    target = confined(root, "asset-bindings.json")
    if target.stat().st_size > MAX_TEXT_BYTES:
        raise ToolError("Asset binding file exceeds the size limit")
    data = json.loads(target.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("schema_version") != 1 or not isinstance(data.get("bindings"), list):
        raise ToolError("asset-bindings.json requires schema_version 1 and a bindings list")
    result = []
    for item in data["bindings"]:
        if not isinstance(item, dict) or set(item) != {"svg", "source", "svg_sha256", "source_sha256"}:
            raise ToolError("Malformed asset binding")
        svg = confined(root, item["svg"])
        source = confined(root, item["source"])
        if svg.suffix.lower() != ".svg" or source.suffix.lower() != ".drawio":
            raise ToolError("Bindings must connect an SVG and a draw.io source")
        if not all(isinstance(item[k], str) and re.fullmatch(r"[a-f0-9]{64}", item[k]) for k in ("svg_sha256", "source_sha256")):
            raise ToolError("Asset bindings require SHA-256 hashes")
        if sha256(svg) != item["svg_sha256"] or sha256(source) != item["source_sha256"]:
            raise ToolError("Asset binding hashes do not match the initial workspace")
        result.append({**item, "svg": svg.relative_to(root).as_posix(), "source": source.relative_to(root).as_posix()})
    return result


def input_schema(**properties) -> dict:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def read_schema() -> dict:
    return {"type":"object", "properties":{
        "path":{"type":"string"},
        "start_line":{"type":"integer","minimum":1},
        "max_lines":{"type":"integer","minimum":1,"maximum":500}},
        "required":["path"],"additionalProperties":False}


TOOL_DEFINITIONS = [
    ("read_project_file", "Read project rules or registered skill references/templates. Defaults to 160 lines; use start_line/max_lines for another window and check truncated. The SHA is for the whole file. Read the stage needed, not all stages.", read_schema(), True),
    ("read_workspace_file", "Read prepared-workspace UTF-8 text. Defaults to 160 lines with explicit truncation and whole-file SHA; use start_line/max_lines for another window. inspect_rendering provides rendering decisions without rereading the full manuscript.", read_schema(), True),
    ("inspect_rendering", "Inspect actual Typst availability, declared contract fonts, local image compatibility and any declared summary contract. If main.pdf exists, report its actual summary/body page boundary.", input_schema(), True),
    ("apply_font_profile", "Apply rendering-contract.json to supported top-level main.typ font declarations only. Refuse missing font families or a change outside those declarations.", input_schema(), False),
    ("ensure_summary_page", "When rendering-contract.json declares summary requirements, insert a strong pagebreak before the unambiguous body heading in main.typ. Preserve all existing scientific text. Without a summary contract this tool makes no change; compile_and_check verifies the actual PDF boundary.", input_schema(), False),
    ("export_diagram", "Export one workspace draw.io diagram using the configured draw.io CLI to same-stem PNG at scale 3 and vector PDF. Check actual PNG DPI against the rendering contract and keep editable source.", input_schema(source={"type": "string"}), False),
    ("use_compatible_image", "Replace the specified literal SVG reference in main.typ with same-stem PNG actually produced by export_diagram. Require matching embedded draw.io cells or a startup-frozen asset binding; preserve SVG and scientific text.", input_schema(svg={"type": "string"}), False),
    ("compile_and_check", "Compile main.typ to main.pdf with the configured Typst compiler and workspace root. Refuse incompatible SVG, failed fonts/page minimum and, when required by the contract, shared or overflowing summary pages. This does not certify diagram meaning, full layout or science.", input_schema(), False),
]


class ProjectServer:
    def __init__(self, workspace: Path, compiler: Path, font_dir: Path | None = None,
                 drawio: Path | None = None, *, project_root: Path = PROJECT_ROOT):
        workspace = Path(workspace).absolute()
        if not workspace.is_dir() or _is_link(workspace):
            raise ToolError("--workspace must be an existing real directory")
        self.workspace = workspace.resolve()
        self.project_root = Path(project_root).resolve()
        if self.workspace == self.project_root or self.project_root in self.workspace.parents:
            raise ToolError("Use a separate prepared workspace outside the skill repository")
        self.compiler = Path(compiler).resolve()
        if not self.compiler.is_file():
            raise ToolError("Configured Typst executable does not exist; no installation is performed")
        self.drawio = Path(drawio).resolve() if drawio else None
        if self.drawio and not self.drawio.is_file():
            raise ToolError("Configured draw.io executable does not exist")
        self.font_dir = Path(font_dir).resolve() if font_dir else None
        if self.font_dir and not self.font_dir.is_dir():
            raise ToolError("Configured font directory does not exist")
        self.bindings = frozen_bindings(self.workspace)
        self.exports: dict[str, dict] = {}
        self.observed: dict[str, dict] = {}
        self.initialized = False
        self.env = self.process_environment()
        self.secret_values = [value for key, value in os.environ.items()
                              if re.search(r"KEY|TOKEN|SECRET|PASSWORD", key, re.I) and len(value) >= 8]
        self.vendor_files = {"vendor/skill-integrations.json"}
        self.vendor_roots = set()
        registry_path = self.project_root / "vendor/skill-integrations.json"
        if registry_path.is_file():
            registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
            for item in registry.get("skills", []):
                path = "vendor/" + item["source"] + "/" + item["path"]
                parts = relative_parts(path)
                if parts[-1] == "SKILL.md" and not private_path(parts):
                    self.vendor_files.add("/".join(parts))
                    self.vendor_roots.add(parts[:-1])

    def process_environment(self) -> dict[str, str]:
        allowed = {"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LOCALAPPDATA", "APPDATA",
                   "LANG", "LC_ALL", "LC_CTYPE"}
        env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
        paths = {str(self.compiler.parent)}
        if self.drawio:
            paths.add(str(self.drawio.parent))
        system = os.environ.get("SystemRoot") or os.environ.get("SYSTEMROOT")
        if system:
            paths.add(str(Path(system) / "System32"))
        env["PATH"] = os.pathsep.join(sorted(paths))
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def sanitize(self, text: str) -> str:
        for value in self.secret_values:
            text = text.replace(value, "[redacted]")
        text = re.sub(r'\b(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,})', "[redacted]", text)
        return SECRET_ASSIGNMENT.sub(lambda m: m.group(0).replace(m.group(1), "[redacted]"), text)

    def path(self, value: str, *, project=False, existing=True) -> Path:
        root = self.project_root if project else self.workspace
        path = confined(root, value, existing=existing)
        if path.is_file():
            key = ("project/" if project else "workspace/") + path.relative_to(root).as_posix()
            digest = sha256(path)
            record = self.observed.setdefault(key, {"before_sha256": digest, "after_sha256": digest})
            record["after_sha256"] = digest
        return path

    def read(self, path: Path) -> str:
        if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > MAX_TEXT_BYTES:
            raise ToolError("Only supported UTF-8 text files up to 4 MiB can be read")
        try:
            data = path.read_text(encoding="utf-8-sig")
        except (UnicodeError, OSError) as exc:
            raise ToolError("Requested file is not readable UTF-8 text") from exc
        if "\x00" in data:
            raise ToolError("Binary text is unavailable")
        return data

    def contract(self) -> dict:
        return guard.validate_contract(json.loads(self.read(self.path("rendering-contract.json"))))

    def run(self, args: list[str], timeout=90) -> subprocess.CompletedProcess:
        kwargs = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        try:
            process = subprocess.run(args, cwd=self.workspace, env=self.env,
                                     capture_output=True, text=True, encoding="utf-8",
                                     errors="replace", timeout=timeout, check=False, **kwargs)
        except subprocess.TimeoutExpired as exc:
            raise ToolError("Configured renderer timed out") from exc
        if process.returncode:
            message = self.sanitize((process.stderr + "\n" + process.stdout).strip())[-8000:]
            raise ToolError("Renderer failed (exit " + str(process.returncode) + "): " + message)
        return process

    def read_window(self, target: Path, start_line=1, max_lines=160) -> dict:
        if type(start_line) is not int or start_line<1 or type(max_lines) is not int or not 1<=max_lines<=500:
            raise ToolError("start_line must be positive and max_lines must be an integer from 1 to 500")
        original=self.read(target)
        if any(value in original for value in self.secret_values) or re.search(r'\b(?:sk-[A-Za-z0-9_-]{12,}|Bearer\s+[A-Za-z0-9._-]{12,})',original):
            raise ToolError('Credential-like content cannot be returned; prepare a reviewed credential-free input')
        lines=original.splitlines(keepends=True)
        if start_line>max(1,len(lines)):raise ToolError("start_line is beyond this file")
        selected=lines[start_line-1:start_line-1+max_lines]
        end=start_line+len(selected)-1
        returned=''.join(selected)
        return {"content":returned,"sha256":sha256(target),"total_lines":len(lines),
                "returned_content_sha256":hashlib.sha256(returned.encode('utf-8')).hexdigest(),"sanitized":False,
                "returned_range":[start_line,end],"truncated":start_line>1 or end<len(lines),
                "next_start_line":end+1 if end<len(lines) else None,
                "read_scope":"selected lines; file hash does not mean the full file was read"}

    def read_project_file(self, path: str, start_line=1, max_lines=160) -> dict:
        parts = relative_parts(path)
        normalized = "/".join(parts)
        vendor_reference = (PurePosixPath(normalized).suffix.lower() in {".md", ".typ", ".tex", ".json"}
                            and any(parts[:len(root)] == root and len(parts) > len(root) for root in self.vendor_roots))
        permitted = (normalized == "SKILL.md" or normalized in self.vendor_files or
                     normalized.split("/")[0] in {"references", "docs", "assets"} or vendor_reference)
        if not permitted:
            raise ToolError("Project reads are restricted to rules, reference/assets text and registered vendor skill directories")
        target = self.path(normalized, project=True)
        return {"path":normalized,**self.read_window(target,start_line,max_lines)}

    def read_workspace_file(self, path: str, start_line=1, max_lines=160) -> dict:
        target = self.path(path)
        return {"path":target.relative_to(self.workspace).as_posix(),**self.read_window(target,start_line,max_lines)}

    def sources_and_images(self) -> tuple[list[dict], list[str]]:
        visited = set()
        images = []
        issues = []
        pending = [self.path("main.typ")]
        while pending:
            source = pending.pop()
            if source in visited:
                continue
            visited.add(source)
            text = self.read(source)
            calls, unresolved = image_calls(text)
            issues.extend(unresolved)
            for match in calls:
                name = decode_literal(match["path"])
                parent = source.parent.relative_to(self.workspace)
                image = self.path((parent / name).as_posix())
                images.append({"source": source.relative_to(self.workspace).as_posix(),
                               "path": image.relative_to(self.workspace).as_posix(), "file": image})
            cleaned = clean_comments(text)
            for match in IMPORT_CALL.finditer(cleaned):
                name = decode_literal(match["path"])
                if name.startswith("@"):
                    issues.append("Package imports are not certified by this local-source tool")
                    continue
                imported = self.path((source.parent.relative_to(self.workspace) / name).as_posix())
                if imported.suffix.lower() != ".typ":
                    issues.append("Only local .typ imports can be inspected")
                else:
                    pending.append(imported)
            literal_imports = {m.start() for m in IMPORT_CALL.finditer(cleaned)}
            if any(m.start() not in literal_imports for m in re.finditer(r'#(?:import|include)\b', cleaned)):
                issues.append("Dynamic or unsupported import/include expression")
        return images, issues

    def image_checks(self, contract: dict) -> tuple[list[dict], list[str]]:
        images, issues = self.sources_and_images()
        checked = []
        for item in images:
            path = item["file"]
            result = {key: value for key, value in item.items() if key != "file"}
            if path.suffix.lower() == ".svg":
                try:
                    result.update(guard.svg_compatibility(path, engine="typst"))
                except (ET.ParseError, UnicodeError) as exc:
                    result.update(direct_embedding_ready=False, reasons=["Invalid SVG XML: " + str(exc)])
            elif path.suffix.lower() == ".png":
                with Image.open(path) as image:
                    width, height = image.size
                dpi = width * 25.4 / contract["figure_width_mm"]
                result.update(pixels=[width, height], assumed_width_mm=contract["figure_width_mm"],
                              effective_dpi=round(dpi, 2), minimum_dpi=contract["minimum_dpi"],
                              direct_embedding_ready=dpi >= contract["minimum_dpi"],
                              reasons=[] if dpi >= contract["minimum_dpi"] else ["PNG DPI is below the contract at its declared figure width"])
            else:
                result.update(direct_embedding_ready=True,
                              scope="File present; this format has no automatic visual certification")
            checked.append(result)
        return checked, issues

    def inspect_rendering(self) -> dict:
        contract = self.contract()
        source = self.read(self.path("main.typ"))
        try:
            version = self.run([str(self.compiler), "--version"], timeout=20).stdout.strip()
            available = guard.font_names(self.compiler, self.font_dir, env=self.env)
            engine_available = True
            engine_error = None
        except (ToolError, subprocess.SubprocessError, OSError) as exc:
            version, available, engine_available, engine_error = "", set(), False, self.sanitize(str(exc))
        declared, body, headings = self.declared_fonts(source, contract)
        fonts = contract["fonts"]
        images, issues = self.image_checks(contract)
        missing = sorted(family for family in set(fonts.values()) if family.casefold() not in {name.casefold() for name in available})
        summary_contract = contract.get("summary")
        summary_check = None
        if summary_contract is not None:
            pdf = self.path("main.pdf", existing=False)
            if pdf.is_file():
                summary_check = summary_guard.check_pdf(pdf, summary_contract)
            else:
                summary_check = {"passed": False, "status": "pending",
                                 "issues": ["No actual main.pdf exists yet; compile_and_check is needed"],
                                 "scope": "Declared summary requirement has not been verified on a PDF"}
        return {"contract": contract, "engine_available": engine_available,
                "compiler_version": self.sanitize(version), "engine_error": engine_error,
                "declared_font_families": {"text": body, "heading": headings},
                "declared_roles_match": declared, "profile_declarations_conform": all(declared.values()),
                "missing_font_families": missing, "requested_fonts_available": not missing and engine_available,
                "available_font_families": sorted(available), "images": images, "source_scan_issues": issues,
                "summary_contract": summary_contract, "summary_check": summary_check,
                "summary_check_required": summary_contract is not None,
                "ready_for_compile_check": engine_available and not missing and all(declared.values()) and not issues and all(i["direct_embedding_ready"] for i in images),
                "scope": "Declarations, compiler discovery and local literal assets only; no scientific or final-PDF visual certification"}

    def declared_fonts(self, source: str, contract: dict) -> tuple[dict, list, list]:
        declarations = guard._declarations(source)
        body_lines = [source[opening + 1:closing] for kind, opening, closing in declarations if kind == "body"]
        heading_lines = [source[opening + 1:closing] for kind, opening, closing in declarations if kind == "heading"]
        def families(lines):
            names = []
            for line in lines:
                match = re.search(r'\bfont:\s*(\([^)]*\)|"(?:[^"\\]|\\.)*")', line)
                if match:
                    names.extend(json.loads('"' + value + '"') for value in re.findall(r'"((?:[^"\\]|\\.)*)"', match[1]))
            return sorted(set(names))
        body = families(body_lines[:1])
        headings = families(heading_lines)
        fonts = contract["fonts"]
        has_family = lambda family, names: family.casefold() in {name.casefold() for name in names}
        declared = {"body": len(body_lines) == 1 and has_family(fonts["body"], body),
                    "latin": len(body_lines) == 1 and has_family(fonts["latin"], body),
                    "heading": bool(heading_lines) and all(has_family(fonts["heading"], families([line])) for line in heading_lines)}
        return declared, body, headings

    def apply_font_profile(self) -> dict:
        contract = self.contract()
        source = self.path("main.typ")
        original = source.read_bytes()
        old_text = original.decode("utf-8-sig")
        def prose(text):
            spans = []
            for _, opening, closing in guard._declarations(text):
                start = text.rfind("\n", 0, opening) + 1
                end = text.find("\n", closing + 1)
                spans.append((start, len(text) if end < 0 else end + 1))
            for start, end in sorted(spans, reverse=True):
                text = text[:start] + text[end:]
            return text
        try:
            result = guard.apply_profile(source, contract, self.compiler, self.font_dir, env=self.env)
            new_text = source.read_bytes().decode("utf-8-sig")
            if prose(old_text) != prose(new_text):
                raise ToolError("Font helper changed content outside supported font declarations")
        except Exception:
            if source.read_bytes() != original:
                source.write_bytes(original)
            raise
        self.path("main.typ")
        return {**result, "path": "main.typ", "before_sha256": hashlib.sha256(original).hexdigest(),
                "after_sha256": sha256(source), "scientific_text_preserved": True}

    def ensure_summary_page(self) -> dict:
        contract = self.contract()
        summary_contract = contract.get("summary")
        if summary_contract is None:
            return {"changed": False, "status": "not_required", "summary_check_required": False,
                    "scope": "No summary contract was declared; no page or source text was changed"}
        source = self.path("main.typ")
        original = source.read_bytes()
        old_text = original.decode("utf-8-sig")
        try:
            result = summary_guard.ensure_separation(source, summary_contract)
            new_text = source.read_bytes().decode("utf-8-sig")
            edits = [item for item in difflib.SequenceMatcher(a=old_text, b=new_text, autojunk=False).get_opcodes() if item[0] != "equal"]
            if edits and (len(edits) != 1 or edits[0][0] != "insert" or
                          not re.fullmatch(r'\s*#pagebreak\(\)\s*', new_text[edits[0][3]:edits[0][4]])):
                raise ToolError("Summary helper changed existing source content instead of only inserting a pagebreak")
        except Exception:
            if source.read_bytes() != original:
                source.write_bytes(original)
            raise
        self.path("main.typ")
        return {**result, "path": "main.typ", "summary_check_required": True,
                "before_sha256": hashlib.sha256(original).hexdigest(), "after_sha256": sha256(source),
                "scientific_text_preserved": True,
                "scope": "A supported source pagebreak only; actual summary length and PDF separation require compile_and_check"}

    def validate_diagram_resources(self, text: str, signatures: list) -> None:
        root = ET.fromstring(text)
        values = [value for node in root.iter() for value in node.attrib.values()]
        def leaves(item):
            if isinstance(item, (list, tuple)):
                for child in item:
                    yield from leaves(child)
            elif isinstance(item, str):
                yield item
        # Compressed diagrams must pass the same resource checks after decoding.
        values.extend(leaves(signatures))
        for value in values:
            value = html.unescape(value)
            if re.search(r'<\s*(?:script|iframe)|javascript:|\bon\w+\s*=', value, re.I):
                raise ToolError("Active HTML content is not supported in diagram exports")
            resources = re.findall(r'\bimage=([^;]+)', value)
            resources += re.findall(r'<img[^>]+src\s*=\s*["\']([^"\']+)', value, re.I)
            for resource in resources:
                if not resource.startswith("data:image/"):
                    raise ToolError("Only bundled data:image resources are supported by the restricted draw.io export")

    def export_diagram(self, source: str) -> dict:
        if not self.drawio:
            raise ToolError("draw.io CLI is unavailable; host must supply --drawio for a real export")
        contract = self.contract()
        drawing = self.path(source)
        if drawing.suffix.lower() != ".drawio":
            raise ToolError("export_diagram requires a workspace .drawio source")
        text = self.read(drawing)
        signatures = graph_signature(text)
        if len(signatures) != 1:
            raise ToolError("This exporter accepts one diagram per .drawio source")
        self.validate_diagram_resources(text, signatures)
        digest = sha256(drawing)
        png = self.path(drawing.with_suffix(".png").relative_to(self.workspace).as_posix(), existing=False)
        pdf = self.path(drawing.with_suffix(".pdf").relative_to(self.workspace).as_posix(), existing=False)
        with tempfile.TemporaryDirectory(prefix=".project-export-", dir=self.workspace) as temporary:
            tmp_png = Path(temporary) / "diagram.png"
            tmp_pdf = Path(temporary) / "diagram.pdf"
            self.run([str(self.drawio), "--export", "--format", "png", "--scale", "3", "--crop", "--output", str(tmp_png), str(drawing)], timeout=120)
            self.run([str(self.drawio), "--export", "--format", "pdf", "--crop", "--output", str(tmp_pdf), str(drawing)], timeout=120)
            if not tmp_png.is_file() or not tmp_pdf.is_file():
                raise ToolError("draw.io exited without both expected export files")
            with Image.open(tmp_png) as image:
                width, height = image.size
                image.verify()
            dpi = width * 25.4 / contract["figure_width_mm"]
            if dpi < contract["minimum_dpi"]:
                raise ToolError("Exported PNG is too small: %.2f DPI at %.2f mm; minimum %.2f" % (dpi, contract["figure_width_mm"], contract["minimum_dpi"]))
            with pymupdf.open(tmp_pdf) as document:
                if not len(document):
                    raise ToolError("Exported PDF has no page")
            if sha256(drawing) != digest:
                raise ToolError("Editable diagram changed during export; artifacts were not accepted")
            self.path(png.relative_to(self.workspace).as_posix(), existing=False)
            self.path(pdf.relative_to(self.workspace).as_posix(), existing=False)
            tmp_png.replace(png)
            tmp_pdf.replace(pdf)
        record = {"source": drawing.relative_to(self.workspace).as_posix(), "source_sha256": digest,
                  "png": png.relative_to(self.workspace).as_posix(), "png_sha256": sha256(png),
                  "pdf": pdf.relative_to(self.workspace).as_posix(), "pdf_sha256": sha256(pdf),
                  "pixels": [width, height], "scale": 3, "effective_dpi": round(dpi, 2),
                  "assumed_width_mm": contract["figure_width_mm"], "minimum_dpi": contract["minimum_dpi"]}
        self.exports[record["source"]] = record
        self.path(record["source"])
        self.path(record["png"])
        self.path(record["pdf"])
        return {"passed": True, **record, "scope": "Actual CLI export and file/DPI checks; diagram meaning requires review"}

    def same_source(self, svg: Path, drawing: Path) -> str:
        svg_text = self.read(svg)
        root = ET.fromstring(svg_text)
        embedded = root.attrib.get("content")
        if embedded:
            candidates = [embedded, unquote(embedded), html.unescape(embedded)]
            expected = graph_signature(self.read(drawing))
            for candidate in candidates:
                try:
                    if graph_signature(candidate) == expected:
                        return "embedded editable cells, labels, edges, styles and geometry match"
                except (ValueError, ET.ParseError, zlib.error):
                    pass
            raise ToolError("SVG embedded editable source does not match this draw.io graph")
        for binding in self.bindings:
            if binding["svg"] == svg.relative_to(self.workspace).as_posix() and binding["source"] == drawing.relative_to(self.workspace).as_posix():
                if sha256(svg) == binding["svg_sha256"] and sha256(drawing) == binding["source_sha256"]:
                    return "startup-frozen host asset binding and both source hashes match"
        raise ToolError("SVG has no matching editable metadata or startup-frozen asset binding; verify its source before replacement")

    def use_compatible_image(self, svg: str) -> dict:
        old_image = self.path(svg)
        if old_image.suffix.lower() != ".svg":
            raise ToolError("Specify the exact workspace SVG to adapt")
        drawing = self.path(old_image.with_suffix(".drawio").relative_to(self.workspace).as_posix())
        record = self.exports.get(drawing.relative_to(self.workspace).as_posix())
        if not record:
            raise ToolError("Call export_diagram for this same-stem editable source first")
        png = self.path(record["png"])
        if sha256(drawing) != record["source_sha256"] or sha256(png) != record["png_sha256"]:
            raise ToolError("Export source or PNG changed; repeat the real export before adapting")
        evidence = self.same_source(old_image, drawing)
        source = self.path("main.typ")
        old_bytes = source.read_bytes()
        old_text = old_bytes.decode("utf-8-sig")
        calls, _ = image_calls(old_text)
        replacements = []
        for match in calls:
            name = decode_literal(match["path"])
            referenced = self.path(name)
            if referenced == old_image:
                new_name = str(PurePosixPath(name.replace("\\", "/")).with_suffix(".png"))
                replacements.append((match.start("path"), match.end("path"), json.dumps(new_name, ensure_ascii=False)[1:-1]))
        if not replacements:
            # Repeated requests are common in tool loops. Treat a verified
            # already-applied replacement as idempotent, never trust an
            # arbitrary same-name PNG without the export/hash/source checks above.
            for match in calls:
                if self.path(decode_literal(match["path"]))==png:
                    return {"changed":False,"replacements":0,"status":"already_using_verified_export",
                            "png":record["png"],"source_evidence":evidence,
                            "before_sha256":hashlib.sha256(old_bytes).hexdigest(),"after_sha256":sha256(source),
                            "next_step":"compile_and_check; do not repeat a completed image adaptation"}
            raise ToolError("The specified SVG is not a supported literal image reference in main.typ")
        new_text = old_text
        for start, end, value in reversed(replacements):
            new_text = new_text[:start] + value + new_text[end:]
        source.write_bytes((b'\xef\xbb\xbf' if old_bytes.startswith(b'\xef\xbb\xbf') else b'') + new_text.encode("utf-8"))
        self.path("main.typ")
        return {"changed": True, "replacements": len(replacements), "svg": old_image.relative_to(self.workspace).as_posix(),
                "png": record["png"], "source_evidence": evidence,
                "before_sha256": hashlib.sha256(old_bytes).hexdigest(), "after_sha256": sha256(source),
                "scope": "Specified image path literals only; SVG/editable originals and all other source text preserved"}

    def compile_and_check(self) -> dict:
        contract = self.contract()
        source = self.path("main.typ")
        formula_source_check = formula_guard.check_source(self.read(source), "main.typ")
        if formula_source_check['status']=='fail':
            return {'passed':False,'compiled':False,'formula_status':'fail',
                    'formula_source_check':formula_source_check,
                    'reason':'Repair fragmented mathematical relations in the responsible writing source before compilation; do not modify unrelated manuscripts'}
        images, issues = self.image_checks(contract)
        incompatible = [image for image in images if not image["direct_embedding_ready"]]
        if incompatible or issues:
            return {"passed": False, "compiled": False, "reason": "Resolve incompatible or uninspectable assets before compilation",
                    "images": images, "source_scan_issues": issues}
        declared, _, _ = self.declared_fonts(self.read(source), contract)
        if not all(declared.values()):
            return {"passed": False, "compiled": False,
                    "reason": "Main font declarations do not match rendering-contract.json; apply the declared font profile first",
                    "declared_roles_match": declared, "images": images}
        target = self.path("main.pdf", existing=False)
        with tempfile.TemporaryDirectory(prefix=".project-compile-", dir=self.workspace) as temporary:
            output = Path(temporary) / "main.pdf"
            args = [str(self.compiler), "compile", "--root", str(self.workspace)]
            if self.font_dir:
                args += ["--font-path", str(self.font_dir)]
            args += [str(source), str(output)]
            process = self.run(args, timeout=180)
            if not output.is_file():
                raise ToolError("Typst exited without an actual PDF")
            result = guard.pdf_font_check(output, contract)
            summary_contract = contract.get("summary")
            summary_check = summary_guard.check_pdf(output, summary_contract) if summary_contract is not None else None
            formula_pdf_check = formula_guard.check_pdf(output)
            formula_status = ('fail' if formula_pdf_check['status']=='fail' else
                              'review' if formula_source_check['status']=='review' or formula_pdf_check['status']=='review' else 'pass')
            font_and_page_passed = bool(result["passed"])
            result = {**result, "font_and_page_check_passed": font_and_page_passed,
                      "summary_contract": summary_contract, "summary_check": summary_check,
                      "summary_check_required": summary_contract is not None,
                      'formula_source_check':formula_source_check,'formula_pdf_check':formula_pdf_check,
                      'formula_status':formula_status,'formula_review_required':formula_status=='review',
                      "passed": font_and_page_passed and (summary_check is None or bool(summary_check["passed"])) and formula_status!='fail'}
            # A failed candidate must not replace a previously accepted output.
            if result["passed"]:
                self.path("main.pdf", existing=False)
                output.replace(target)
                self.path("main.pdf")
            warnings = self.sanitize(process.stderr.strip())[-8000:]
        return {**result, "compiled": True, "output_accepted": bool(result["passed"]),
                "path": "main.pdf" if result["passed"] else None, "compiler_warnings": warnings,
                "images": images, "source_scan_issues": issues,
                "next_step":"report_results; rendering-contract steps complete, other acceptance scopes remain separate" if result['passed'] else 'address_failed_check',
                "scope": "Actual compilation, font family/page/declared summary checks and refusal of supported severe formula-fragmentation patterns; formula warnings require review. No full layout, diagram meaning or mathematical/scientific certification"}

    def event(self, name: str, result: dict, is_error: bool) -> None:
        summary = {key: result[key] for key in ("passed", "changed", "compiled", "output_accepted", "pages", "replacements", "ready_for_compile_check", "scientific_text_preserved") if key in result}
        if "error" in result:
            summary["error"] = self.sanitize(str(result["error"]))[:500]
        if isinstance(result.get("summary_check"), dict):
            summary["summary_passed"] = result["summary_check"].get("passed")
            summary["summary_status"] = result["summary_check"].get("status")
        for key in ('formula_status','formula_review_required'):
            if key in result:summary[key]=result[key]
        if name in {'read_project_file','read_workspace_file'}:
            for key in ('path','returned_range','total_lines','truncated','sha256','returned_content_sha256','sanitized'):
                if key in result:
                    summary[key]=result[key]
        summary["is_error"] = is_error
        record = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "tool": name,
                  "result_summary": summary, "source_hashes": self.observed}
        target = confined(self.workspace, "project-tool-events.jsonl", existing=False)
        with target.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    def call_tool(self, name: str, arguments: dict) -> dict:
        self.observed = {}
        known = {item[0]: item[2] for item in TOOL_DEFINITIONS}
        is_error = False
        try:
            audit = confined(self.workspace, "project-tool-events.jsonl", existing=False)
            if audit.exists() and not audit.is_file():
                raise ToolError("The tool event path must be a regular file")
            if name not in known:
                raise ToolError("Unknown project tool")
            schema = known[name]
            if not isinstance(arguments,dict) or not set(schema['required'])<=set(arguments) or set(arguments)-set(schema['properties']):
                raise ToolError("Arguments must match required and optional fields of the advertised tool schema")
            for key,value in arguments.items():
                spec=schema['properties'][key]
                if spec['type']=='string' and not isinstance(value,str):raise ToolError('File path arguments must be strings')
                if spec['type']=='integer' and (type(value) is not int or value<spec.get('minimum',value) or value>spec.get('maximum',value)):
                    raise ToolError('Invalid integer field '+key)
            result = getattr(self, name)(**arguments)
            is_error = result.get("passed") is False
        except (ToolError, ValueError, RuntimeError, OSError, ET.ParseError, zlib.error, subprocess.SubprocessError) as exc:
            result = {"error": self.sanitize(str(exc)), "passed": False}
            is_error = True
        try:
            self.event(name if name in known else "unknown", result, is_error)
        except (ToolError, OSError) as exc:
            # Auditing is necessary for acceptance; do not conceal a lost event.
            result = {"error": "Could not record project tool event: " + self.sanitize(str(exc)), "passed": False}
            is_error = True
        return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "structuredContent": result, "isError": is_error}

    def dispatch(self, request) -> dict | None:
        if not isinstance(request, dict) or request.get("jsonrpc") != "2.0" or not isinstance(request.get("method"), str):
            return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
        identifier = request.get("id")
        method = request["method"]
        params = request.get("params", {})
        if "id" not in request:
            return None
        def error(code, message):
            return {"jsonrpc": "2.0", "id": identifier, "error": {"code": code, "message": message}}
        if not isinstance(params, dict):
            return error(-32602, "params must be an object")
        if method == "initialize":
            self.initialized = True
            result = {"protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}},
                      "serverInfo": {"name": "mathmodel-paper-project", "version": "1.0.0"},
                      "instructions": "Read SKILL.md and references/rendering-contract.md through read_project_file. Then read the workspace contract and inspect real feedback. Registered vendor skill directories include readable .md/.typ/.tex/.json templates and references; vendor/skill-integrations.json lists the entrypoints. Declared summary requirements are checked on the actual PDF. This server adapts rendering only; it does not certify full paper science or visual layout."}
        elif method == "ping":
            result = {}
        elif not self.initialized:
            return error(-32002, "Initialize the MCP connection first")
        elif method == "tools/list":
            result = {"tools": [{"name": name, "description": description, "inputSchema": schema,
                                  "annotations": {"readOnlyHint": readonly, "destructiveHint": False,
                                                  "idempotentHint": True, "openWorldHint": False}}
                                 for name, description, schema, readonly in TOOL_DEFINITIONS]}
        elif method == "tools/call":
            if not isinstance(params.get("name"), str):
                return error(-32602, "A tool name is required")
            result = self.call_tool(params["name"], params.get("arguments", {}))
        else:
            return error(-32601, "Method not found")
        return {"jsonrpc": "2.0", "id": identifier, "result": result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--compiler", type=Path, required=True)
    parser.add_argument("--font-dir", type=Path)
    parser.add_argument("--drawio", type=Path)
    args = parser.parse_args()
    if hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    try:
        server = ProjectServer(args.workspace, args.compiler, args.font_dir, args.drawio)
    except (ToolError, ValueError, OSError) as exc:
        print("Project server configuration error: " + str(exc), file=sys.stderr)
        return 2
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            if len(line.encode("utf-8")) > MAX_RPC_BYTES:
                raise ValueError("JSON-RPC line exceeds 1 MiB")
            request = json.loads(line)
            response = server.dispatch(request)
        except (ValueError, json.JSONDecodeError):
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error or oversized input"}}
        except Exception as exc:
            print("Project server request failed: " + server.sanitize(str(exc)), file=sys.stderr)
            identifier = request.get("id") if isinstance(request, dict) else None
            response = {"jsonrpc": "2.0", "id": identifier, "error": {"code": -32603, "message": "Internal project tool error"}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
