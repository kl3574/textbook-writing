#!/usr/bin/env python3
"""Create a new LaTeX textbook project from the bundled or a user template.

The initializer only creates files.  It never runs TeX, template commands, or
template code, and it never installs dependencies.  The output directory must
not exist; the project is assembled in a sibling staging directory and renamed
only after all files and the creation receipt have been written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = "TextbookLatexTemplate/v1"
PROFILE = "latex-pdf"
RECEIPT_NAME = "textbook-template.receipt.json"
SUPPORTED_ENGINES = ("pdflatex", "xelatex", "lualatex")
DEFAULT_LANGUAGE = "zh"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILTIN_ROOT = PROJECT_ROOT / "assets" / "latex-template"
BUILTIN_MANIFEST = BUILTIN_ROOT / "template-source.json"
BUILTIN_PREAMBLE_FILES = (
    "preamble/packages.tex",
    "preamble/style.tex",
    "preamble/macros.tex",
    "preamble/boxes.tex",
    "preamble/code.tex",
)
BUILTIN_INPUT_FILES = ("main.tex",) + BUILTIN_PREAMBLE_FILES

# The snapshot is pinned.  Built-in projects apply only the documented derived
# changes (bilingual fonts, pinned pgfplots compatibility, and header height); a
# missing anchor is an error, not a silent guess.
PDFLATEX_FONT_BLOCK = """% ------------- For Encoding & fonts ----------------
\\usepackage[T1]{fontenc}
\\usepackage[utf8]{inputenc}
\\usepackage{lmodern}
\\usepackage[scaled=.92]{helvet}   % sans-serif for headings
\\usepackage{microtype}"""
CTEX_FONT_BLOCK = """% ------------- Fonts: XeLaTeX + ctex (Fandol CJK, Latin Modern Latin) ----------------
\\usepackage[fontset=fandol]{ctex}
\\usepackage{microtype}"""
PGFPLOTS_NEWEST = "\\pgfplotsset{compat=newest}"
PGFPLOTS_PINNED = "\\pgfplotsset{compat=1.18}"
GEOMETRY_ORIGINAL = "\\usepackage[margin=1in, headheight=15pt]{geometry}"
GEOMETRY_FIXED = "\\usepackage[margin=1in, headheight=22pt]{geometry}"

IGNORED_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".ipynb_checkpoints",
        ".cache",
    }
)
IGNORED_FILE_SUFFIXES = (
    ".aux",
    ".log",
    ".out",
    ".toc",
    ".lof",
    ".lot",
    ".fls",
    ".fdb_latexmk",
    ".synctex",
    ".synctex.gz",
    ".bcf",
    ".run.xml",
    ".blg",
    ".nav",
    ".snm",
    ".vrb",
)

TEX_ESCAPES = {
    "\\": "\\textbackslash{}",
    "{": "\\{",
    "}": "\\}",
    "$": "\\$",
    "&": "\\&",
    "#": "\\#",
    "^": "\\textasciicircum{}",
    "_": "\\_",
    "%": "\\%",
    "~": "\\textasciitilde{}",
}

_MAGIC_PROGRAM = re.compile(
    r"^\s*%\s*!TEX\s+(?:TS-)?program\s*=\s*([A-Za-z]+)\s*$",
    re.IGNORECASE,
)


class InitializerError(RuntimeError):
    """A user-facing initialization failure."""


class ProjectPlan:
    def __init__(
        self,
        source_info: dict[str, object],
        entry: str,
        engine: str | None,
        engine_source: str | None,
        language: str | None,
        copies: dict[str, Path] | None = None,
        writes: dict[str, bytes] | None = None,
        directories: set[str] | None = None,
        source_hashes: dict[str, str] | None = None,
    ) -> None:
        self.source_info = source_info
        self.entry = entry
        self.engine = engine
        self.engine_source = engine_source
        self.language = language
        self.copies = copies if copies is not None else {}
        self.writes = writes if writes is not None else {}
        self.directories = directories if directories is not None else set()
        self.source_hashes = source_hashes if source_hashes is not None else {}


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(path))))


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _check_metadata_text(value: str, option: str) -> None:
    if "\x00" in value:
        raise InitializerError(f"{option} must not contain NUL characters")
    if any(character in value for character in "\n\r\v\f\u0085\u2028\u2029"):
        raise InitializerError(f"{option} must be a single line (no newline characters)")


def _escape_tex(value: str) -> str:
    return "".join(TEX_ESCAPES.get(character, character) for character in value)


def _relative_parts(value: str, label: str) -> tuple[str, ...]:
    if not value:
        raise InitializerError(f"{label} must not be empty")
    if "\x00" in value:
        raise InitializerError(f"{label} contains a NUL character")
    candidate = Path(value)
    if candidate.is_absolute():
        raise InitializerError(f"{label} must be relative: {value!r}")
    parts = candidate.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise InitializerError(f"{label} must stay inside the template root: {value!r}")
    return parts


def _normalize_main(value: str) -> str:
    parts = _relative_parts(value, "--main")
    if not parts[-1].lower().endswith(".tex"):
        raise InitializerError(f"--main must name a .tex file: {value!r}")
    return "/".join(parts)


def _validate_output(output: Path) -> Path:
    output = _absolute(output)
    if os.path.lexists(output):
        raise InitializerError(f"output already exists (refusing to overwrite): {output}")
    parent = output.parent
    if not parent.exists():
        raise InitializerError(f"output parent directory does not exist: {parent}")
    if not parent.is_dir():
        raise InitializerError(f"output parent is not a directory: {parent}")
    return output


def _validate_template_root(root: Path) -> Path:
    root = _absolute(root)
    if not os.path.lexists(root):
        raise InitializerError(f"template directory does not exist: {root}")
    if root.is_symlink():
        raise InitializerError(f"template directory must not be a symlink: {root}")
    if not root.is_dir():
        raise InitializerError(f"template path is not a directory: {root}")
    return root


def _ensure_disjoint(source_root: Path, output: Path) -> None:
    source = Path(os.path.realpath(source_root))
    destination = Path(os.path.realpath(output))
    if _is_within(destination, source):
        raise InitializerError("output must not be inside the template directory")
    if _is_within(source, destination):
        raise InitializerError("template directory must not be inside the output directory")


def _replace_required(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise InitializerError(
            f"built-in template snapshot changed: expected {label} in a pinned file"
        )
    return text.replace(old, new)


def _read_builtin(relative: str) -> bytes:
    _relative_parts(relative, "built-in template path")
    path = BUILTIN_ROOT / relative
    if path.is_symlink() or not path.is_file():
        raise InitializerError(f"built-in template file is missing or unsafe: {relative}")
    return path.read_bytes()


def _load_builtin_manifest() -> tuple[dict[str, object], dict[str, str], str]:
    if BUILTIN_MANIFEST.is_symlink() or not BUILTIN_MANIFEST.is_file():
        raise InitializerError(
            f"built-in template manifest is missing or unsafe: {BUILTIN_MANIFEST}"
        )
    raw = BUILTIN_MANIFEST.read_bytes()
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InitializerError(f"invalid built-in template manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise InitializerError("invalid built-in template manifest: expected an object")
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        raise InitializerError("invalid built-in template manifest: missing files map")

    inventory: dict[str, str] = {}
    for relative, expected in sorted(files.items()):
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise InitializerError("invalid built-in template manifest entry")
        _relative_parts(relative, "built-in template manifest path")
        path = BUILTIN_ROOT / relative
        if path.is_symlink() or not path.is_file():
            raise InitializerError(f"built-in template file is missing or unsafe: {relative}")
        actual = _sha256_file(path)
        if actual != expected:
            raise InitializerError(
                f"built-in template snapshot changed: hash mismatch for {relative}"
            )
        inventory[relative] = actual

    for relative in BUILTIN_INPUT_FILES:
        if relative not in inventory:
            raise InitializerError(
                f"built-in template manifest does not list required file: {relative}"
            )
    return manifest, inventory, _sha256_bytes(raw)


def _builtin_source_info(
    manifest: dict[str, object], inventory: dict[str, str], manifest_sha: str
) -> dict[str, object]:
    origin = manifest.get("source")
    captured_at = manifest.get("captured_at")
    return {
        "kind": "builtin",
        "path": str(BUILTIN_ROOT),
        "snapshot": str(BUILTIN_ROOT),
        "template_origin": origin if isinstance(origin, str) else None,
        "captured_at": captured_at if isinstance(captured_at, str) else None,
        "snapshot_manifest": "template-source.json",
        "snapshot_manifest_sha256": manifest_sha,
        "files": dict(sorted(inventory.items())),
    }


def _builtin_main_zh(title: str, course: str, engine: str) -> bytes:
    lines = [
        "% ===============================================================",
        "% 教材 LaTeX 项目骨架（空白；由 init_latex_project.py 生成）",
        "% 正文、学习目标和讲次内容均待撰写，不是完整教材。",
        f"% 建议编译：{engine} -no-shell-escape -interaction=nonstopmode -halt-on-error main.tex",
        "% ===============================================================",
        "\\documentclass[11pt,a4paper]{article}",
        "",
        "% ----- 课程元信息（纯文本；由 --title / --course-name 提供） -----",
        "\\newcommand{\\coursecode}{课程代码（待填写）}",
        f"\\newcommand{{\\coursename}}{{{course}}}",
        "\\newcommand{\\lecnumber}{1}",
        f"\\newcommand{{\\lectitle}}{{{title}}}",
        "\\newcommand{\\lecturer}{教师（待填写）}",
        "\\newcommand{\\semester}{学期（待填写）}",
        "",
        "% ----- 导言区加载顺序与模板一致 -----",
        "\\input{preamble/packages}",
        "\\input{preamble/style}",
        "\\input{preamble/macros}",
        "\\input{preamble/boxes}",
        "\\input{preamble/code}",
        "",
        "\\begin{document}",
        "",
        "\\makelecturetitle",
        "",
        "\\begin{objectives}",
        "本讲学习目标待撰写。请在此列出 3--6 条可检验的学习目标。",
        "\\end{objectives}",
        "",
        "\\tableofcontents",
        "\\bigskip",
        "",
        "\\input{sections/01_chapter}",
        "",
        "\\end{document}",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _builtin_main_en(title: str, course: str, engine: str) -> bytes:
    lines = [
        "% ===============================================================",
        "% Textbook LaTeX project skeleton (blank; generated by init_latex_project.py)",
        "% Body text, learning objectives, and lecture content are to be written.",
        f"% Suggested build: {engine} -no-shell-escape -interaction=nonstopmode -halt-on-error main.tex",
        "% ===============================================================",
        "\\documentclass[11pt,a4paper]{article}",
        "",
        "% ----- Course metadata (plain text; from --title / --course-name) -----",
        "\\newcommand{\\coursecode}{Course code (to be filled)}",
        f"\\newcommand{{\\coursename}}{{{course}}}",
        "\\newcommand{\\lecnumber}{1}",
        f"\\newcommand{{\\lectitle}}{{{title}}}",
        "\\newcommand{\\lecturer}{Instructor (to be filled)}",
        "\\newcommand{\\semester}{Term (to be filled)}",
        "",
        "% ----- Preamble order matches the template -----",
        "\\input{preamble/packages}",
        "\\input{preamble/style}",
        "\\input{preamble/macros}",
        "\\input{preamble/boxes}",
        "\\input{preamble/code}",
        "",
        "\\begin{document}",
        "",
        "\\makelecturetitle",
        "",
        "\\begin{objectives}",
        "Learning objectives are to be written. List 3--6 checkable objectives here.",
        "\\end{objectives}",
        "",
        "\\tableofcontents",
        "\\bigskip",
        "",
        "\\input{sections/01_chapter}",
        "",
        "\\end{document}",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _builtin_chapter(language: str) -> bytes:
    if language == "zh":
        lines = [
            "% 本章是空白写作骨架，请替换为实际教材正文。",
            "\\section{第 1 章（待撰写）}",
            "",
            "\\begin{notebox}[待撰写]",
            "本章正文尚未撰写。请在此加入定义、定理、证明、算例与习题。",
            "\\end{notebox}",
            "",
        ]
    else:
        lines = [
            "% This chapter is a blank writing skeleton; replace it with textbook prose.",
            "\\section{Chapter 1 (to be written)}",
            "",
            "\\begin{notebox}[To be written]",
            "This chapter has no body yet. Add definitions, theorems, proofs, examples, and exercises here.",
            "\\end{notebox}",
            "",
        ]
    return "\n".join(lines).encode("utf-8")


def _builtin_packages(language: str) -> bytes:
    text = _read_builtin("preamble/packages.tex").decode("utf-8")
    text = _replace_required(text, PGFPLOTS_NEWEST, PGFPLOTS_PINNED, "pgfplots compat setting")
    text = _replace_required(
        text, GEOMETRY_ORIGINAL, GEOMETRY_FIXED, "geometry headheight setting"
    )
    if language == "zh":
        text = _replace_required(
            text, PDFLATEX_FONT_BLOCK, CTEX_FONT_BLOCK, "pdfLaTeX font block"
        )
    return text.encode("utf-8")


def _builtin_style(language: str) -> bytes:
    text = _read_builtin("preamble/style.tex").decode("utf-8")
    if language == "zh":
        text = _replace_required(
            text,
            "Lecture \\lecnumber: \\lectitle",
            "第 \\lecnumber 讲：\\lectitle",
            "lecture heading",
        )
        text = _replace_required(
            text,
            "Lecturer: \\lecturer\\hfill Compiled: \\today",
            "主讲：\\lecturer\\hfill 编译日期：\\today",
            "lecturer/date labels",
        )
        text = _replace_required(
            text,
            "Page \\thepage\\ of \\pageref{LastPage}",
            "第 \\thepage\\ 页，共 \\pageref{LastPage} 页",
            "page label",
        )
    return text.encode("utf-8")


def _builtin_boxes(language: str) -> bytes:
    text = _read_builtin("preamble/boxes.tex").decode("utf-8")
    if language == "zh":
        text = _replace_required(
            text, "Learning objectives", "学习目标", "objectives box label"
        )
    return text.encode("utf-8")


def _builtin_engine(language: str, explicit: str | None) -> tuple[str, str]:
    default = "xelatex" if language == "zh" else "pdflatex"
    if explicit is None:
        return default, "builtin"
    if language == "zh" and explicit == "pdflatex":
        raise InitializerError(
            "built-in zh uses ctex/Fandol and cannot be compiled with pdflatex; "
            "use --engine xelatex or lualatex (or provide --template for a custom setup)"
        )
    if language == "en" and explicit != "pdflatex":
        raise InitializerError(
            "built-in en keeps the pdfLaTeX font setup; use --engine pdflatex "
            "or provide --template for a custom engine"
        )
    return explicit, "explicit"


def _build_builtin_plan(
    language: str,
    title: str,
    course: str,
    explicit_engine: str | None,
) -> ProjectPlan:
    _check_metadata_text(title, "--title")
    _check_metadata_text(course, "--course-name")
    escaped_title = _escape_tex(title)
    escaped_course = _escape_tex(course)
    engine, engine_source = _builtin_engine(language, explicit_engine)

    manifest, inventory, manifest_sha = _load_builtin_manifest()
    source_info = _builtin_source_info(manifest, inventory, manifest_sha)

    main = (
        _builtin_main_zh(escaped_title, escaped_course, engine)
        if language == "zh"
        else _builtin_main_en(escaped_title, escaped_course, engine)
    )
    writes = {
        "main.tex": main,
        "preamble/packages.tex": _builtin_packages(language),
        "preamble/style.tex": _builtin_style(language),
        "preamble/boxes.tex": _builtin_boxes(language),
        "preamble/macros.tex": _read_builtin("preamble/macros.tex"),
        "preamble/code.tex": _read_builtin("preamble/code.tex"),
        "sections/01_chapter.tex": _builtin_chapter(language),
    }
    return ProjectPlan(
        source_info=source_info,
        entry="main.tex",
        engine=engine,
        engine_source=engine_source,
        language=language,
        writes=writes,
        source_hashes={relative: inventory[relative] for relative in BUILTIN_INPUT_FILES},
    )


def _is_ignored_dir(name: str) -> bool:
    return name in IGNORED_DIR_NAMES or name.startswith("_minted-")


def _is_ignored_file(name: str) -> bool:
    return any(name.lower().endswith(suffix) for suffix in IGNORED_FILE_SUFFIXES)


def _raise_walk_error(error: OSError) -> None:
    raise error


def _literal_input_paths(files: dict[str, Path]) -> set[str]:
    """Keep explicit TeX inputs even when their suffix resembles a build cache.

    This recognizes literal paths, not arbitrary TeX macro expansion. The final
    build remains the dependency-closure check for a custom template.
    """
    referenced: set[str] = set()
    for relative, path in files.items():
        if path.suffix.lower() not in {".tex", ".sty", ".cls", ".ltx"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        text = "\n".join(_strip_tex_comment(line) for line in text.splitlines())
        tokens = re.findall(r"\{([^{}\r\n]+)\}", text)
        tokens.extend(re.findall(r"\\(?:input|include)\s+([^\s{}%]+)", text))
        for token in tokens:
            token = token.strip()
            if not token or "\\" in token or Path(token).is_absolute():
                continue
            for base in (Path(), Path(relative).parent):
                candidate = Path(os.path.normpath(str(base / token))).as_posix()
                if candidate in files:
                    referenced.add(candidate)
    return referenced


def _scan_template(
    root: Path,
) -> tuple[dict[str, Path], set[str], list[str], dict[str, str]]:
    files: dict[str, Path] = {}
    directories: set[str] = set()
    skipped: list[str] = []
    hashes: dict[str, str] = {}

    for directory, dirnames, filenames in os.walk(
        root, topdown=True, followlinks=False, onerror=_raise_walk_error
    ):
        current = Path(directory)
        relative_dir = current.relative_to(root)
        dirnames.sort()
        for name in list(dirnames):
            path = current / name
            if path.is_symlink():
                raise InitializerError(f"template contains a symlink: {path.relative_to(root)}")
            relative = (relative_dir / name).as_posix()
            if _is_ignored_dir(name):
                skipped.append(relative + "/")
                dirnames.remove(name)
                continue
            directories.add(relative)
        for name in sorted(filenames):
            path = current / name
            if path.is_symlink():
                raise InitializerError(f"template contains a symlink: {path.relative_to(root)}")
            if not path.is_file():
                raise InitializerError(
                    f"template contains an unsupported file type: {path.relative_to(root)}"
                )
            relative = (relative_dir / name).as_posix()
            if name in IGNORED_DIR_NAMES:
                skipped.append(relative)
                continue
            files[relative] = path

    referenced = _literal_input_paths(files)
    for relative in list(files):
        if _is_ignored_file(Path(relative).name) and relative not in referenced:
            skipped.append(relative)
            del files[relative]
        else:
            hashes[relative] = _sha256_file(files[relative])

    if not files:
        raise InitializerError("template contains no usable files")
    return files, directories, sorted(skipped), hashes


def _strip_tex_comment(line: str) -> str:
    result: list[str] = []
    escaped = False
    for character in line:
        if character == "\\" and not escaped:
            escaped = True
            result.append(character)
            continue
        if character == "%" and not escaped:
            break
        result.append(character)
        escaped = False
    return "".join(result)


def _has_documentclass(path: Path) -> bool:
    try:
        text = path.read_bytes().decode("utf-8", "replace")
    except OSError as exc:
        raise InitializerError(f"cannot read template entry {path}: {exc}") from exc
    for line in text.splitlines():
        if "\\documentclass" in _strip_tex_comment(line):
            return True
    return False


def _engine_from_magic(path: Path) -> str | None:
    try:
        text = path.read_bytes()[: 64 * 1024].decode("utf-8-sig", "replace")
    except OSError as exc:
        raise InitializerError(f"cannot read template entry {path}: {exc}") from exc
    for line in text.splitlines():
        match = _MAGIC_PROGRAM.match(line)
        if match:
            engine = match.group(1).lower()
            if engine in SUPPORTED_ENGINES:
                return engine
    return None


def _select_entry(
    files: dict[str, Path], explicit_main: str | None
) -> str:
    if explicit_main is not None:
        relative = _normalize_main(explicit_main)
        if relative not in files:
            raise InitializerError(f"--main does not name a template file: {relative}")
        entry = files[relative]
        if not _has_documentclass(entry):
            raise InitializerError(
                f"--main does not look like a root entry (no \\documentclass): {relative}"
            )
        return relative

    if "main.tex" in files:
        entry = files["main.tex"]
        if not _has_documentclass(entry):
            raise InitializerError(
                "main.tex exists but does not contain \\documentclass; "
                "pass --main with the real root entry"
            )
        return "main.tex"

    candidates = [
        relative
        for relative, path in files.items()
        if "/" not in relative
        and relative.lower().endswith(".tex")
        and _has_documentclass(path)
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise InitializerError(
            "no root .tex entry found: main.tex is absent and no top-level .tex "
            "file contains \\documentclass; pass --main"
        )
    names = ", ".join(sorted(candidates))
    raise InitializerError(
        f"multiple top-level .tex entries contain \\documentclass ({names}); "
        "pass --main to choose one"
    )


def _build_custom_plan(
    template_root: Path,
    explicit_main: str | None,
    explicit_engine: str | None,
) -> ProjectPlan:
    root = _validate_template_root(template_root)
    receipt_path = root / RECEIPT_NAME
    if os.path.lexists(receipt_path):
        raise InitializerError(
            f"template already contains the reserved receipt path: {RECEIPT_NAME}"
        )

    files, directories, skipped, hashes = _scan_template(root)
    entry = _select_entry(files, explicit_main)

    if explicit_engine is not None:
        engine = explicit_engine
        engine_source = "explicit"
    else:
        engine = _engine_from_magic(files[entry])
        engine_source = "magic" if engine is not None else None

    source_info: dict[str, object] = {
        "kind": "user",
        "path": str(root),
        "files": dict(sorted(hashes.items())),
    }
    if skipped:
        source_info["ignored"] = skipped

    return ProjectPlan(
        source_info=source_info,
        entry=entry,
        engine=engine,
        engine_source=engine_source,
        language=None,
        copies=dict(sorted(files.items())),
        directories=directories,
        source_hashes=hashes,
    )


def _payload_hashes(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise InitializerError(f"staged project contains a symlink: {path}")
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            rows.append(
                {
                    "path": relative,
                    "sha256": _sha256_file(path),
                    "bytes": path.stat().st_size,
                }
            )
    return rows


def _write_receipt(staging: Path, plan: ProjectPlan, output: Path) -> None:
    payload = _payload_hashes(staging)
    source_files = plan.source_info.get("files", {})
    inputs = [
        {"path": relative, "sha256": digest}
        for relative, digest in sorted(source_files.items())
    ]
    receipt: dict[str, object] = {
        "schema": SCHEMA,
        "profile": PROFILE,
        "receipt_kind": "creation",
        "created_at": _utc_now(),
        "generator": "scripts/init_latex_project.py",
        "output": str(output),
        "source_kind": plan.source_info["kind"],
        "source_path": plan.source_info["path"],
        "entry": plan.entry,
        "suggested_engine": plan.engine,
        "engine_source": plan.engine_source,
        "language": plan.language,
        "source": plan.source_info,
        "inputs": inputs,
        "files": payload,
        "note": (
            "This is a project creation receipt, not a final acceptance manifest. "
            "It records copied/created bytes only; no TeX, template commands, or "
            "template code were executed."
        ),
    }
    if plan.engine is None:
        receipt["engine_note"] = (
            "No engine was inferred from the entry TeX magic program line; "
            "confirm the required engine from the template documentation."
        )
    text = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    (staging / RECEIPT_NAME).write_text(text, encoding="utf-8")


def _materialize(plan: ProjectPlan, output: Path) -> None:
    output = _validate_output(output)
    if output.exists() or output.is_symlink():
        raise InitializerError(f"output already exists (refusing to overwrite): {output}")

    staging = Path(
        tempfile.mkdtemp(prefix=f".{output.name}.tmp-", dir=str(output.parent))
    )
    try:
        os.chmod(staging, 0o755)
        for relative in sorted(plan.directories):
            _relative_parts(relative, "project directory")
            (staging / relative).mkdir(parents=True, exist_ok=True)

        for relative, source in sorted(plan.copies.items()):
            _relative_parts(relative, "project file")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            expected = plan.source_hashes.get(relative)
            if expected is None or _sha256_file(destination) != expected:
                raise InitializerError(f"copied file changed while initializing: {relative}")

        for relative, data in sorted(plan.writes.items()):
            _relative_parts(relative, "project file")
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)

        if os.path.lexists(staging / RECEIPT_NAME):
            raise InitializerError(
                f"generated payload conflicts with reserved receipt: {RECEIPT_NAME}"
            )
        _write_receipt(staging, plan, output)

        if os.path.lexists(output):
            raise InitializerError(f"output appeared while initializing: {output}")
        os.rename(staging, output)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _path_argument(value: str) -> Path:
    if not value:
        raise argparse.ArgumentTypeError("path must not be empty")
    return Path(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Create a new LaTeX textbook project from the bundled blank skeleton "
            "or a user-supplied template. Never compiles TeX and never overwrites "
            "an existing output directory."
        )
    )
    parser.add_argument(
        "--output",
        required=True,
        type=_path_argument,
        help="new project directory (parent directory must already exist)",
    )
    parser.add_argument(
        "--template",
        type=_path_argument,
        default=None,
        help="optional user template directory (copied byte-for-byte, with caches ignored)",
    )
    parser.add_argument(
        "--main",
        default=None,
        help="optional .tex root entry relative to the template directory",
    )
    parser.add_argument(
        "--engine",
        choices=SUPPORTED_ENGINES,
        default=None,
        help="explicit compiler; otherwise inferred from built-in language or TeX magic line",
    )
    parser.add_argument(
        "--language",
        choices=("zh", "en"),
        default=None,
        help="built-in template language (default: zh; not supported with --template)",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="built-in plain-text lecture title (not supported with --template)",
    )
    parser.add_argument(
        "--course-name",
        default=None,
        help="built-in plain-text course name (not supported with --template)",
    )
    return parser


def initialize(args: argparse.Namespace) -> Path:
    output = _validate_output(args.output)

    if args.template is not None:
        for option, value in (
            ("--language", args.language),
            ("--title", args.title),
            ("--course-name", args.course_name),
        ):
            if value is not None:
                raise InitializerError(
                    f"{option} is not applicable with --template; custom template "
                    "bytes and metadata are preserved unchanged"
                )
        template_root = _validate_template_root(args.template)
        _ensure_disjoint(template_root, output)
        plan = _build_custom_plan(template_root, args.main, args.engine)
    else:
        if args.main is not None:
            raise InitializerError(
                "--main is only applicable with --template; the built-in project "
                "always uses main.tex"
            )
        if args.language is not None and args.language not in ("zh", "en"):
            raise InitializerError("--language must be one of: zh, en")
        language = args.language or DEFAULT_LANGUAGE
        default_title = "待撰写" if language == "zh" else "To be written"
        default_course = (
            "课程名称（待填写）" if language == "zh" else "Course name (to be filled)"
        )
        plan = _build_builtin_plan(
            language,
            args.title if args.title is not None else default_title,
            args.course_name if args.course_name is not None else default_course,
            args.engine,
        )

    _materialize(plan, output)
    return output


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        output = initialize(args)
    except InitializerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"created {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
