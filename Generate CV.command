#!/bin/bash
# macOS Finder: double-click to build cv.pdf and cv_designed.pdf.
set -e
cd "$(dirname "$0")"
./cv-build cv.md --layout both
printf '\nYour PDFs are ready in this folder.\n'
if command -v open >/dev/null 2>&1; then open cv.pdf; fi
