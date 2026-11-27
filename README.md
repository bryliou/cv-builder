# Local CV Builder — ATS & Designed PDF

A small local app that converts your editable Markdown CV into **searchable PDFs**. No account, web service, or upload is needed. Rendering is done through the Chrome/Chromium browser already installed on your computer.

## Quick start (macOS)

1. Unzip the folder somewhere permanent, e.g. `~/Documents/cv-builder`.
2. Put your CV content in `cv.md`.
3. Install **Python 3** and **Google Chrome** if they are not installed already.
4. In Terminal, enter the folder and run:

   ```bash
   chmod +x cv-build 'Generate CV.command'
   ./cv-build cv.md
   ```

   The **first run only** creates `.venv` and installs two small Python packages. Later runs use the local environment and do not need network access.

   Or double-click **Generate CV.command** in Finder to make both PDFs. If macOS blocks an unsigned script, use Terminal or right-click → Open.

## Common commands

| Command | Result |
| --- | --- |
| `./cv-build cv.md` | `cv.pdf` — **ATS-friendly default**, single column |
| `./cv-build cv.md --layout both` | `cv.pdf` (ATS) and `cv_designed.pdf` (two columns) |
| `./cv-build cv.md --layout two` | Two-column `cv.pdf` |
| `./cv-build cv.md -o company.pdf` | Single-column `company.pdf` |
| `./cv-build cv.md --html` | PDF + HTML preview |
| `./cv-build cv.md --html-only` | HTML preview without Chrome |
| `./cv-build cv.md --engine weasyprint` | Use the optional WeasyPrint renderer |
| `./cv-build note.md --letter --header-from cv.md` | `note.pdf` — cover letter with the CV's Arial header and today's date (`--date "…"`, `--no-date`) |
| `./cv-build --help` | Full command options |

Each Markdown file can represent a different vacancy. E.g. `./cv-build company.md -o company.pdf`.

## Editing the look

- ATS layout: `template/single.css` — change `--font-size` (default 10.5pt), `--line-height`, accent colour, or `@page` margins.
- Designed layout: `template/two-column.css` — retains the previous blue/white style.
- **Font:** Karla is optional. If you want to keep using your own local Karla font files, put them in `template/fonts/` under the filenames `Karla.ttf` and `Karla-Italic.ttf`. They are **not distributed with this builder**. Without them, the app uses an available sans-serif font.
- Photo: `--photo /path/to/picture.jpg` is supported for the **designed layout only**. The ATS PDF deliberately has no photo.

### Input format

Use simple Markdown. The recommended header is:

```md
# Alex Example
**Senior QA Engineer**
Amsterdam, Netherlands · +31 6 0000 0000 · alex@example.com
[LinkedIn](https://www.linkedin.com/in/alex-example/)

## Profile
Short professional introduction.

## Core skills
- **Backend and APIs:** REST APIs, integrations, troubleshooting.

## Professional experience
### Senior QA Engineer — Example Co
*January 2022 – Present*
- One achievement, ideally with real evidence.

## Certification
Your certificate.

## Education
Your degree.
```

The tool also accepts your existing YAML front-matter files with `# Main` and `# Sidebar` sections. The single-column mode linearises those sections in the order: profile, skills, experience, projects, certifications, education, languages. The two-column mode uses the sidebar hints.

## ATS/readability notes

The single-column output has: one reading stream, proper heading tags, selectable text, visible URLs, ordinary bullets, no tables and no text inside images. This **reduces** parsing risks; no PDF layout can guarantee compatibility with every ATS vendor. If an application portal asks for DOCX, submit DOCX instead.

Check the exported PDF once before submitting: confirm the page count, copy/paste the text into a plain text editor, and verify your dates and contact details.

## Requirements / privacy

- Python 3.10+ (3.11+ recommended)
- Chrome/Chromium (detected automatically on macOS and Linux; use `--chrome` if needed). If Chrome is unavailable or hangs, you can install an optional PDF fallback with `.venv/bin/python -m pip install weasyprint`. Then `--engine weasyprint` will use it; in the default `auto` mode it is used when Chrome fails.
- The script writes PDFs and temporary HTML locally. No CV data is sent to a remote CV service. Google's local Chrome may follow your browser's own update/privacy settings, but this generator requests no network resources.
- No font files are included in the download. Use your own existing fonts or the system fallback.
