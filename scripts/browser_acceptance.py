#!/usr/bin/env python3
"""Create a desktop/mobile browser receipt for a standalone textbook HTML."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--chromium", type=Path, required=True)
    parser.add_argument("--playwright-root", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--ready-expression")
    parser.add_argument("--math-selector", default=".math")
    parser.add_argument("--require-rendered-math", action="store_true")
    parser.add_argument("--expected-math", type=int)
    parser.add_argument("--font-family")
    parser.add_argument("--search-input", default="#chapter-search")
    parser.add_argument("--chapter-selector", default="article.chapter")
    parser.add_argument("--hidden-class", default="search-hidden")
    parser.add_argument("--query")
    parser.add_argument("--query-min", type=int)
    parser.add_argument("--query-max", type=int)
    parser.add_argument("--screenshot-dir", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    html_path = args.html.expanduser().resolve()
    chromium = args.chromium.expanduser().resolve()
    report_path = args.report.expanduser().resolve()
    if html_path.is_symlink() or not html_path.is_file():
        raise ValueError(f"HTML must be an ordinary non-symlink file: {html_path}")
    if chromium.is_symlink() or not chromium.is_file():
        raise ValueError(f"Chromium must be an ordinary non-symlink file: {chromium}")
    playwright_root = args.playwright_root.expanduser().resolve() if args.playwright_root else None
    if playwright_root:
        root = str(playwright_root)
        if root not in sys.path:
            sys.path.insert(0, root)
    try:
        import playwright as playwright_package
        import greenlet as greenlet_package
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError(
            "Playwright import failed; run this script with a Python interpreter matching "
            f"the native-extension ABI under --playwright-root (current: {sys.executable}, "
            f"Python {platform.python_version()}): {error}"
        ) from error

    if (args.query is None) != (args.query_min is None) or (args.query is None) != (args.query_max is None):
        raise ValueError("--query, --query-min, and --query-max must be provided together")
    if args.query is not None and (args.query_min < 1 or args.query_max < args.query_min):
        raise ValueError("query bounds must satisfy 1 <= min <= max")
    screenshot_dir = args.screenshot_dir.expanduser().resolve() if args.screenshot_dir else None
    if screenshot_dir:
        screenshot_dir.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-background-networking",
                "--disable-component-update",
                "--disable-sync",
                "--no-first-run",
            ],
        )
        try:
            for label, width, height in (("desktop", 1440, 900), ("mobile", 390, 844)):
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                requests: list[str] = []
                blocked_http: list[str] = []
                page.on("request", lambda request: requests.append(request.url))

                def route_handler(route: Any) -> None:
                    url = route.request.url
                    if url.startswith(("http://", "https://")):
                        blocked_http.append(url)
                        route.abort()
                    else:
                        route.continue_()

                page.route("**/*", route_handler)
                page.goto(html_path.as_uri(), wait_until="load", timeout=180_000)
                if args.ready_expression:
                    page.wait_for_function(args.ready_expression, timeout=180_000)
                page.evaluate("document.fonts.ready")
                base = page.evaluate(
                    """([mathSelector,fontFamily]) => {
                      const root=document.documentElement;const body=document.body;
                      const math=[...document.querySelectorAll(mathSelector)];
                      const tables=[...document.querySelectorAll('table')];
                      return {
                        scrollWidth:root.scrollWidth,clientWidth:root.clientWidth,
                        horizontalOverflow:root.scrollWidth>root.clientWidth+1,
                        htmlOverflowX:getComputedStyle(root).overflowX,
                        bodyOverflowX:getComputedStyle(body).overflowX,
                        unwrappedTables:tables.filter(t=>!t.closest('.table-wrap')).length,
                        tableCount:tables.length,
                        mathCount:math.length,
                        renderedMathCount:math.filter(n=>n.querySelector('.katex')).length,
                        fontReady:fontFamily?document.fonts.check('16px '+fontFamily):null
                      };
                    }""",
                    [args.math_selector, args.font_family],
                )
                search: dict[str, Any] = {"status": "NOT_REQUESTED"}
                if args.query is not None:
                    input_locator = page.locator(args.search_input)
                    if input_locator.count() != 1:
                        search = {"status": "FAIL", "reason": "search input count", "count": input_locator.count()}
                    else:
                        input_locator.fill(args.query)
                        visible = page.locator(
                            f"{args.chapter_selector}:not(.{args.hidden_class})"
                        ).count()
                        input_locator.fill("")
                        restored = page.locator(
                            f"{args.chapter_selector}:not(.{args.hidden_class})"
                        ).count()
                        total = page.locator(args.chapter_selector).count()
                        search = {
                            "status": "PASS"
                            if args.query_min <= visible <= args.query_max and restored == total
                            else "FAIL",
                            "query": args.query,
                            "visible_matches": visible,
                            "minimum": args.query_min,
                            "maximum": args.query_max,
                            "restored_chapters": restored,
                            "total_chapters": total,
                        }
                screenshot_path = None
                screenshot_sha = None
                if screenshot_dir:
                    screenshot_path = screenshot_dir / f"browser-acceptance-{label}.png"
                    if screenshot_path.exists() or screenshot_path.is_symlink():
                        raise FileExistsError(f"screenshot already exists: {screenshot_path}")
                    page.screenshot(path=str(screenshot_path), full_page=False)
                    screenshot_sha = sha256_file(screenshot_path)
                result = {
                    **base,
                    "search": search,
                    "blocked_http_requests": blocked_http,
                    "automatic_non_file_requests": [
                        value for value in requests if not value.startswith(("file:", "data:", "about:"))
                    ],
                    "screenshot_path": str(screenshot_path) if screenshot_path else None,
                    "screenshot_sha256": screenshot_sha,
                }
                results[label] = result
                if result["horizontalOverflow"]:
                    errors.append({"kind": "document_horizontal_overflow", "viewport": label})
                if result["htmlOverflowX"] in {"hidden", "clip"} or result["bodyOverflowX"] in {"hidden", "clip"}:
                    errors.append({"kind": "document_overflow_mask", "viewport": label})
                if result["unwrappedTables"]:
                    errors.append(
                        {"kind": "unwrapped_tables", "viewport": label, "count": result["unwrappedTables"]}
                    )
                if args.expected_math is not None and result["mathCount"] != args.expected_math:
                    errors.append(
                        {
                            "kind": "math_count",
                            "viewport": label,
                            "expected": args.expected_math,
                            "actual": result["mathCount"],
                        }
                    )
                if args.require_rendered_math and result["renderedMathCount"] != result["mathCount"]:
                    errors.append(
                        {
                            "kind": "rendered_math_count",
                            "viewport": label,
                            "expected": result["mathCount"],
                            "actual": result["renderedMathCount"],
                        }
                    )
                if args.font_family and result["fontReady"] is not True:
                    errors.append({"kind": "font_not_ready", "viewport": label, "font": args.font_family})
                if search["status"] == "FAIL":
                    errors.append({"kind": "interaction_probe", "viewport": label, "result": search})
                if result["blocked_http_requests"] or result["automatic_non_file_requests"]:
                    errors.append({"kind": "automatic_external_request", "viewport": label})
                context.close()
        finally:
            browser.close()

    report = {
        "schema": "TextbookBrowserAcceptance/v1",
        "status": "PASS" if not errors else "FAIL",
        "html_path": str(html_path),
        "html_sha256": sha256_file(html_path),
        "browser_runtime": {
            "python_executable": str(Path(sys.executable).resolve()),
            "python_version": platform.python_version(),
            "playwright_root": str(playwright_root) if playwright_root else None,
            "playwright_package": str(Path(playwright_package.__file__).resolve()),
            "greenlet_package": str(Path(greenlet_package.__file__).resolve()),
            "chromium_executable": str(chromium),
            "chromium_sha256": sha256_file(chromium),
        },
        "viewports": results,
        "errors": errors,
    }
    without_hash = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    report["report_sha256"] = hashlib.sha256(without_hash.encode("utf-8")).hexdigest()
    atomic_write_new(report_path, report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "html_sha256": report["html_sha256"],
                "error_count": len(errors),
                "report": str(report_path),
                "report_sha256": report["report_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
