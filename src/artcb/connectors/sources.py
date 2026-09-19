"""Lecture des sources d'apprentissage externes — base de données client (lecture seule)."""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import json
import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from src.artcb.connectors.manager import ConnectorRecord

logger = logging.getLogger("artcb.connectors.sources")


class DataSourceError(Exception):
    """Failed to read external data source."""


@dataclass
class LearningBatch:
    text: str
    row_count: int
    offset: int
    limit: int
    has_more: bool


def fetch_learning_text(
    record: ConnectorRecord,
    *,
    limit: int = 50,
    offset: int = 0,
) -> str:
    batch = fetch_learning_text_batched(record, limit=limit, offset=offset)
    return batch.text


def fetch_learning_text_batched(
    record: ConnectorRecord,
    *,
    limit: int = 50,
    offset: int = 0,
) -> LearningBatch:
    """Lecture paginée — banque / grosses bases (batch par batch)."""
    if not record._api_key and record.provider not in ("sqlite", "local_folder", "pdf_file"):
        raise DataSourceError("Connector has no API key / secret")

    if record.provider == "supabase":
        text, count, has_more = _fetch_supabase_batch(record, limit=limit, offset=offset)
    elif record.provider == "sqlite":
        text, count, has_more = _fetch_sqlite_batch(record, limit=limit, offset=offset)
    elif record.provider == "postgres":
        text, count, has_more = _fetch_postgres_batch(record, limit=limit, offset=offset)
    elif record.provider == "mysql":
        text, count, has_more = _fetch_mysql_batch(record, limit=limit, offset=offset)
    elif record.provider == "local_folder":
        text, count, has_more = _fetch_local_folder_batch(record, limit=limit, offset=offset)
    elif record.provider == "pdf_file":
        text, count, has_more = _fetch_pdf_file_batch(record, limit=limit, offset=offset)
    elif record.provider == "github":
        text, count, has_more = _fetch_github_batch(record, limit=limit, offset=offset)
    elif record.provider == "wikipedia":
        text, count, has_more = _fetch_wikipedia_batch(record, limit=limit, offset=offset)
    else:
        raise DataSourceError(f"Unsupported data source: {record.provider}")

    return LearningBatch(text=text, row_count=count, offset=offset, limit=limit, has_more=has_more)


def _fetch_supabase_batch(record: ConnectorRecord, *, limit: int, offset: int) -> tuple[str, int, bool]:
    base_url = record.config.get("project_url", "").rstrip("/")
    table = record.config.get("table", "")
    if not base_url or not table:
        raise DataSourceError("supabase requires config.project_url and config.table")
    api_key = record._api_key or ""
    url = f"{base_url}/rest/v1/{table}?select=*&limit={limit}&offset={offset}"
    with httpx.Client(timeout=60.0) as client:
        r = client.get(
            url,
            headers={
                "apikey": api_key,
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "Prefer": "count=exact",
            },
        )
        r.raise_for_status()
        rows = r.json()
    text = _rows_to_text(rows, source_label=f"Supabase:{table}@{offset}")
    has_more = len(rows) >= limit
    return text, len(rows), has_more


def _fetch_sqlite_batch(record: ConnectorRecord, *, limit: int, offset: int) -> tuple[str, int, bool]:
    db_path = record.config.get("database_path") or record.config.get("path", "")
    table = record.config.get("table", "")
    text_column = record.config.get("text_column", "content")
    order_by = record.config.get("order_by", "rowid")
    if not db_path or not table:
        raise DataSourceError("sqlite requires config.database_path and config.table")
    path = Path(db_path)
    if not path.is_file():
        raise DataSourceError(f"SQLite file not found: {db_path}")
    conn = sqlite3.connect(str(path))
    try:
        cur = conn.execute(
            f"SELECT * FROM {table} ORDER BY {order_by} LIMIT ? OFFSET ?",
            (limit, offset),
        )
        cols = [d[0] for d in cur.description or []]
        rows = [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]
    finally:
        conn.close()
    if text_column in cols:
        texts = [str(row.get(text_column, "")) for row in rows if row.get(text_column)]
        text = "\n\n".join(texts)
    else:
        text = _rows_to_text(rows, source_label=f"SQLite:{table}@{offset}")
    return text, len(rows), len(rows) >= limit


