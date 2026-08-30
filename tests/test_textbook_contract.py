from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/check_textbook_contract.py"
SPEC = importlib.util.spec_from_file_location("check_textbook_contract", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
CONTRACT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTRACT)


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class TextbookContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_case(
        self,
        html: str,
        *,
        profile: str,
        counts: dict[str, int] | None = None,
        math_required: bool = False,
        runtime: dict[str, object] | None = None,
        interaction: dict[str, object] | None = None,
        declared_html_sha: str | None = None,
    ) -> tuple[Path, Path, str]:
        html_path = self.root / "textbook.html"
        html_path.write_text(html, encoding="utf-8")
        manifest: dict[str, object] = {
            "schema": "TextbookAcceptanceManifest/v1",
            "profile": profile,
            "artifact": {"sha256": declared_html_sha or sha(html.encode("utf-8"))},
            "counts": counts or {},
            "math": {"require_katex": math_required},
        }
        if runtime is not None:
            manifest["runtime"] = runtime
        if interaction is not None:
            manifest["interaction_probe"] = interaction
        manifest_path = self.root / "manifest.json"
        raw = json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        manifest_path.write_text(raw, encoding="utf-8")
        return html_path, manifest_path, sha(raw.encode("utf-8"))

    def validate(self, html_path: Path, manifest_path: Path, manifest_sha: str):
        return CONTRACT.validate(html_path, manifest_path, manifest_sha, None)

    def test_forward_standalone_case_passes(self) -> None:
        html = """<!doctype html><html><head><meta charset="utf-8"><style>
        .table-wrap{overflow-x:auto}.math{max-width:100%;overflow-x:auto}
        </style></head><body><article class="chapter" id="ridge"><h1>岭回归</h1>
        <div class="table-wrap"><table><tr><td><span class="math">$x^2$</span></td></tr></table></div>
        <pre><code class="language-python">print("ok")</code></pre><pre class="program-output">ok</pre>
        <details><summary>答案</summary><p>完成</p></details></article>
        <details><summary>全书说明</summary><p>附录</p></details></body></html>"""
        paths = self.write_case(
            html,
            profile="standalone-publication",
            counts={
                "chapters": 1,
                "math_nodes": 1,
                "python_blocks": 1,
                "program_outputs": 1,
                "details": 1,
            },
            runtime={"python_executable": sys.executable, "required_imports": []},
            interaction={"query": "岭回归", "min_matches": 1, "max_matches": 1},
        )
        report = self.validate(*paths)
        self.assertEqual(report["status"], "PASS", report["errors"])
        self.assertEqual(report["execution"]["passed"], 1)
        self.assertEqual(report["counts"]["details"], 1)
        self.assertEqual(report["counts"]["document_details"], 2)

    def test_authoring_profile_preserves_declared_anchors(self) -> None:
        html = """<div data-formula-anchor-id="f1" data-task-id="t1"><span class="math">$x$</span></div>"""
        paths = self.write_case(
            html,
            profile="authoring-master",
            counts={"math_nodes": 1, "formula_anchors": 1, "task_ids": 1},
        )
        report = self.validate(*paths)
        self.assertEqual(report["status"], "PASS", report["errors"])

    def test_note_fragment_profile_accepts_passive_schema9_root(self) -> None:
        html = '<div data-schema-version="9"><h1>教材</h1><span class="math">$a&amp;b$</span></div>'
        paths = self.write_case(html, profile="note-fragment", counts={"math_nodes": 1})
        report = self.validate(*paths)
        self.assertEqual(report["status"], "PASS", report["errors"])

    def test_old_math_failure_shapes_are_rejected(self) -> None:
        cases = {
            "tab": '<div data-schema-version="9"><span class="math">$x\t+y$</span></div>',
            "delimiter": '<div data-schema-version="9"><span class="math">$x+y</span></div>',
            "double_encoded_entity": '<div data-schema-version="9"><span class="math">$x&amp;gt;y$</span></div>',
        }
        for name, html in cases.items():
            with self.subTest(name=name):
                case_root = self.root / name
                case_root.mkdir()
                prior_root = self.root
                self.root = case_root
                paths = self.write_case(html, profile="note-fragment", counts={"math_nodes": 1})
                report = self.validate(*paths)
                self.assertEqual(report["status"], "FAIL")
                self.root = prior_root

    def test_single_html_escape_is_dom_decoded_before_math_validation(self) -> None:
        html = '<div data-schema-version="9"><span class="math">$x&gt;y$</span></div>'
        paths = self.write_case(html, profile="note-fragment", counts={"math_nodes": 1})
        report = self.validate(*paths)
        self.assertEqual(report["status"], "PASS", report["errors"])

    def test_note_fragment_rejects_active_runtime(self) -> None:
        html = '<div data-schema-version="9"><script>void 0</script><p>正文</p></div>'
        paths = self.write_case(html, profile="note-fragment")
        report = self.validate(*paths)
        self.assertTrue(any(row["kind"] == "note_fragment_forbidden_elements" for row in report["errors"]))

    def test_standalone_rejects_unwrapped_table_and_body_mask(self) -> None:
        html = """<!doctype html><html><head><style>body{overflow-x:hidden}</style></head>
        <body><article class="chapter"><table><tr><td>wide</td></tr></table></article></body></html>"""
        paths = self.write_case(html, profile="standalone-publication", counts={"chapters": 1})
        report = self.validate(*paths)
        kinds = {row["kind"] for row in report["errors"]}
        self.assertIn("unwrapped_tables", kinds)
        self.assertIn("document_overflow_mask", kinds)

    def test_artifact_and_count_drift_are_rejected(self) -> None:
        html = '<div data-schema-version="9"><span class="math">$x$</span></div>'
        paths = self.write_case(
            html,
            profile="note-fragment",
            counts={"math_nodes": 2},
            declared_html_sha="0" * 64,
        )
        report = self.validate(*paths)
        kinds = {row["kind"] for row in report["errors"]}
        self.assertIn("artifact_sha256", kinds)
        self.assertIn("count_mismatch", kinds)

    def test_external_manifest_pin_is_required(self) -> None:
        paths = self.write_case('<div data-schema-version="9"></div>', profile="note-fragment")
        with self.assertRaises(ValueError):
            CONTRACT.validate(paths[0], paths[1], "f" * 64, None)

    def test_runtime_dependency_preflight_fails_closed(self) -> None:
        html = """<!doctype html><html><head></head><body><article class="chapter">
        <pre><code class="language-python">print("ok")</code></pre></article></body></html>"""
        paths = self.write_case(
            html,
            profile="standalone-publication",
            counts={"chapters": 1, "python_blocks": 1},
            runtime={
                "python_executable": sys.executable,
                "required_imports": ["module_that_does_not_exist_textbook_fixture"],
            },
        )
        report = self.validate(*paths)
        self.assertTrue(any(row["kind"] == "runtime_preflight" for row in report["errors"]))

    def test_fixture_derived_query_rejects_zero_and_all_matches(self) -> None:
        html = """<!doctype html><html><head></head><body>
        <article class="chapter">共同词 第一章</article><article class="chapter">共同词 第二章</article>
        </body></html>"""
        for name, query in (("zero", "不存在"), ("all", "共同词")):
            with self.subTest(name=name):
                case_root = self.root / name
                case_root.mkdir()
                prior_root = self.root
                self.root = case_root
                paths = self.write_case(
                    html,
                    profile="standalone-publication",
                    counts={"chapters": 2},
                    interaction={"query": query, "min_matches": 1, "max_matches": 1},
                )
                report = self.validate(*paths)
                self.assertTrue(any(row["kind"] == "interaction_probe_matches" for row in report["errors"]))
                self.root = prior_root

    def test_required_katex_cannot_be_silently_skipped(self) -> None:
        html = '<div data-schema-version="9"><span class="math">$x$</span></div>'
        paths = self.write_case(
            html,
            profile="note-fragment",
            counts={"math_nodes": 1},
            math_required=True,
        )
        report = self.validate(*paths)
        self.assertTrue(any(row["kind"] == "katex_required_but_not_provided" for row in report["errors"]))


if __name__ == "__main__":
    unittest.main()
