from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/init_latex_project.py"
SPEC = importlib.util.spec_from_file_location("init_latex_project", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
INIT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INIT
SPEC.loader.exec_module(INIT)

BUILTIN = ROOT / "assets/latex-template"
EXPECTED_BUILTIN_FILES = {
    "main.tex",
    "preamble/packages.tex",
    "preamble/style.tex",
    "preamble/macros.tex",
    "preamble/boxes.tex",
    "preamble/code.tex",
    "sections/01_chapter.tex",
    "textbook-template.receipt.json",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LatexProjectInitializerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_init(self, *arguments: object) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = INIT.main([str(argument) for argument in arguments])
        return code, stdout.getvalue(), stderr.getvalue()

    def write_template(
        self, files: dict[str, str | bytes], name: str = "template"
    ) -> Path:
        root = self.root / name
        root.mkdir(parents=True)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, str):
                path.write_text(content, encoding="utf-8")
            else:
                path.write_bytes(content)
        return root

    def receipt(self, output: Path) -> dict[str, object]:
        return json.loads((output / "textbook-template.receipt.json").read_text(encoding="utf-8"))

    def assert_failed_without_output(
        self, code: int, stderr: str, output: Path, message: str | None = None
    ) -> None:
        self.assertEqual(code, 2, stderr)
        self.assertFalse(os.path.lexists(output), f"unexpected output: {output}")
        if message is not None:
            self.assertIn(message, stderr.lower())

    def test_builtin_zh_source_closure_and_ctex_setup(self) -> None:
        output = self.root / "zh-project"
        code, _stdout, stderr = self.run_init("--output", output)
        self.assertEqual(code, 0, stderr)

        receipt = self.receipt(output)
        self.assertEqual(receipt["schema"], "TextbookLatexTemplate/v1")
        self.assertEqual(receipt["profile"], "latex-pdf")
        self.assertEqual(receipt["receipt_kind"], "creation")
        self.assertEqual(receipt["entry"], "main.tex")
        self.assertEqual(receipt["suggested_engine"], "xelatex")
        self.assertEqual(receipt["language"], "zh")
        self.assertEqual(receipt["source_kind"], "builtin")
        self.assertIn("not a final acceptance manifest", receipt["note"])
        self.assertEqual(len(receipt["source"]["files"]), 17)
        self.assertEqual(len(receipt["inputs"]), 17)
        self.assertIn("snapshot_manifest_sha256", receipt["source"])

        actual = {
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, EXPECTED_BUILTIN_FILES)
        self.assertEqual(
            {row["path"] for row in receipt["files"]},
            EXPECTED_BUILTIN_FILES - {"textbook-template.receipt.json"},
        )

        main = (output / "main.tex").read_text(encoding="utf-8")
        packages = (output / "preamble/packages.tex").read_text(encoding="utf-8")
        style = (output / "preamble/style.tex").read_text(encoding="utf-8")
        boxes = (output / "preamble/boxes.tex").read_text(encoding="utf-8")
        macros = (output / "preamble/macros.tex").read_text(encoding="utf-8")
        code_style = (output / "preamble/code.tex").read_text(encoding="utf-8")
        chapter = (output / "sections/01_chapter.tex").read_text(encoding="utf-8")
        self.assertIn("\\documentclass[11pt,a4paper]{article}", main)
        self.assertIn("\\usepackage[fontset=fandol]{ctex}", packages)
        self.assertIn("\\usepackage{microtype}", packages)
        self.assertIn("\\pgfplotsset{compat=1.18}", packages)
        self.assertNotIn("compat=newest", packages)
        self.assertIn("headheight=22pt", packages)
        self.assertNotIn("headheight=15pt", packages)
        for obsolete in ("fontenc", "inputenc", "lmodern", "helvet"):
            self.assertNotIn(obsolete, packages)
        self.assertIn("\\definecolor{accent}{HTML}{1F5FBF}", style)
        self.assertIn("\\newtcolorbox{notebox}", boxes)
        self.assertIn("\\newcommand{\\R}", macros)
        self.assertIn("\\lstdefinestyle{modern}", code_style)
        order = [
            "\\input{preamble/packages}",
            "\\input{preamble/style}",
            "\\input{preamble/macros}",
            "\\input{preamble/boxes}",
            "\\input{preamble/code}",
        ]
        positions = [main.index(item) for item in order]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("待撰写", main)
        self.assertIn("学习目标", packages + boxes)
        self.assertIn("待撰写", chapter)
        self.assertNotIn("Dijkstra", main + chapter)
        self.assertNotIn("Merge sort", main + chapter)
        self.assertNotIn("\\lstinputlisting", main + chapter)
        self.assertFalse((output / "figures").exists())
        self.assertFalse((output / "code").exists())

    def test_builtin_en_source_closure_and_pdflatex_setup(self) -> None:
        output = self.root / "en-project"
        code, _stdout, stderr = self.run_init("--output", output, "--language", "en")
        self.assertEqual(code, 0, stderr)

        receipt = self.receipt(output)
        self.assertEqual(receipt["suggested_engine"], "pdflatex")
        self.assertEqual(receipt["language"], "en")
        self.assertEqual(receipt["source_kind"], "builtin")

        actual = {
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, EXPECTED_BUILTIN_FILES)
        main = (output / "main.tex").read_text(encoding="utf-8")
        packages = (output / "preamble/packages.tex").read_text(encoding="utf-8")
        chapter = (output / "sections/01_chapter.tex").read_text(encoding="utf-8")
        self.assertIn("\\documentclass[11pt,a4paper]{article}", main)
        for required in ("fontenc", "inputenc", "lmodern", "helvet", "microtype"):
            self.assertIn(required, packages)
        self.assertNotIn("ctex", packages)
        self.assertNotIn("fandol", packages)
        self.assertIn("\\pgfplotsset{compat=1.18}", packages)
        self.assertNotIn("compat=newest", packages)
        self.assertIn("headheight=22pt", packages)
        self.assertNotIn("headheight=15pt", packages)
        self.assertIn("to be written", main.lower())
        self.assertIn("to be written", chapter.lower())
        self.assertNotIn("Dijkstra", main + chapter)
        self.assertNotIn("Merge sort", main + chapter)
        self.assertFalse((output / "figures").exists())
        self.assertFalse((output / "code").exists())

    def test_builtin_metadata_is_escaped_and_control_characters_rejected(self) -> None:
        title = r"A & B $x$ #1 100% {ok} _ ^ ~ \path"
        course = "C++ & R&D"
        output = self.root / "escaped"
        code, _stdout, stderr = self.run_init(
            "--output", output, "--title", title, "--course-name", course
        )
        self.assertEqual(code, 0, stderr)
        main = (output / "main.tex").read_text(encoding="utf-8")
        expected_title = (
            r"A \& B \$x\$ \#1 100\% \{ok\} \_ "
            r"\textasciicircum{} \textasciitilde{} \textbackslash{}path"
        )
        self.assertIn(expected_title, main)
        self.assertIn(r"C++ \& R\&D", main)

        for index, (option, value) in enumerate(
            (("--title", "line one\nline two"), ("--course-name", "nul\x00here"))
        ):
            with self.subTest(option=option):
                bad_output = self.root / f"bad-{index}"
                code, _stdout, stderr = self.run_init(
                    "--output", bad_output, option, value
                )
                self.assert_failed_without_output(code, stderr, bad_output)
                self.assertIn("error:", stderr.lower())

    def test_builtin_engine_override_is_limited_to_compatible_engines(self) -> None:
        zh_lua = self.root / "zh-lua"
        code, _stdout, stderr = self.run_init(
            "--output", zh_lua, "--engine", "lualatex"
        )
        self.assertEqual(code, 0, stderr)
        receipt = self.receipt(zh_lua)
        self.assertEqual(receipt["suggested_engine"], "lualatex")
        self.assertEqual(receipt["engine_source"], "explicit")

        code, _stdout, stderr = self.run_init(
            "--output", self.root / "zh-pdf", "--engine", "pdflatex"
        )
        self.assert_failed_without_output(2, stderr, self.root / "zh-pdf")
        self.assertIn("ctex", stderr.lower())

        code, _stdout, stderr = self.run_init(
            "--output", self.root / "en-xetex", "--language", "en", "--engine", "xelatex"
        )
        self.assert_failed_without_output(2, stderr, self.root / "en-xetex")
        self.assertIn("pdflatex", stderr.lower())

        code, _stdout, stderr = self.run_init(
            "--output", self.root / "builtin-main", "--main", "custom.tex"
        )
        self.assert_failed_without_output(2, stderr, self.root / "builtin-main")

    def test_custom_template_book_entry_preserves_bytes_and_ignores_caches(self) -> None:
        template = self.write_template(
            {
                "book.tex": (
                    "% !TEX program = lualatex\n"
                    "\\documentclass[12pt,openright]{book}\n"
                    "\\usepackage{customstyle}\n"
                    "\\begin{document}\n\\input{chapters/one}\n\\end{document}\n"
                ),
                "styles/customstyle.sty": (
                    "\\NeedsTeXFormat{LaTeX2e}\n"
                    "\\ProvidesPackage{customstyle}\n"
                    "\\definecolor{myaccent}{HTML}{123456}\n"
                    "\\newcommand{\\keepme}{RAW}\n"
                ),
                "chapters/one.tex": "\\chapter{Raw chapter}\nText.\n",
                "README.md": "# User README\n\nKeep me byte-for-byte.\n",
                "images/plot.pdf": b"%PDF-1.4\n\x00\xffraw-binary\n",
                "data/table.csv": "x,y\n1,2\n",
                ".git/config": "[core]\n\trepositoryformatversion = 0\n",
                "__pycache__/junk.pyc": b"junk",
                "book.aux": "generated",
                "book.log": "generated",
                "_minted-book/snippet.pyg": "generated",
            }
        )
        before = {
            path.relative_to(template).as_posix(): sha(path.read_bytes())
            for path in template.rglob("*")
            if path.is_file()
        }

        output = self.root / "copy"
        code, _stdout, stderr = self.run_init("--template", template, "--output", output)
        self.assertEqual(code, 0, stderr)

        receipt = self.receipt(output)
        self.assertEqual(receipt["entry"], "book.tex")
        self.assertEqual(receipt["suggested_engine"], "lualatex")
        self.assertEqual(receipt["engine_source"], "magic")
        self.assertIsNone(receipt["language"])
        self.assertEqual(receipt["source_kind"], "user")
        self.assertEqual(receipt["source_path"], str(template))
        self.assertEqual(
            receipt["source"]["files"]["README.md"], before["README.md"]
        )

        for relative, digest in before.items():
            if relative.startswith((".git/", "__pycache__/", "_minted-book/")):
                continue
            if relative in {"book.aux", "book.log"}:
                continue
            copied = output / relative
            self.assertTrue(copied.is_file(), relative)
            self.assertEqual(sha(copied.read_bytes()), digest, relative)
        expected_files = {
            relative
            for relative in before
            if not relative.startswith((".git/", "__pycache__/", "_minted-book/"))
            and relative not in {"book.aux", "book.log"}
        } | {"textbook-template.receipt.json"}
        self.assertEqual(
            {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            },
            expected_files,
        )
        self.assertEqual(
            {row["path"]: row["sha256"] for row in receipt["inputs"]},
            {
                relative: digest
                for relative, digest in before.items()
                if relative in expected_files
            },
        )
        self.assertEqual((output / "book.tex").read_bytes(), (template / "book.tex").read_bytes())
        self.assertEqual(
            (output / "styles/customstyle.sty").read_bytes(),
            (template / "styles/customstyle.sty").read_bytes(),
        )
        self.assertEqual(
            (output / "images/plot.pdf").read_bytes(),
            (template / "images/plot.pdf").read_bytes(),
        )
        self.assertFalse((output / ".git").exists())
        self.assertFalse((output / "__pycache__").exists())
        self.assertFalse((output / "_minted-book").exists())
        self.assertFalse((output / "book.aux").exists())
        self.assertFalse((output / "book.log").exists())
        self.assertFalse((output / "main.tex").exists())

        skipped = receipt["source"].get("ignored", [])
        self.assertTrue(any(item.startswith(".git/") for item in skipped), skipped)
        after = {
            path.relative_to(template).as_posix(): sha(path.read_bytes())
            for path in template.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)

    def test_custom_nested_main_and_explicit_engine_override(self) -> None:
        template = self.write_template(
            {
                "src/book.tex": (
                    "% !TEX TS-program = xelatex\n"
                    "\\documentclass{book}\n"
                    "\\begin{document}Root\\end{document}\n"
                ),
                "notes.tex": "\\section{Not a root entry}\n",
            }
        )
        output = self.root / "nested"
        code, _stdout, stderr = self.run_init(
            "--template",
            template,
            "--output",
            output,
            "--main",
            "src/book.tex",
            "--engine",
            "pdflatex",
        )
        self.assertEqual(code, 0, stderr)
        receipt = self.receipt(output)
        self.assertEqual(receipt["entry"], "src/book.tex")
        self.assertEqual(receipt["suggested_engine"], "pdflatex")
        self.assertEqual(receipt["engine_source"], "explicit")
        self.assertEqual(
            (output / "src/book.tex").read_bytes(),
            (template / "src/book.tex").read_bytes(),
        )

    def test_custom_entry_selection_and_bad_main_paths(self) -> None:
        ambiguous = self.write_template(
            {
                "a.tex": "\\documentclass{article}\n",
                "b.tex": "\\documentclass{book}\n",
            },
            name="ambiguous",
        )
        code, _stdout, stderr = self.run_init(
            "--template", ambiguous, "--output", self.root / "ambiguous-out"
        )
        self.assert_failed_without_output(2, stderr, self.root / "ambiguous-out")
        self.assertIn("multiple", stderr.lower())
        self.assertIn("a.tex", stderr)
        self.assertIn("b.tex", stderr)

        nested_only = self.write_template(
            {
                "notes.tex": "\\section{Notes}\n",
                "chapters/root.tex": "\\documentclass{book}\n",
            },
            name="nested-only",
        )
        code, _stdout, stderr = self.run_init(
            "--template", nested_only, "--output", self.root / "nested-only-out"
        )
        self.assert_failed_without_output(2, stderr, self.root / "nested-only-out")
        self.assertIn("no root", stderr.lower())

        explicit = self.write_template(
            {
                "book.tex": "\\documentclass{book}\n",
                "chapter.tex": "\\section{Not a root}\n",
            },
            name="explicit",
        )
        outside = self.root / "outside.tex"
        outside.write_text("\\documentclass{book}\n", encoding="utf-8")
        for index, main in enumerate(
            ("missing.tex", "../outside.tex", str(outside), "chapter.tex")
        ):
            with self.subTest(main=main):
                target = self.root / f"explicit-out-{index}"
                code, _stdout, stderr = self.run_init(
                    "--template", explicit, "--output", target, "--main", main
                )
                self.assert_failed_without_output(code, stderr, target)

        priority = self.write_template(
            {
                "main.tex": "\\documentclass{article}\n",
                "book.tex": "\\documentclass{book}\n",
            },
            name="priority",
        )
        output = self.root / "priority-out"
        code, _stdout, stderr = self.run_init(
            "--template", priority, "--output", output
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(self.receipt(output)["entry"], "main.tex")

    def test_output_overwrite_is_rejected_and_old_bytes_survive(self) -> None:
        existing_dir = self.root / "existing-dir"
        existing_dir.mkdir()
        sentinel = existing_dir / "keep.txt"
        sentinel.write_bytes(b"keep me\n")
        before = sha(sentinel.read_bytes())
        code, _stdout, stderr = self.run_init("--output", existing_dir)
        self.assertEqual(code, 2, stderr)
        self.assertEqual(sentinel.read_bytes(), b"keep me\n")
        self.assertEqual(sha(sentinel.read_bytes()), before)
        self.assertFalse((existing_dir / "main.tex").exists())
        self.assertFalse((existing_dir / "textbook-template.receipt.json").exists())

        existing_file = self.root / "existing-file"
        existing_file.write_bytes(b"do not replace")
        code, _stdout, stderr = self.run_init("--output", existing_file)
        self.assertEqual(code, 2, stderr)
        self.assertEqual(existing_file.read_bytes(), b"do not replace")

        target = self.root / "symlink-target"
        target.mkdir()
        target_file = target / "keep.txt"
        target_file.write_bytes(b"target")
        link = self.root / "output-link"
        os.symlink(target, link, target_is_directory=True)
        code, _stdout, stderr = self.run_init("--output", link)
        self.assertEqual(code, 2, stderr)
        self.assertTrue(link.is_symlink())
        self.assertEqual(target_file.read_bytes(), b"target")
        self.assertFalse((target / "main.tex").exists())

        dangling = self.root / "dangling"
        os.symlink(self.root / "does-not-exist", dangling)
        code, _stdout, stderr = self.run_init("--output", dangling)
        self.assertEqual(code, 2, stderr)
        self.assertTrue(dangling.is_symlink())

    def test_bad_templates_and_paths_are_rejected_without_partial_output(self) -> None:
        missing = self.root / "missing-template"
        code, _stdout, stderr = self.run_init(
            "--template", missing, "--output", self.root / "missing-out"
        )
        self.assert_failed_without_output(code, stderr, self.root / "missing-out")

        template_file = self.root / "template-file"
        template_file.write_text("not a directory", encoding="utf-8")
        code, _stdout, stderr = self.run_init(
            "--template", template_file, "--output", self.root / "file-out"
        )
        self.assert_failed_without_output(code, stderr, self.root / "file-out")

        real_template = self.write_template(
            {"book.tex": "\\documentclass{book}\n"}, name="real-template"
        )
        root_link = self.root / "template-link"
        os.symlink(real_template, root_link, target_is_directory=True)
        code, _stdout, stderr = self.run_init(
            "--template", root_link, "--output", self.root / "link-out"
        )
        self.assert_failed_without_output(code, stderr, self.root / "link-out")

        unsafe = self.write_template(
            {"book.tex": "\\documentclass{book}\n"}, name="unsafe-template"
        )
        external = self.root / "external.tex"
        external.write_text("\\documentclass{book}\n", encoding="utf-8")
        os.symlink(external, unsafe / "external.tex")
        code, _stdout, stderr = self.run_init(
            "--template", unsafe, "--output", self.root / "unsafe-out"
        )
        self.assert_failed_without_output(code, stderr, self.root / "unsafe-out")

        inside = real_template / "generated"
        code, _stdout, stderr = self.run_init(
            "--template", real_template, "--output", inside
        )
        self.assert_failed_without_output(code, stderr, inside)
        self.assertTrue((real_template / "book.tex").is_file())

        conflict = self.write_template(
            {
                "book.tex": "\\documentclass{book}\n",
                "textbook-template.receipt.json": "{}\n",
            },
            name="receipt-conflict",
        )
        code, _stdout, stderr = self.run_init(
            "--template", conflict, "--output", self.root / "conflict-out"
        )
        self.assert_failed_without_output(code, stderr, self.root / "conflict-out")

    def test_copy_failure_cleans_staging_and_leaves_no_output(self) -> None:
        template = self.write_template(
            {
                "book.tex": "\\documentclass{book}\n",
                "notes.tex": "% second file\n",
            },
            name="copy-failure",
        )
        output = self.root / "copy-failure-out"
        real_copy2 = INIT.shutil.copy2
        calls = {"count": 0}

        def fail_after_first_copy(source, destination, *args, **kwargs):
            real_copy2(source, destination, *args, **kwargs)
            calls["count"] += 1
            if calls["count"] == 1:
                raise OSError("simulated copy failure")

        with mock.patch.object(
            INIT.shutil, "copy2", side_effect=fail_after_first_copy
        ):
            code, _stdout, stderr = self.run_init(
                "--template", template, "--output", output
            )
        self.assertEqual(code, 2, stderr)
        self.assertIn("simulated copy failure", stderr)
        self.assertFalse(os.path.lexists(output))
        leftovers = [
            path.name
            for path in self.root.iterdir()
            if path.name.startswith(f".{output.name}.tmp-")
        ]
        self.assertEqual(leftovers, [])

    def test_custom_template_rejects_builtin_only_options(self) -> None:
        template = self.write_template(
            {"book.tex": "\\documentclass{book}\n"}, name="options-template"
        )
        cases = (
            ("--language", "en"),
            ("--title", "A title"),
            ("--course-name", "A course"),
        )
        for index, (option, value) in enumerate(cases):
            with self.subTest(option=option):
                output = self.root / f"option-out-{index}"
                code, _stdout, stderr = self.run_init(
                    "--template", template, "--output", output, option, value
                )
                self.assert_failed_without_output(code, stderr, output)
                self.assertIn("not applicable", stderr.lower())
        self.assertEqual(
            (template / "book.tex").read_text(encoding="utf-8"),
            "\\documentclass{book}\n",
        )

    def test_custom_template_without_magic_has_null_engine_and_no_rewrite(self) -> None:
        template = self.write_template(
            {
                "book.tex": (
                    "\\documentclass[12pt]{book}\n"
                    "\\usepackage{preamble/packages}\n"
                    "\\begin{document}Book\\end{document}\n"
                ),
                "preamble/packages.tex": (
                    "\\usepackage{pgfplots}\n"
                    "\\pgfplotsset{compat=newest}\n"
                    "\\definecolor{accent}{HTML}{1F5FBF}\n"
                ),
            },
            name="no-magic"
        )
        output = self.root / "no-magic-out"
        code, _stdout, stderr = self.run_init("--template", template, "--output", output)
        self.assertEqual(code, 0, stderr)
        receipt = self.receipt(output)
        self.assertIsNone(receipt["suggested_engine"])
        self.assertIsNone(receipt["engine_source"])
        self.assertIn("confirm", receipt["engine_note"].lower())
        self.assertEqual(
            (output / "preamble/packages.tex").read_bytes(),
            (template / "preamble/packages.tex").read_bytes(),
        )
        self.assertIn(b"compat=newest", (output / "preamble/packages.tex").read_bytes())
        self.assertEqual(
            (output / "book.tex").read_bytes(), (template / "book.tex").read_bytes()
        )

    def test_builtin_snapshot_matches_manifest_and_is_unchanged(self) -> None:
        manifest = json.loads((BUILTIN / "template-source.json").read_text(encoding="utf-8"))
        before = {
            path.relative_to(BUILTIN).as_posix(): sha(path.read_bytes())
            for path in BUILTIN.rglob("*")
            if path.is_file()
        }
        self.assertEqual(
            set(before),
            set(manifest["files"]) | {"template-source.json"},
        )
        for relative, expected in manifest["files"].items():
            self.assertEqual(before[relative], expected, relative)

        for language in ("zh", "en"):
            output = self.root / f"snapshot-{language}"
            code, _stdout, stderr = self.run_init(
                "--output", output, "--language", language
            )
            self.assertEqual(code, 0, stderr)

        after = {
            path.relative_to(BUILTIN).as_posix(): sha(path.read_bytes())
            for path in BUILTIN.rglob("*")
            if path.is_file()
        }
        self.assertEqual(before, after)


    def test_literal_inputs_with_cache_like_extensions_are_preserved(self) -> None:
        template = self.write_template({
            "book.tex": "% !TeX program = pdflatex\n\\documentclass{book}\n"
                        "\\begin{document}\\input{chapters/content}\\end{document}\n",
            "chapters/content.tex": "\\input{data/observations.out}\n"
                                    "\\input data/explanation.log\n",
            "data/observations.out": "Real source input.\n",
            "data/explanation.log": "Another explicit source input.\n",
            "book.log": "An unreferenced generated compiler log.\n",
            ".git": "gitdir: /a/different/worktree\n",
        })
        output = self.root / "literal-inputs"
        code, _stdout, stderr = self.run_init("--template", template, "--output", output)
        self.assertEqual(code, 0, stderr)
        for relative in ["data/observations.out", "data/explanation.log"]:
            self.assertEqual((output / relative).read_bytes(), (template / relative).read_bytes())
        self.assertFalse((output / "book.log").exists())
        self.assertFalse((output / ".git").exists())


if __name__ == "__main__":
    unittest.main()