def _fetch_postgres_batch(record: ConnectorRecord, *, limit: int, offset: int) -> tuple[str, int, bool]:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError as exc:
        raise DataSourceError("pip install psycopg2-binary for postgres connector") from exc

    dsn = record._api_key or record.config.get("connection_string", "")
    table = record.config.get("table", "")
    text_column = record.config.get("text_column", "content")
    order_by = record.config.get("order_by", "1")
    if not dsn or not table:
        raise DataSourceError("postgres requires api_key=connection_string and config.table")
    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"SELECT * FROM {table} ORDER BY {order_by} LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
    if rows and text_column in rows[0]:
        text = "\n\n".join(str(r.get(text_column, "")) for r in rows if r.get(text_column))
    else:
        text = _rows_to_text(rows, source_label=f"Postgres:{table}@{offset}")
    return text, len(rows), len(rows) >= limit


def _fetch_mysql_batch(record: ConnectorRecord, *, limit: int, offset: int) -> tuple[str, int, bool]:
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:
        raise DataSourceError("pip install pymysql for mysql connector") from exc

    dsn = record._api_key or ""
    table = record.config.get("table", "")
    text_column = record.config.get("text_column", "content")
    order_by = record.config.get("order_by", "1")
    if not dsn or not table:
        raise DataSourceError("mysql requires api_key=connection_string and config.table")
    parsed = urlparse(dsn)
    conn = pymysql.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=parsed.username,
        password=parsed.password,
        database=(parsed.path or "/").lstrip("/"),
        cursorclass=DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM `{table}` ORDER BY {order_by} LIMIT %s OFFSET %s", (limit, offset))
            rows = list(cur.fetchall())
    finally:
        conn.close()
    if rows and text_column in rows[0]:
        text = "\n\n".join(str(r.get(text_column, "")) for r in rows if r.get(text_column))
    else:
        text = _rows_to_text(rows, source_label=f"MySQL:{table}@{offset}")
    return text, len(rows), len(rows) >= limit


def _fetch_local_folder_batch(record: ConnectorRecord, *, limit: int, offset: int) -> tuple[str, int, bool]:
    from src.artcb.io.media_ingest import MediaIngestError, ingest_folder

    folder_path = record.config.get("folder_path") or record.config.get("path", "")
    if not folder_path:
        raise DataSourceError("local_folder requires config.folder_path")
    folder = Path(folder_path)
    openai_key = record.config.get("openai_api_key_for_vision")
    try:
        text, count, has_more = ingest_folder(folder, limit=limit, offset=offset, openai_api_key=openai_key)
    except MediaIngestError as exc:
        raise DataSourceError(str(exc)) from exc
    return text, count, has_more


def _fetch_pdf_file_batch(record: ConnectorRecord, *, limit: int, offset: int) -> tuple[str, int, bool]:
    from src.artcb.io.media_ingest import MediaIngestError, ingest_file

    file_path = record.config.get("file_path") or record.config.get("path", "")
    if not file_path:
        raise DataSourceError("pdf_file requires config.file_path")
    path = Path(file_path)
    if offset > 0:
        return "", 0, False
    try:
        ingested = ingest_file(path)
    except MediaIngestError as exc:
        raise DataSourceError(str(exc)) from exc
    return ingested.text, 1, False


