"""PDF text extraction for real-world ARTCB tests."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pypdf import PdfReader

DEFAULT_BOOK_PATHS = (
    Path(os.getenv("ARTCB_TEST_BOOK_PDF", "")),
    Path("data/fixtures/wailly_le_roi_de_l_inconnu.pdf"),
    Path("/home/lvx/Downloads/wailly_le_roi_de_l_inconnu.pdf"),
    Path("/workspace/data/fixtures/wailly_le_roi_de_l_inconnu.pdf"),
)

BOOK_FILENAME = "wailly_le_roi_de_l_inconnu.pdf"


def resolve_book_path() -> Path | None:
    """Find the Wailly test book PDF on disk."""
    candidates: list[Path] = []
    env_path = os.getenv("ARTCB_TEST_BOOK_PDF")
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(p for p in DEFAULT_BOOK_PATHS if str(p) and str(p) != ".")
    for path in candidates:
        if path.is_file():
            return path
    return None


def _extract_page_text(page_data: tuple[str, int]) -> tuple[int, str]:
    """Extract text from a single page (for parallel processing)."""
    path_str, page_num = page_data
    reader = PdfReader(path_str)
    page = reader.pages[page_num]
    text = page.extract_text() or ""
    return (page_num, text.strip() if text.strip() else "")


def extract_pdf_text(path: Path, max_pages: int | None = None, parallel: bool = True) -> str:
    """Extract text from PDF with optional parallel processing (threads — no fork)."""
    reader = PdfReader(str(path))
    total_pages = len(reader.pages)
    num_pages = min(max_pages, total_pages) if max_pages else total_pages

    if not parallel or num_pages < 4:
        pages = reader.pages[:num_pages]
        chunks: list[str] = []
        for page in pages:
            text = page.extract_text() or ""
            if text.strip():
                chunks.append(text.strip())
        return "\n\n".join(chunks)

    page_data = [(str(path), i) for i in range(num_pages)]
    workers = min(4, num_pages)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        results = list(executor.map(_extract_page_text, page_data))

    results.sort(key=lambda x: x[0])
    chunks = [text for _, text in results if text]
    return "\n\n".join(chunks)


def extract_pdf_chunks(path: Path, chunk_size: int = 2000, max_chunks: int = 5, parallel: bool = False) -> list[str]:
    """Split book text into chunks for incremental encode tests with optional parallel extraction.

    parallel=False par défaut : évite le deadlock ThreadPoolExecutor de pypdf
    sur macOS quand le PDF est large (chaque thread recrée un PdfReader complet).
    """
    full_text = extract_pdf_text(path, parallel=parallel)
    if not full_text:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(full_text) and len(chunks) < max_chunks:
        end = min(start + chunk_size, len(full_text))
        piece = full_text[start:end].strip()
        if piece:
            chunks.append(piece)
        start = end
    return chunks
