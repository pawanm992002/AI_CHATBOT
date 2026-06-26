def _extract_pages(doc) -> str:
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()
        if text:
            lines = text.splitlines()
            cleaned_lines = []
            prev_blank = False
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    if not prev_blank:
                        cleaned_lines.append("")
                    prev_blank = True
                else:
                    cleaned_lines.append(stripped)
                    prev_blank = False

            page_text = "\n".join(cleaned_lines).strip()
            if page_text:
                pages.append(f"## Page {page_num + 1}\n\n{page_text}")

    doc.close()
    return "\n\n".join(pages)


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file and return as markdown-formatted text."""
    try:
        import fitz
    except ImportError:
        raise ImportError("PyMuPDF (fitz) is required for PDF parsing. Install with: pip install PyMuPDF")

    doc = fitz.open(file_path)
    return _extract_pages(doc)


def extract_text_from_pdf_from_bytes(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes and return as markdown-formatted text."""
    try:
        import fitz
    except ImportError:
        raise ImportError("PyMuPDF (fitz) is required for PDF parsing. Install with: pip install PyMuPDF")

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    return _extract_pages(doc)
