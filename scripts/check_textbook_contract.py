#!/usr/bin/env python3
"""Validate a textbook HTML artifact against a hash-bound acceptance manifest."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any


SCHEMA = "TextbookAcceptanceManifest/v1"
PROFILES = {"authoring-master", "note-fragment", "standalone-publication"}
HEX64 = re.compile(r"^[0-9a-f]{64}$")
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json_no_duplicates(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def atomic_write_new(path: Path, value: Any) -> None:
    if path.exists() or path.is_symlink():
        raise FileExistsError(f"refusing to overwrite report: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise


class TextbookHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.stack: list[dict[str, Any]] = []
        self.doctypes: list[str] = []
        self.top_level_tags: list[str] = []
        self.tag_counts: Counter[str] = Counter()
        self.ids: list[str] = []
        self.internal_hrefs: list[str] = []
        self.external_runtime_elements: list[dict[str, str]] = []
        self.math_nodes: list[dict[str, Any]] = []
        self.current_math: dict[str, Any] | None = None
        self.current_math_depth = 0
        self.python_blocks: list[dict[str, Any]] = []
        self.current_code: dict[str, Any] | None = None
        self.current_code_depth = 0
        self.program_outputs: list[dict[str, Any]] = []
        self.current_output: dict[str, Any] | None = None
        self.current_output_depth = 0
        self.styles: list[str] = []
        self.current_style: list[str] | None = None
        self.current_style_depth = 0
        self.article_texts: list[list[str]] = []
        self.chapter_details = 0
        self.unwrapped_tables = 0
        self.formula_anchors = 0
        self.task_ids = 0

    def _current_article(self) -> int | None:
        for context in reversed(self.stack):
            if context["article_index"] is not None:
                return int(context["article_index"])
        return None

    def _start(self, tag: str, attrs_list: list[tuple[str, str | None]], *, push: bool) -> None:
        tag = tag.casefold()
        attrs = {key.casefold(): (value or "") for key, value in attrs_list}
        classes = set(attrs.get("class", "").split())
        parent_classes = self.stack[-1]["classes"] if self.stack else set()
        if not self.stack:
            self.top_level_tags.append(tag)
        self.tag_counts[tag] += 1
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        href = attrs.get("href", "")
        if tag == "a" and href.startswith("#"):
            self.internal_hrefs.append(href[1:])
        if tag == "script" and attrs.get("src"):
            self.external_runtime_elements.append({"tag": tag, "attribute": "src", "value": attrs["src"]})
        if tag == "link" and attrs.get("href"):
            self.external_runtime_elements.append({"tag": tag, "attribute": "href", "value": attrs["href"]})
        if tag in {"iframe", "object", "embed"}:
            self.external_runtime_elements.append({"tag": tag, "attribute": "element", "value": "present"})
        if tag == "table" and "table-wrap" not in parent_classes:
            self.unwrapped_tables += 1
        if any("formula" in key and "anchor" in key for key in attrs):
            self.formula_anchors += 1
        if "data-task-id" in attrs:
            self.task_ids += 1

        article_index = self._current_article()
        if tag == "article" and "chapter" in classes:
            article_index = len(self.article_texts)
            self.article_texts.append([])
        if tag == "details" and article_index is not None:
            self.chapter_details += 1

        if self.current_math is not None:
            self.current_math_depth += 1
        elif "math" in classes:
            self.current_math = {
                "tag": tag,
                "parts": [],
                "article_index": article_index,
            }
            self.current_math_depth = 1

        if self.current_code is not None:
            self.current_code_depth += 1
        elif tag == "code" and "language-python" in classes:
            self.current_code = {"parts": [], "article_index": article_index}
            self.current_code_depth = 1

        if self.current_output is not None:
            self.current_output_depth += 1
        elif tag == "pre" and "program-output" in classes:
            self.current_output = {"parts": [], "article_index": article_index}
            self.current_output_depth = 1

        if self.current_style is not None:
            self.current_style_depth += 1
        elif tag == "style":
            self.current_style = []
            self.current_style_depth = 1

        if push:
            self.stack.append(
                {"tag": tag, "classes": classes, "attrs": attrs, "article_index": article_index}
            )

    def handle_decl(self, decl: str) -> None:
        self.doctypes.append(decl)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, push=tag.casefold() not in VOID_TAGS)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, push=False)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if self.current_math is not None:
            self.current_math_depth -= 1
            if self.current_math_depth == 0:
                self.current_math["text"] = "".join(self.current_math.pop("parts"))
                self.math_nodes.append(self.current_math)
                self.current_math = None
        if self.current_code is not None:
            self.current_code_depth -= 1
            if self.current_code_depth == 0:
                self.current_code["text"] = "".join(self.current_code.pop("parts"))
                self.python_blocks.append(self.current_code)
                self.current_code = None
        if self.current_output is not None:
            self.current_output_depth -= 1
            if self.current_output_depth == 0:
                self.current_output["text"] = "".join(self.current_output.pop("parts"))
                self.program_outputs.append(self.current_output)
                self.current_output = None
        if self.current_style is not None:
            self.current_style_depth -= 1
            if self.current_style_depth == 0:
                self.styles.append("".join(self.current_style))
                self.current_style = None
        if self.stack:
            if self.stack[-1]["tag"] == tag:
                self.stack.pop()
            else:
                for index in range(len(self.stack) - 1, -1, -1):
                    if self.stack[index]["tag"] == tag:
                        del self.stack[index:]
                        break

    def handle_data(self, data: str) -> None:
        if self.current_math is not None:
            self.current_math["parts"].append(data)
        if self.current_code is not None:
            self.current_code["parts"].append(data)
        if self.current_output is not None:
            self.current_output["parts"].append(data)
        if self.current_style is not None:
            self.current_style.append(data)
        article = self._current_article()
        if article is not None:
            self.article_texts[article].append(data)

    def handle_entityref(self, name: str) -> None:
        decoded = unescape(f"&{name};")
        if self.current_math is not None:
            self.current_math["parts"].append(decoded)
        else:
            self.handle_data(decoded)

    def handle_charref(self, name: str) -> None:
        decoded = unescape(f"&#{name};")
        if self.current_math is not None:
            self.current_math["parts"].append(decoded)
        else:
            self.handle_data(decoded)


def extract_tex(node: dict[str, Any]) -> tuple[str, bool]:
    text = str(node["text"]).strip()
    if text.startswith("$$") and text.endswith("$$") and len(text) >= 4:
        return text[2:-2], True
    if text.startswith("$") and text.endswith("$") and not text.startswith("$$") and len(text) >= 2:
        return text[1:-1], node["tag"] == "pre"
    raise ValueError("math node must have balanced $...$ or $$...$$ delimiters")


def run_katex(rows: list[dict[str, Any]], katex_js: Path) -> dict[str, Any]:
    javascript = r"""
