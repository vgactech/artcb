"""Connecteur Kaggle pour ARTCB — source de datasets pour l'apprentissage PoL.

Permet d'ingérer des datasets Kaggle directement dans le pipeline de minage ARTCB.

Configuration (.env) :
    KAGGLE_USERNAME=ndarray2000
    KAGGLE_KEY=VOTRE_CLE_API

Usage :
    connector = KaggleConnector()
    datasets = connector.search_datasets("blockchain")
    text = connector.dataset_to_text("bigquery/ethereum-blockchain", max_rows=100)
    # → texte prêt pour POST /api/v1/mining/pipeline
"""

from __future__ import annotations
MODULE_VERSION = '1.0.0'  # R390 — auto-versioning

import csv
import io
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("artcb.connectors.kaggle")

_KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME", "")
_KAGGLE_KEY = os.getenv("KAGGLE_KEY", "")

# Assurer que kaggle.json existe si les vars d'env sont définies
def _ensure_kaggle_config() -> None:
    config_path = Path.home() / ".config" / "kaggle" / "kaggle.json"
    if not config_path.exists() and _KAGGLE_USERNAME and _KAGGLE_KEY:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            json.dumps({"username": _KAGGLE_USERNAME, "key": _KAGGLE_KEY})
        )
        config_path.chmod(0o600)
        logger.info("kaggle.json créé depuis variables d'environnement")


class KaggleConnectorError(Exception):
    """Erreur connecteur Kaggle."""


class KaggleConnector:
    """Connecteur Kaggle → source de données pour pipeline minage ARTCB."""

    def __init__(self) -> None:
        _ensure_kaggle_config()
        try:
            from kaggle import api as _kapi
            _kapi.authenticate()
            self._api = _kapi
            self._available = True
            logger.info("Kaggle API authentifiée (user=%s)", _KAGGLE_USERNAME or "via kaggle.json")
        except Exception as exc:
            self._api = None
            self._available = False
            logger.warning("Kaggle non disponible : %s", exc)

    @property
    def available(self) -> bool:
        return self._available

    def search_datasets(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """Recherche des datasets Kaggle par mots-clés."""
        if not self._available:
            raise KaggleConnectorError("Kaggle API non disponible — vérifier KAGGLE_USERNAME et KAGGLE_KEY")
        datasets = self._api.dataset_list(search=query, page=1)
        results = []
        for d in (datasets or [])[:max_results]:
            results.append({
                "ref": getattr(d, "ref", ""),
                "title": getattr(d, "title", ""),
                "subtitle": getattr(d, "subtitle", ""),
                "total_bytes": getattr(d, "totalBytes", 0),
                "url": f"https://www.kaggle.com/datasets/{getattr(d, 'ref', '')}",
            })
        return results

    def dataset_to_text(self, dataset_ref: str, max_rows: int = 200) -> str:
        """Télécharge un dataset Kaggle et le convertit en texte pour le pipeline PoL.

        Args:
            dataset_ref: ex "bigquery/ethereum-blockchain" ou "jesusgraterol/bitcoin-blockchain-dataset"
            max_rows: nombre max de lignes CSV à encoder

        Returns:
            Texte structuré lisible par l'IR PoL Encoder
        """
        if not self._available:
            raise KaggleConnectorError("Kaggle API non disponible")

        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                self._api.dataset_download_files(
                    dataset_ref,
                    path=tmpdir,
                    unzip=True,
                    quiet=True,
                )
            except Exception as exc:
                raise KaggleConnectorError(f"Téléchargement échoué ({dataset_ref}) : {exc}") from exc

            # Trouver le premier fichier CSV/JSON téléchargé
            tmp_path = Path(tmpdir)
            csv_files = list(tmp_path.rglob("*.csv"))
            json_files = list(tmp_path.rglob("*.json"))

            if csv_files:
                return self._csv_to_text(csv_files[0], dataset_ref, max_rows)
            elif json_files:
                return self._json_to_text(json_files[0], dataset_ref, max_rows)
            else:
                # Lister ce qui a été téléchargé
                all_files = list(tmp_path.rglob("*"))
                return (
                    f"Dataset Kaggle importé : {dataset_ref}\n"
                    f"Fichiers disponibles : {[f.name for f in all_files[:10]]}\n"
                    f"Format non CSV/JSON — traitement manuel requis."
                )

    @staticmethod
    def _csv_to_text(csv_path: Path, dataset_ref: str, max_rows: int) -> str:
        """Convertit un CSV en texte structuré pour l'IR PoL."""
        lines = [f"Dataset Kaggle : {dataset_ref}", f"Fichier : {csv_path.name}", ""]
        try:
            with csv_path.open(encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames:
                    lines.append(f"Colonnes : {', '.join(reader.fieldnames)}")
                    lines.append("")
                for i, row in enumerate(reader):
                    if i >= max_rows:
                        lines.append(f"... ({i} lignes au total, limité à {max_rows})")
                        break
                    row_text = " | ".join(f"{k}: {v}" for k, v in row.items() if v)
                    lines.append(f"Ligne {i+1}: {row_text}")
        except Exception as exc:
            lines.append(f"Erreur lecture CSV : {exc}")
        return "\n".join(lines)

    @staticmethod
    def _json_to_text(json_path: Path, dataset_ref: str, max_rows: int) -> str:
        """Convertit un JSON en texte structuré pour l'IR PoL."""
        lines = [f"Dataset Kaggle : {dataset_ref}", f"Fichier : {json_path.name}", ""]
        try:
            data = json.loads(json_path.read_text(encoding="utf-8", errors="replace"))
            if isinstance(data, list):
                lines.append(f"Entrées : {len(data)}")
                for i, item in enumerate(data[:max_rows]):
                    lines.append(f"Entrée {i+1}: {json.dumps(item, ensure_ascii=False)[:200]}")
            else:
                lines.append(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
        except Exception as exc:
            lines.append(f"Erreur lecture JSON : {exc}")
        return "\n".join(lines)

    def dataset_metadata(self, dataset_ref: str) -> dict[str, Any]:
        """Retourne les métadonnées d'un dataset sans le télécharger."""
        if not self._available:
            raise KaggleConnectorError("Kaggle API non disponible")
        results = self.search_datasets(dataset_ref.split("/")[-1], max_results=20)
        for r in results:
            if r["ref"] == dataset_ref:
                return r
        return {"ref": dataset_ref, "found": False}
