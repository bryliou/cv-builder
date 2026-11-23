#!/usr/bin/env python3
"""Build a readable, searchable CV PDF from Markdown (ATS-first by default).

Dependencies: PyYAML, and either markdown-it-py or Python-Markdown.
PDF renderer: local Chrome/Chromium (Mac/Linux), with a safe temporary profile.

Examples:
  ./cv-build cv.md                     # ATS-friendly single-column PDF
  ./cv-build cv.md --layout both       # ATS + designed two-column PDFs
  ./cv-build cv.md --layout two        # original two-column style
  ./cv-build cv.md --html              # also save the HTML preview
"""
from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

try:
    import yaml
except ImportError:
    sys.exit("Missing PyYAML. Run: python3 -m pip install -r requirements.txt")

try:
    from markdown_it import MarkdownIt
    _md_renderer = MarkdownIt("commonmark", {"breaks": False, "html": True}).enable("table")
    def markdown_to_html(raw: str) -> str:
        return _md_renderer.render(raw)
except ImportError:
    try:
        import markdown
        def markdown_to_html(raw: str) -> str:
            return markdown.markdown(raw, extensions=["sane_lists", "attr_list"])
    except ImportError:
        sys.exit("Missing Markdown renderer. Run: python3 -m pip install -r requirements.txt")

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template"
CONTACT_KEYS = ("location", "email", "phone")
LINK_KEYS = ("linkedin", "website", "github", "portfolio")
PHOTO_NAMES = ("photo", "avatar", "headshot", "profile-photo", "profile_photo")
PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff")
LABELS = {"location": "location", "address": "location", "city": "location",
          "email": "email", "e-mail": "email", "phone": "phone", "mobile": "phone",
          "linkedin": "linkedin", "website": "website", "portfolio": "portfolio",
          "github": "github", "photo": "photo", "picture": "photo"}
SIDE_RE = re.compile(r"skill|certif|language|education|social|link", re.I)
LAST_RE = re.compile(r"hobb|interest", re.I)
PROFILE_RE = re.compile(r"^(profile|summary|professional summary|about me|about)$", re.I)
SKILLS_RE = re.compile(r"skill|technolog", re.I)
EXPERIENCE_RE = re.compile(r"experience|employment|work history", re.I)