const fs=require('fs');const katex=require(process.argv[1]);const rows=JSON.parse(fs.readFileSync(0,'utf8'));
const failures=[];for(const row of rows){try{katex.renderToString(row.tex,{displayMode:row.display,throwOnError:true,strict:'ignore',trust:false,maxExpand:1000});}catch(error){failures.push({index:row.index,error:String(error),tex:row.tex.slice(0,180)});}}
process.stdout.write(JSON.stringify({version:katex.version,count:rows.length,failures}));if(failures.length)process.exitCode=1;
"""
    completed = subprocess.run(
        ["node", "-e", javascript, str(katex_js)],
        input=json.dumps(rows, ensure_ascii=False, separators=(",", ":")),
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if not completed.stdout:
        return {
            "status": "FAIL",
            "returncode": completed.returncode,
            "failures": [{"error": completed.stderr[-1000:]}],
        }
    result = json.loads(completed.stdout)
    result["returncode"] = completed.returncode
    result["status"] = "PASS" if completed.returncode == 0 and not result["failures"] else "FAIL"
    return result


def run_examples(
    parser: TextbookHTMLParser, runtime: dict[str, Any] | None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if runtime is None:
        return {"status": "NOT_REQUESTED", "runs": 0, "passed": 0, "results": []}, errors
    executable = Path(str(runtime.get("python_executable", "")))
    if not executable.is_absolute() or not executable.is_file() or not os.access(executable, os.X_OK):
        errors.append({"kind": "python_executable", "value": str(executable)})
        return {"status": "FAIL", "runs": 0, "passed": 0, "results": []}, errors
    imports = runtime.get("required_imports", [])
    if not isinstance(imports, list) or not all(isinstance(value, str) and value for value in imports):
        errors.append({"kind": "required_imports"})
        return {"status": "FAIL", "runs": 0, "passed": 0, "results": []}, errors
    preflight_code = "\n".join(f"import {name}" for name in imports)
    preflight = subprocess.run(
        [str(executable), "-c", preflight_code or "pass"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if preflight.returncode:
        errors.append({"kind": "runtime_preflight", "stderr": preflight.stderr[-800:]})
        return {
            "status": "FAIL",
            "executable": str(executable),
            "required_imports": imports,
            "runs": 0,
            "passed": 0,
            "results": [],
        }, errors

    results: list[dict[str, Any]] = []
    stdout_by_article: dict[int | None, list[str]] = {}
    for index, block in enumerate(parser.python_blocks, start=1):
        try:
            completed = subprocess.run(
                [str(executable), "-c", str(block["text"])],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            errors.append({"kind": "python_timeout", "index": index})
            results.append({"index": index, "returncode": None, "status": "TIMEOUT"})
            continue
        result = {
            "index": index,
            "article_index": block["article_index"],
            "returncode": completed.returncode,
            "stdout_sha256": sha256_bytes(completed.stdout.encode("utf-8")),
        }
        results.append(result)
        if completed.returncode:
            errors.append({"kind": "python_failure", "index": index, "stderr": completed.stderr[-800:]})
        else:
            stdout_by_article.setdefault(block["article_index"], []).append(completed.stdout.strip())
    for index, output in enumerate(parser.program_outputs, start=1):
        if str(output["text"]).strip() not in stdout_by_article.get(output["article_index"], []):
            errors.append({"kind": "program_output_mismatch", "index": index})
    return {
        "status": "PASS" if not errors else "FAIL",
        "executable": str(executable),
        "required_imports": imports,
        "preflight_passed": preflight.returncode == 0,
        "runs": len(results),
        "passed": sum(row.get("returncode") == 0 for row in results),
        "results": results,
    }, errors


def validate(
    html_path: Path,
    manifest_path: Path,
    expected_manifest_sha256: str,
    katex_js: Path | None,
) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    for label, path in (("html", html_path), ("manifest", manifest_path)):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} must be an ordinary non-symlink file: {path}")
    actual_manifest_hash = sha256_file(manifest_path)
    if not HEX64.fullmatch(expected_manifest_sha256):
        raise ValueError("expected manifest SHA-256 must be 64 lowercase hexadecimal characters")
    if actual_manifest_hash != expected_manifest_sha256:
        raise ValueError(
            f"manifest SHA-256 mismatch: expected {expected_manifest_sha256}, observed {actual_manifest_hash}"
        )
    manifest = load_json_no_duplicates(manifest_path)
    if manifest.get("schema") != SCHEMA:
        errors.append({"kind": "manifest_schema", "actual": manifest.get("schema")})
    profile = manifest.get("profile")
    if profile not in PROFILES:
        errors.append({"kind": "profile", "actual": profile})

    raw_bytes = html_path.read_bytes()
    html_sha = sha256_bytes(raw_bytes)
    declared_sha = manifest.get("artifact", {}).get("sha256")
    if not isinstance(declared_sha, str) or not HEX64.fullmatch(declared_sha):
        errors.append({"kind": "artifact_sha256_shape", "actual": declared_sha})
    elif declared_sha != html_sha:
        errors.append({"kind": "artifact_sha256", "expected": declared_sha, "actual": html_sha})
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"HTML is not UTF-8: {error}") from error
    parser = TextbookHTMLParser()
    parser.feed(raw)
    parser.close()

    duplicate_ids = sorted(value for value, count in Counter(parser.ids).items() if count > 1)
    if duplicate_ids:
        errors.append({"kind": "duplicate_ids", "values": duplicate_ids})
    missing_ids = sorted(set(parser.internal_hrefs) - set(parser.ids))
    if missing_ids:
        errors.append({"kind": "broken_internal_links", "values": missing_ids})

    if profile == "note-fragment":
        if parser.doctypes or parser.top_level_tags != ["div"]:
            errors.append(
                {
                    "kind": "note_fragment_root",
                    "doctypes": parser.doctypes,
                    "top_level_tags": parser.top_level_tags,
                }
            )
        forbidden = sorted(
            tag
            for tag in ("html", "head", "body", "script", "style", "link", "iframe", "object", "embed")
            if parser.tag_counts[tag]
        )
        if forbidden:
            errors.append({"kind": "note_fragment_forbidden_elements", "values": forbidden})
        root_match = re.match(r"\s*<div\b[^>]*data-schema-version=[\"']9[\"']", raw, flags=re.I)
        if root_match is None:
            errors.append({"kind": "note_fragment_schema9_root"})
    if profile == "standalone-publication":
        if not any(value.casefold().startswith("doctype html") for value in parser.doctypes):
            errors.append({"kind": "standalone_doctype"})
        for required_tag in ("html", "head", "body"):
            if parser.tag_counts[required_tag] != 1:
                errors.append(
                    {"kind": "standalone_document_tag", "tag": required_tag, "count": parser.tag_counts[required_tag]}
                )
        if parser.external_runtime_elements:
            errors.append({"kind": "external_runtime_elements", "values": parser.external_runtime_elements})
        if parser.unwrapped_tables:
            errors.append({"kind": "unwrapped_tables", "count": parser.unwrapped_tables})
        for css in parser.styles:
            for selector, declarations in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
                if re.search(r"(?:^|,)\s*(?:html|body)(?:\s|,|$)", selector, flags=re.I) and re.search(
                    r"overflow-x\s*:\s*(?:hidden|clip)\b", declarations, flags=re.I
                ):
                    errors.append({"kind": "document_overflow_mask", "selector": selector.strip()})

    formula_rows: list[dict[str, Any]] = []
    for index, node in enumerate(parser.math_nodes, start=1):
        text = str(node["text"])
        if "\t" in text:
            errors.append({"kind": "tab_inside_math", "index": index})
        residual_entities = re.findall(
            r"&(?:amp;)*(?:lt|gt);|&#(?:60|62);|&#x(?:3c|3e);",
            text,
            flags=re.I,
        )
        if residual_entities:
            errors.append(
                {"kind": "residual_html_entity_inside_math", "index": index, "values": residual_entities}
            )
        try:
            tex, display = extract_tex(node)
        except ValueError as error:
            errors.append({"kind": "math_delimiter", "index": index, "error": str(error)})
            continue
        formula_rows.append({"index": index, "tex": tex, "display": display})

    counts = {
        "chapters": len(parser.article_texts),
        "math_nodes": len(parser.math_nodes),
        "python_blocks": len(parser.python_blocks),
        "program_outputs": len(parser.program_outputs),
        "details": parser.chapter_details,
        "document_details": parser.tag_counts["details"],
        "formula_anchors": parser.formula_anchors,
        "task_ids": parser.task_ids,
        "ids": len(parser.ids),
        "internal_links": len(parser.internal_hrefs),
    }
    declared_counts = manifest.get("counts", {})
    if not isinstance(declared_counts, dict):
        errors.append({"kind": "manifest_counts"})
    else:
        for key, expected in declared_counts.items():
            if key not in counts or not isinstance(expected, int) or expected < 0:
                errors.append({"kind": "manifest_count_field", "field": key, "value": expected})
            elif counts[key] != expected:
                errors.append({"kind": "count_mismatch", "field": key, "expected": expected, "actual": counts[key]})

    math_contract = manifest.get("math", {})
    require_katex = bool(math_contract.get("require_katex", False)) if isinstance(math_contract, dict) else False
    if require_katex and katex_js is None:
        errors.append({"kind": "katex_required_but_not_provided"})
        katex = {"status": "NOT_RUN", "count": len(formula_rows), "failures": []}
    elif katex_js is not None:
        if katex_js.is_symlink() or not katex_js.is_file():
            errors.append({"kind": "katex_path", "value": str(katex_js)})
            katex = {"status": "FAIL", "count": len(formula_rows), "failures": []}
        else:
            katex = run_katex(formula_rows, katex_js)
            if katex["status"] != "PASS":
                errors.append({"kind": "katex_parse", "failures": katex.get("failures", [])[:20]})
    else:
        katex = {"status": "NOT_REQUESTED", "count": len(formula_rows), "failures": []}

    execution, execution_errors = run_examples(
        parser, manifest.get("runtime") if isinstance(manifest.get("runtime"), dict) else None
    )
    errors.extend(execution_errors)

    interaction = manifest.get("interaction_probe")
    interaction_result: dict[str, Any] = {"status": "NOT_REQUESTED"}
    if interaction is not None:
        if not isinstance(interaction, dict):
            errors.append({"kind": "interaction_probe"})
        else:
            query = interaction.get("query")
            minimum = interaction.get("min_matches")
            maximum = interaction.get("max_matches")
            if (
                not isinstance(query, str)
                or not query.strip()
                or not isinstance(minimum, int)
                or not isinstance(maximum, int)
                or minimum < 1
                or maximum < minimum
            ):
                errors.append({"kind": "interaction_probe_contract"})
            else:
                folded = query.strip().casefold()
                matches = sum(folded in "".join(parts).casefold() for parts in parser.article_texts)
                interaction_result = {
                    "status": "PASS" if minimum <= matches <= maximum else "FAIL",
                    "query": query,
                    "matches": matches,
                    "min_matches": minimum,
                    "max_matches": maximum,
                }
                if interaction_result["status"] != "PASS":
                    errors.append({"kind": "interaction_probe_matches", **interaction_result})

    report = {
        "schema": "TextbookContractCheck/v1",
        "status": "PASS" if not errors else "FAIL",
        "profile": profile,
        "html_path": str(html_path),
        "html_sha256": html_sha,
        "manifest_path": str(manifest_path),
        "manifest_sha256": actual_manifest_hash,
        "counts": counts,
        "katex": katex,
        "execution": execution,
        "interaction_probe": interaction_result,
        "errors": errors,
    }
    report_without_hash = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report["report_sha256"] = sha256_bytes(report_without_hash.encode("utf-8"))
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--katex-js", type=Path)
    parser.add_argument("--report", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = validate(
        args.html.expanduser().resolve(),
        args.manifest.expanduser().resolve(),
        args.expected_manifest_sha256,
        args.katex_js.expanduser().resolve() if args.katex_js else None,
    )
    if args.report:
        atomic_write_new(args.report.expanduser().resolve(), report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "profile": report["profile"],
                "counts": report["counts"],
                "katex_status": report["katex"]["status"],
                "execution_status": report["execution"]["status"],
                "error_count": len(report["errors"]),
                "report_sha256": report["report_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
