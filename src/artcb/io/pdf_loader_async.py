"""Async PDF text extraction (Optimisation #4).

IMPORTANT — Thread-safety :
  PdfReader de pypdf N'EST PAS thread-safe. Partager un seul reader
  entre plusieurs threads via asyncio.gather + run_in_executor provoque
  des race conditions sur le curseur BytesIO interne → LimitReachedError
  et pages vides.
  FIX : chaque thread crée son propre PdfReader à partir des bytes bruts.
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import asyncio
import io
from pathlib import Path

import aiofiles
from pypdf import PdfReader
from pypdf.errors import PdfReadError, LimitReachedError


async def extract_pdf_text_async(
    path: Path,
    max_pages: int | None = None,
    parallel: bool = True,
) -> str:
    """Extract text from PDF asynchronously with parallel page processing.

    Args:
        path: Path to PDF file
        max_pages: Maximum number of pages to extract
        parallel: Whether to process pages in parallel (chaque thread a son propre reader)

    Returns:
        Extracted text from PDF
    """
    # Lire les bytes du PDF une seule fois de façon async
    async with aiofiles.open(path, 'rb') as f:
        pdf_bytes = await f.read()

    # Déterminer le nombre de pages avec un reader temporaire
    try:
        _tmp_reader = PdfReader(io.BytesIO(pdf_bytes))
        total_pages = len(_tmp_reader.pages)
    except (PdfReadError, LimitReachedError, Exception):
        return ""

    num_pages = min(max_pages, total_pages) if max_pages else total_pages

    if not parallel or num_pages < 4:
        # Extraction séquentielle — un seul reader, pas de problème thread-safety
        reader = PdfReader(io.BytesIO(pdf_bytes))
        chunks = []
        for i in range(num_pages):
            try:
                text = reader.pages[i].extract_text() or ""
            except (PdfReadError, LimitReachedError, Exception):
                text = ""
            if text.strip():
                chunks.append(text.strip())
        return "\n\n".join(chunks)

    # Extraction parallèle — CHAQUE THREAD crée son propre PdfReader
    # (PdfReader n'est pas thread-safe — race condition sur le BytesIO interne)
    async def extract_page(page_num: int) -> tuple[int, str]:
        """Extrait une page dans un thread isolé avec son propre PdfReader."""
        loop = asyncio.get_event_loop()
        def _extract() -> str:
            # Reader isolé par thread — thread-safe garanti
            try:
                isolated_reader = PdfReader(io.BytesIO(pdf_bytes))
                return isolated_reader.pages[page_num].extract_text() or ""
            except (PdfReadError, LimitReachedError, Exception):
                return ""
        text = await loop.run_in_executor(None, _extract)
        return (page_num, text.strip() if text.strip() else "")

    # Toutes les pages en parallèle, chacune dans un thread avec son propre reader
    tasks = [extract_page(i) for i in range(num_pages)]
    results = await asyncio.gather(*tasks)

    # Tri par numéro de page et assemblage
    results.sort(key=lambda x: x[0])
    chunks = [text for _, text in results if text]
    return "\n\n".join(chunks)


async def extract_pdf_chunks_async(
    path: Path,
    chunk_size: int = 2000,
    max_chunks: int = 5,
    parallel: bool = True,
) -> list[str]:
    """Split PDF text into chunks asynchronously.

    Args:
        path: Path to PDF file
        chunk_size: Size of each chunk in characters
        max_chunks: Maximum number of chunks to return
        parallel: Whether to use parallel extraction

    Returns:
        List of text chunks
    """
    full_text = await extract_pdf_text_async(path, parallel=parallel)
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