def _fetch_github_batch(
    record: ConnectorRecord,
    *,
    limit: int,
    offset: int,
) -> tuple[str, int, bool]:
    """
    Lit récursivement un dépôt GitHub via l'API REST v3.
    config attendu :
      repo     : "owner/repo"            (ex: "vgac2025/lvx")
      branch   : "main"                  (optionnel, défaut "main")
      path     : ""                      (sous-dossier, optionnel)
      extensions: "py,ts,md,txt,js,tsx"  (optionnel, filtre d'extensions)
    api_key   : token GitHub (ghp_…) ou token fine-grained — peut être vide pour dépôt public
    """
    repo = record.config.get("repo", "").strip()
    if not repo or "/" not in repo:
        raise DataSourceError("github connector requires config.repo = 'owner/repo'")

    branch    = record.config.get("branch", "main").strip() or "main"
    root_path = record.config.get("path", "").strip().strip("/")
    raw_exts  = record.config.get("extensions", "py,ts,tsx,md,txt,js,json,yaml,yml,toml,rst,css,html")
    allowed   = {e.strip().lstrip(".").lower() for e in raw_exts.split(",") if e.strip()}

    headers: dict[str, str] = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = record._api_key or ""
    # N'ajoute le token que si c'est un vrai token GitHub — pas le placeholder "github-public"
    if token and not token.startswith("local-") and not token.startswith("github-"):
        headers["Authorization"] = f"Bearer {token}"

    api_base = record.config.get("api_base", "https://api.github.com").rstrip("/")

    def _list_tree(path: str = "") -> list[dict]:
        """Récupère récursivement tous les fichiers texte du repo."""
        url = f"{api_base}/repos/{repo}/git/trees/{branch}?recursive=1"
        with httpx.Client(timeout=60.0) as client:
            r = client.get(url, headers=headers)
            if r.status_code == 401:
                raise DataSourceError("GitHub token invalide ou dépôt privé sans token")
            if r.status_code == 403:
                raise DataSourceError("GitHub rate limit atteint — ajoutez un token personnel")
            if r.status_code == 404:
                raise DataSourceError(f"Dépôt GitHub introuvable: {repo} (branche: {branch})")
            r.raise_for_status()
            data = r.json()
        if data.get("truncated"):
            logger.warning("GitHub tree truncated for %s — repo très large, résultats partiels", repo)
        files = [
            item for item in data.get("tree", [])
            if item.get("type") == "blob"
            and (not path or item["path"].startswith(path))
            and (not allowed or item["path"].rsplit(".", 1)[-1].lower() in allowed)
        ]
        return files

    def _get_file_content(file_path: str) -> str:
        url = f"{api_base}/repos/{repo}/contents/{file_path}?ref={branch}"
        with httpx.Client(timeout=30.0) as client:
            r = client.get(url, headers=headers)
            r.raise_for_status()
            data = r.json()
        if data.get("encoding") == "base64":
            import base64
            raw_bytes = base64.b64decode(data["content"].replace("\n", ""))
            try:
                return raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return raw_bytes.decode("latin-1", errors="replace")
        return data.get("content", "")

    all_files = _list_tree(root_path)
    total     = len(all_files)
    page      = all_files[offset : offset + limit]
    has_more  = (offset + limit) < total

    if not page:
        return f"[GitHub:{repo}] Aucun fichier trouvé (offset={offset}, exts={raw_exts})", 0, False

    parts: list[str] = []
    for item in page:
        try:
            content = _get_file_content(item["path"])
            size_kb = round(item.get("size", 0) / 1024, 1)
            parts.append(
                f"=== {item['path']} ({size_kb} KB) ===\n{content}"
            )
        except Exception as exc:
            logger.warning("GitHub: skip %s — %s", item["path"], exc)

    text = f"\n\n".join(parts)
    logger.info("GitHub fetch: repo=%s branch=%s files=%d/%d offset=%d has_more=%s",
                repo, branch, len(page), total, offset, has_more)
    return text, len(page), has_more


def _rows_to_text(rows: list[Any], *, source_label: str) -> str:
    if not rows:
        return f"[{source_label}] Aucune ligne récupérée."
    parts = [f"--- {source_label} row {i} ---\n{json.dumps(row, ensure_ascii=False, default=str)}" for i, row in enumerate(rows)]
    return "\n\n".join(parts)


