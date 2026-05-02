#!/usr/bin/env python3
"""
IPRight PDF Export Utility
Converts generated .docx files to PDF format.
Requires LibreOffice to be installed (headless mode).
"""

import os
import subprocess
import sys
from pathlib import Path


def docx_to_pdf(docx_path: str, output_dir: str | None = None) -> str | None:
    """Convert a .docx file to PDF using LibreOffice headless."""
    if not os.path.exists(docx_path):
        print(f"Error: File not found: {docx_path}")
        return None

    if output_dir is None:
        output_dir = os.path.dirname(docx_path)

    os.makedirs(output_dir, exist_ok=True)

    try:
        result = subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to", "pdf",
                "--outdir", output_dir,
                docx_path,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            base = Path(docx_path).stem
            pdf_path = os.path.join(output_dir, f"{base}.pdf")
            if os.path.exists(pdf_path):
                return pdf_path
        else:
            print(f"LibreOffice error: {result.stderr}")
    except FileNotFoundError:
        print("LibreOffice not found. Install with: brew install libreoffice")
    except subprocess.TimeoutExpired:
        print("PDF conversion timed out")
    except Exception as e:
        print(f"PDF conversion error: {e}")

    return None


def convert_all_docs(output_dir: str) -> list[str]:
    """Convert all .docx files in a directory to PDF."""
    results = []
    for f in Path(output_dir).rglob("*.docx"):
        pdf = docx_to_pdf(str(f), output_dir)
        if pdf:
            results.append(pdf)
            print(f"  ✅ {f.name} -> {Path(pdf).name}")
        else:
            print(f"  ❌ {f.name}")
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/export_pdf.py <docx_path_or_dir>")
        sys.exit(1)

    path = sys.argv[1]
    if os.path.isdir(path):
        convert_all_docs(path)
    else:
        pdf = docx_to_pdf(path)
        if pdf:
            print(f"PDF generated: {pdf}")