ICONS = {  # white glyph on a filled circle (two-column sidebar)
    "location": '<path d="M12 6.5a3.6 3.6 0 0 0-3.6 3.6c0 2.7 3.6 6.4 3.6 6.4s3.6-3.7 3.6-6.4A3.6 3.6 0 0 0 12 6.5zm0 5a1.4 1.4 0 1 1 0-2.8 1.4 1.4 0 0 1 0 2.8z"/>',
    "email": '<path d="M7 8.5h10a.8.8 0 0 1 .8.8v.3L12 13 6.2 9.6v-.3a.8.8 0 0 1 .8-.8zm-.8 2.6L12 14.5l5.8-3.4v4.6a.8.8 0 0 1-.8.8H7a.8.8 0 0 1-.8-.8z"/>',
    "phone": '<path d="M9.3 6.6l1.4 2.6-.9 1.3a7 7 0 0 0 3.7 3.7l1.3-.9 2.6 1.4-.5 2a1 1 0 0 1-1 .7A10 10 0 0 1 6.6 8.1a1 1 0 0 1 .7-1z"/>',
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def split_front_matter(raw: str) -> tuple[dict, str]:
    raw = raw.lstrip("\ufeff")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", raw, re.S)
    if not match:
        return {}, raw
    metadata = yaml.safe_load(match.group(1)) or {}
    if not isinstance(metadata, dict):
        raise ValueError("YAML front matter must be a mapping (key: value).")
    return metadata, match.group(2)


def split_sections(raw: str, side: bool) -> tuple[str, list[dict]]:
    parts = re.split(r"^(##\s+[^\n]+)$", raw, flags=re.M)
    sections = []
    for i in range(1, len(parts), 2):
        heading = re.sub(r"^##\s+", "", parts[i]).strip()
        sections.append({"title": heading, "text": parts[i] + parts[i + 1], "side": side})
    return parts[0], sections


def parse_plain_header(body: str, meta: dict) -> tuple[str, str]:
    """Extract name, title and contact info from a simple '# Name' CV.

    Unrecognised header lines are retained; they are never discarded.
    """
    match = re.match(r"\s*#\s+([^\n]+)\n(.*?)(?=^##\s|\Z)", body, re.S | re.M)
    if not match:
        return body, ""
    meta.setdefault("name", match.group(1).strip())
    rest = []
    for line in match.group(2).splitlines():
        s = line.strip()
        if not s:
            continue
        photo_match = re.fullmatch(r"!\[[^]]*\]\(([^)]+)\)", s)
        if photo_match:
            meta.setdefault("photo", photo_match.group(1))
            continue
        title_match = re.fullmatch(r"\*\*(.+?)\*\*", s)
        if title_match and not meta.get("title"):
            meta["title"] = title_match.group(1).strip()
            continue
        keyval = re.fullmatch(r"(?:\*\*)?([\w-]+):?(?:\*\*)?:\s*(.+)", s)
        if keyval and LABELS.get(keyval.group(1).lower()):
            meta.setdefault(LABELS[keyval.group(1).lower()], keyval.group(2).strip())
            continue
        link = re.fullmatch(r"\[([^]]+)\]\((https?://[^)]+)\)", s)
        if link:
            label = link.group(1).lower()
            key = ("linkedin" if "linkedin" in label else "github" if "github" in label else "website")
            meta.setdefault(key, link.group(2))
            continue
        # A common exported CV header line: city · phone · email
        bits = [p.strip() for p in re.split(r"\s+[·|]\s+", s)]
        if len(bits) >= 2 and any("@" in b for b in bits):
            leftovers = []
            for bit in bits:
                if "@" in bit and not bit.startswith("http"):
                    meta.setdefault("email", bit)
                elif re.fullmatch(r"\+?[0-9][0-9 ()+.-]{6,}", bit):
                    meta.setdefault("phone", bit)
                elif bit.startswith("http"):
                    meta.setdefault("linkedin" if "linkedin" in bit else "website", bit)
                else:
                    leftovers.append(bit)
            if leftovers:
                meta.setdefault("location", ", ".join(leftovers))
            continue
        if not meta.get("title") and not s.startswith(("*", "_", "[", "http")):
            meta["title"] = s
            continue
        rest.append(s)
    following = body[match.end():]
    return following, "\n".join(rest)


def parse(path: Path) -> tuple[dict, str, str, list[dict]]:
    meta, raw = split_front_matter(path.read_text(encoding="utf-8"))
    chunks = re.split(r"^#\s+(Sidebar|Main)\s*$", raw, flags=re.M | re.I)
    if len(chunks) > 1:
        areas = {chunks[i].lower(): chunks[i + 1] for i in range(1, len(chunks), 2)}
        side_intro, sides = split_sections(areas.get("sidebar", ""), True)
        main_intro, mains = split_sections(areas.get("main", ""), False)
        sections = mains + sides
    else:
        raw, header_extra = parse_plain_header(raw, meta)
        main_intro, sections = split_sections(raw, False)
        main_intro = (header_extra + "\n\n" + main_intro).strip()
        side_intro = ""
        for section in sections:
            section["side"] = bool(SIDE_RE.search(section["title"]))
    if not meta.get("name"):
        raise ValueError("CV has no name. Use '# Your Name' or YAML front matter 'name: ...'.")
    return meta, side_intro, main_intro, sections


def priority(section: dict) -> int:
    title = section["title"].strip()
    if PROFILE_RE.search(title):
        return 0
    if SKILLS_RE.search(title):
        return 1
    if EXPERIENCE_RE.search(title):
        return 2
    if LAST_RE.search(title):
        return 9
    if re.search(r"project|portfolio", title, re.I):
        return 3
    if re.search(r"certif", title, re.I):
        return 4
    if re.search(r"education", title, re.I):
        return 5
    if re.search(r"language", title, re.I):
        return 6
    return 7


def md(raw: str) -> str:
    if not raw.strip():
        return ""
    # Make a standard Markdown list work even when the writer omitted a blank line.
    raw = re.sub(r"^(?![ \t]*[-*+] |[ \t]*$)(.+)\n(?=[ \t]*[-*+] )", r"\1\n\n", raw, flags=re.M)
    return markdown_to_html(raw)


def contact_html(meta: dict) -> str:
    chunks = []
    for key in CONTACT_KEYS + LINK_KEYS:
        value = str(meta.get(key, "")).strip()
        if not value:
            continue
        if key == "email":
            markup = f'<a href="mailto:{esc(value)}">{esc(value)}</a>'
        elif key == "phone":
            digits = re.sub(r"[^+0-9]", "", value)
            markup = f'<a href="tel:{esc(digits)}">{esc(value)}</a>'
        elif key in LINK_KEYS:
            dest = value if value.startswith(("https://", "http://")) else "https://" + value
            markup = f'<a href="{esc(dest)}">{esc(value)}</a>'
        else:
            markup = esc(value)
        chunks.append(f'<span>{markup}</span>')
    return '<div class="contact">' + "".join(chunks) + "</div>" if chunks else ""


def contact_list_html(meta: dict) -> str:
    """Two-column sidebar: one contact per line with an icon (links go to 'Social profiles')."""
    items = []
    for key in CONTACT_KEYS:
        value = str(meta.get(key, "")).strip()
        if not value:
            continue
        if key == "email":
            text = f'<a href="mailto:{esc(value)}">{esc(value)}</a>'
        elif key == "phone":
            text = f'<a href="tel:{esc(re.sub(r"[^+0-9]", "", value))}">{esc(value)}</a>'
        else:
            text = esc(value)
        svg = (f'<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="12" fill="currentColor"/>'
               f'<g fill="#fff">{ICONS[key]}</g></svg>')
        items.append(f"<li>{svg}<span>{text}</span></li>")
    return f'<ul class="contact">{"".join(items)}</ul>' if items else ""


def document(meta: dict, css_file: str, body: str) -> str:
    css_url = (TEMPLATE / css_file).resolve().as_uri()
    return ("<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>{esc(meta['name'])} — CV</title><link rel=\"stylesheet\" href=\"{css_url}\">"
            f"</head><body>{body}</body></html>")


def render_single(meta: dict, side_intro: str, main_intro: str, sections: list[dict]) -> str:
    # ATS: header first, then one linear content stream, no tables, columns, or photo.
    header = (f'<header><h1 class="name">{esc(meta["name"])}</h1>'
              + (f'<div class="title">{esc(meta["title"])}</div>' if meta.get("title") else "")
              + contact_html(meta) + "</header>")
    ordered = sorted(sections, key=priority)
    profile_exists = any(PROFILE_RE.fullmatch(s["title"]) for s in sections)
    intro = (f'<section class="cv-section profile"><h2>Profile</h2>{md(main_intro)}</section>'
             if main_intro.strip() and not profile_exists else md(main_intro))
    blocks = []
    for sec in ordered:
        block_class = "cv-section" + (" skills-section" if SKILLS_RE.search(sec["title"]) else "")
        blocks.append(f'<section class="{block_class}">{md(sec["text"])}</section>')
    if side_intro.strip():
        blocks.append(f'<section class="cv-section">{md(side_intro)}</section>')
    return document(meta, "single.css", header + intro + "".join(blocks))


def render_two(meta: dict, side_intro: str, main_intro: str, sections: list[dict]) -> str:
    side = f'<div class="name">{esc(meta["name"])}</div>'
    if meta.get("title"):
        side += f'<div class="title">{esc(meta["title"])}</div>'
    if meta.get("photo"):
        side += f'<img class="photo" src="{esc(meta["photo"])}" alt="">'
    side += contact_list_html(meta) + md(side_intro)
    links = "".join(f'<p><a href="{esc(meta[k])}">{esc(meta[k])}</a></p>'
                    for k in LINK_KEYS if meta.get(k))
    if links and not any(re.search("social|links", s["title"], re.I) for s in sections):
        side += f"<h2>Social profiles</h2>{links}"
    side += "".join(md(s["text"]) for s in sections if s["side"])
    primary = [s for s in sections if not s["side"]]
    primary.sort(key=lambda s: bool(LAST_RE.search(s["title"])))
    main = md(main_intro) + "".join(md(s["text"]) for s in primary)
    return document(meta, "two-column.css", f'<div class="panel"></div>'
                    f'<div class="page"><aside class="side">{side}</aside>'
                    f'<main class="main">{main}</main></div>')


def find_photo(md_path: Path, meta: dict, requested: str | None, build: Path) -> str | None:
    if requested:
        possible = Path(requested).expanduser()
    elif meta.get("photo"):
        possible = Path(str(meta["photo"])).expanduser()
        if not possible.is_absolute():
            possible = md_path.parent / possible
    else:
        possible = next((folder / f"{name}{ext}" for folder in
                         (md_path.parent, md_path.parent / "assets") for name in PHOTO_NAMES
                         for ext in PHOTO_EXTS if (folder / f"{name}{ext}").is_file()), None)
    if possible is None:
        return None
    if not possible.is_file():
        print(f"Warning: photo not found: {possible}", file=sys.stderr)
        return None
    if possible.suffix.lower() in (".heic", ".heif", ".tif", ".tiff"):
        converter = shutil.which("sips")
        if not converter:
            print("Warning: photo is HEIC/TIFF, requires macOS 'sips'. Skipping photo.", file=sys.stderr)
            return None
        converted = build / "photo.jpg"
        subprocess.run([converter, "-s", "format", "jpeg", str(possible), "--out", str(converted)], check=True)
        possible = converted
    return possible.resolve().as_uri()


def detect_chrome(override: str | None) -> str:
    mac_paths = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                 "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    candidates = [override, os.getenv("CV_CHROME"), *mac_paths]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("Chrome/Chromium not found. Install Chrome or pass --chrome /path/to/chrome. "
                       "You can still use --html-only to preview in a browser.")