def test_connector(record: ConnectorRecord) -> tuple[bool, str]:
    """Teste la connexion sans stocker de données ARTCB."""
    try:
        if record.provider in {"openai", "anthropic", "bob", "openrouter", "ollama", "cursor", "watsonx", "manus", "google_ai"}:
            from src.artcb.connectors.llm_router import LLMRouter

            result = LLMRouter().classify_sentences(
                ["Test de connexion ARTCB."],
                record=record,
                api_key=record._api_key or "",
            )
            if result is None:
                return False, "LLM n'a pas répondu — vérifiez la clé et le modèle"
            return True, f"LLM {record.provider} connecté"
        if record.provider == "github":
            # Test léger : juste l'API repos (pas de téléchargement)
            repo  = record.config.get("repo", "")
            branch = record.config.get("branch", "main")
            token = record._api_key or ""
            hdrs: dict[str, str] = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
            # N'ajoute le token que si c'est un vrai token GitHub (ghp_*, github_pat_*, etc.)
            if token and not token.startswith("local-") and not token.startswith("github-"):
                hdrs["Authorization"] = f"Bearer {token}"
            with httpx.Client(timeout=15.0) as client:
                r = client.get(f"https://api.github.com/repos/{repo}", headers=hdrs)
            if r.status_code == 401:
                return False, "Token GitHub invalide"
            if r.status_code == 403:
                return False, "GitHub rate limit — ajoutez un token"
            if r.status_code == 404:
                return False, f"Dépôt introuvable: {repo}"
            r.raise_for_status()
            info = r.json()
            return True, (
                f"GitHub OK — {info.get('full_name')} "
                f"({info.get('stargazers_count', 0)}★, branche: {branch}, "
                f"privé: {info.get('private', False)})"
            )
        text = fetch_learning_text(record, limit=3)
        preview = text[:120].replace("\n", " ")
        return True, f"Source OK — aperçu: {preview}…"
    except Exception as exc:
        return False, str(exc)


def _fetch_wikipedia_batch(record: ConnectorRecord, *, limit: int, offset: int) -> tuple[str, int, bool]:
    """
    Connecteur Wikipedia — API REST publique, sans clé.
    config.query  : terme(s) à rechercher (ex: "blockchain proof of learning")
    config.lang   : code langue (fr, en, zh… — défaut: fr)
    config.titles : liste de titres séparés par | pour lire directement des articles
    """
    lang = record.config.get("lang", "fr")
    base = f"https://{lang}.wikipedia.org/w/api.php"
    texts: list[str] = []

    titles_raw = record.config.get("titles", "")
    query = record.config.get("query", "")

    if titles_raw:
        # Mode lecture directe d'articles par titre
        titles = [t.strip() for t in titles_raw.split("|") if t.strip()]
        page_titles = titles[offset : offset + limit]
        has_more = (offset + limit) < len(titles)
    elif query:
        # Mode recherche
        with httpx.Client(timeout=30.0) as client:
            r = client.get(base, params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": limit,
                "sroffset": offset,
                "format": "json",
            })
            r.raise_for_status()
            data = r.json()
        results = data.get("query", {}).get("search", [])
        page_titles = [res["title"] for res in results]
        total = data.get("query", {}).get("searchinfo", {}).get("totalhits", 0)
        has_more = (offset + limit) < int(total)
    else:
        raise DataSourceError("wikipedia connector requires config.query or config.titles")

    # Lire le contenu de chaque article
    if page_titles:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(base, params={
                "action": "query",
                "titles": "|".join(page_titles),
                "prop": "extracts",
                "exintro": True,
                "explaintext": True,
                "exlimit": len(page_titles),
                "format": "json",
            })
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            title = page.get("title", "")
            extract = page.get("extract", "").strip()
            if extract:
                texts.append(f"=== {title} ===\n{extract[:2000]}")

    text = "\n\n".join(texts)
    return text, len(texts), has_more