def make_pdf(html_path: Path, output: Path, chrome: str | None,
             engine: str = "auto", timeout: int = 35) -> str:
    """Render via Chrome, optionally falling back to local WeasyPrint.

    A hung or misconfigured browser should not freeze the CV workflow indefinitely.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    chrome_error = ""
    if engine in ("auto", "chrome") and chrome:
        with tempfile.TemporaryDirectory(prefix="cv-chrome-") as profile:
            args = [chrome, "--headless=new", "--disable-gpu", "--disable-dev-shm-usage",
                    "--no-pdf-header-footer", f"--user-data-dir={profile}",
                    "--no-first-run", "--no-default-browser-check", "--disable-component-update",
                    "--disable-background-networking", "--disable-sync", "--disable-extensions",
                    "--allow-file-access-from-files", f"--print-to-pdf={output}", html_path.as_uri()]
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                args.insert(1, "--no-sandbox")
            try:
                proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
                if proc.returncode == 0 and output.is_file() and output.stat().st_size > 1000:
                    return "Chrome"
                chrome_error = f"Chrome exit {proc.returncode}: {proc.stderr[-600:]}"
            except subprocess.TimeoutExpired:
                chrome_error = f"Chrome timed out after {timeout} seconds"
        output.unlink(missing_ok=True)
    elif engine == "chrome":
        raise RuntimeError("Chrome not installed or not found. Use --html-only or install Chrome.")

    if engine in ("auto", "weasyprint"):
        try:
            from weasyprint import HTML
            HTML(filename=str(html_path)).write_pdf(str(output))
            if output.is_file() and output.stat().st_size > 1000:
                if chrome_error:
                    print(f"Note: {chrome_error}. Used local WeasyPrint renderer instead.", file=sys.stderr)
                return "WeasyPrint"
            raise RuntimeError("WeasyPrint returned no usable PDF")
        except ImportError as exc:
            hint = "Optionally install fallback renderer: python3 -m pip install weasyprint"
            raise RuntimeError(f"{chrome_error}\n{hint}" if chrome_error else hint) from exc
    raise RuntimeError(chrome_error or "No PDF renderer available")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("src", nargs="?", default=str(ROOT / "cv.md"), help="Source Markdown file")
    parser.add_argument("-l", "--layout", choices=("single", "two", "both"),
                        help="single (ATS default), two (designed), both (two PDFs)")
    parser.add_argument("-o", "--out", help="Base output PDF filename; --layout both adds _designed")
    parser.add_argument("--photo", help="Optional photo for two-column only")
    parser.add_argument("--no-photo", action="store_true", help="Remove photo in two-column")
    parser.add_argument("--html", action="store_true", help="Keep intermediate HTML next to PDF")
    parser.add_argument("--html-only", action="store_true", help="Generate HTML previews without Chrome")
    parser.add_argument("--chrome", help="Explicit path to Chrome/Chromium executable")
    parser.add_argument("--engine", choices=("auto", "chrome", "weasyprint"), default="auto",
                        help="PDF renderer: auto (Chrome, then optional WeasyPrint), chrome, weasyprint")
    parser.add_argument("--timeout", type=int, default=35, help="Chrome launch/render timeout in seconds")
    args = parser.parse_args()
    source = Path(args.src).expanduser().resolve()
    if not source.is_file():
        parser.error(f"Source Markdown file not found: {source}")
    try:
        meta, side_intro, main_intro, sections = parse(source)
        layout = args.layout or meta.get("layout", "single")
        if layout not in ("single", "two", "both"):
            raise ValueError(f"Unsupported layout: {layout}")
        base = Path(args.out).expanduser().resolve() if args.out else (
            source.parent / str(meta.get("output", source.with_suffix(".pdf").name))).resolve()
        build = source.parent / ".cv-build"
        build.mkdir(exist_ok=True)
        meta["photo"] = None if args.no_photo else find_photo(source, meta, args.photo, build)
        chrome = None
        if not args.html_only and args.engine in ("auto", "chrome"):
            try:
                chrome = detect_chrome(args.chrome)
            except RuntimeError:
                if args.engine == "chrome":
                    raise
        for which in (("single", "two") if layout == "both" else (layout,)):
            target = (base.with_name(base.stem + "_designed" + base.suffix)
                      if layout == "both" and which == "two" else base)
            markup = (render_single(meta, side_intro, main_intro, sections) if which == "single"
                      else render_two(meta, side_intro, main_intro, sections))
            output_html = (target.with_suffix(".html") if args.html or args.html_only
                           else build / f"{source.stem}-{which}.html")
            output_html.write_text(markup, encoding="utf-8")
            if args.html_only:
                print(f"HTML: {output_html}")
                continue
            pdf_engine = make_pdf(output_html, target, chrome, args.engine, args.timeout)
            if not args.html:
                output_html.unlink(missing_ok=True)
            print(f"PDF ({'ATS / single column' if which == 'single' else 'designed / two column'}, {pdf_engine}): {target}")
        return 0
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
