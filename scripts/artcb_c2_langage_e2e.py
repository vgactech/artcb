#!/usr/bin/env python3
"""R319 — C2 langage IA battery (honest, CERTIFIED_100=false).

R320 (2026-09-11T21:55:00Z) — ajout, rien de supprimé : C2-D ne se contente plus
d'une copie de répertoire (``shutil.copytree``, conservée comme sous-mesure
``arcb_sync_sim_ok``). Un vrai nœud ARTCB est démarré sur une socket TCP locale ;
A publie un bundle binaire ACBN via ``POST /api/v1/concepts/publish`` et B, dont
le ConceptStore est vide, le récupère via ``GET /api/v1/concepts/resolve``.
Le hash du paquet est ancré par mémo puis **relu** pour vérification.

Namespaces (do not mix):
  C2          = lexicon object code for vehicle lemmas
  K3e7dc01…   = concrete ConceptID from type+sym O1C2
  C2-A…C2-D   = this test ladder

Levels:
  C2-A  lexical + adversarial (false equiv / substring / synonym gap)
  C2-B  phrases → overlapping ConceptIDs (not translation-chain)
  C2-C  relation + reasoning on ConceptIDs without human text in packet
  C2-D  A → (optional live memo) → B retrieve/combine — network path measured

Usage:
  PYTHONPATH=src:scripts python3 scripts/artcb_c2_langage_e2e.py
  PYTHONPATH=src:scripts python3 scripts/artcb_c2_langage_e2e.py --live-memo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

try:
    from artcb_dns_fix import install as _dns_install
except Exception:  # noqa: BLE001

    def _dns_install() -> None:
        return None

from src.artcb.ir.concept import concept_id_from_node, decode_concept_packet, encode_concept_packet
from src.artcb.ir.concept_lexicon import object_codes
from src.artcb.ir.encoder import IREncoder
from src.artcb.memory.agent_channel import AgentChannel
from src.artcb.memory.concept_network import HttpConceptResolver, publish_bundle
from src.artcb.memory.concept_store import ConceptStore
from src.artcb.memory.concept_sync import bundle_sha256

UI_LOCALES = ("fr", "en", "zh", "es", "pt", "it", "ru")
# R321: philological L1 set (UI locales + Latin). Not a translation chain.
VEHICLE = {
    "fr": "voiture",
    "en": "car",
    "es": "coche",
    "pt": "carro",
    "it": "auto",
    "ru": "автомобиль",
    "la": "vehiculum",
    "zh": "汽车",
}
PHRASES = {
    "fr": "La voiture consomme beaucoup d'énergie.",
    "en": "The car consumes a lot of energy.",
    "es": "El coche consume mucha energía.",
    "pt": "O carro consome muita energia.",
    "it": "L'auto consuma molta energia.",
    "ru": "Автомобиль потребляет много энергии.",
    "la": "Vehiculum multam energiam consumit.",
    "zh": "汽车消耗大量能源。",
}
RELATION = {
    "fr": "Si la charge augmente, la consommation augmente.",
    "en": "If the load increases, consumption increases.",
    "es": "Si la carga aumenta, el consumo aumenta.",
}
LEXICON_CODE_VEHICLE = "C2"
EXPECTED_VEHICLE_KID = "K3e7dc01c5cf83cd8"
# L4 bag: consume(U1) + vehicle(C2) + energy(E3) → same ConceptID ×8
EXPECTED_L4_KID = "Ke410ef3b8d2bddd5"


def _ids(text: str) -> list[str]:
    g = IREncoder().encode(text)
    return [concept_id_from_node(n) for n in g.nodes]


def _key() -> str:
    k = (os.environ.get("ARTCB_API_KEY") or "").strip()
    if len(k) >= 16:
        return k
    env = Path.home() / ".artcb" / "cursor_agent.env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("ARTCB_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _post_memo(base: str, content: str, *, private: bool = False) -> dict:
    url = f"{base.rstrip('/')}/api/v1/ai/memo"
    body = json.dumps(
        {
            "content": content,
            "visibility": "private" if private else "public",
            "source": "c2_langage_e2e_r319",
        }
    ).encode()
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    k = _key()
    if len(k) >= 16:
        headers["Authorization"] = f"Bearer {k}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _get_memo(base: str, index: int) -> dict:
    """R320 — relire un mémo gravé, pour vérifier l'ancre au lieu de la supposer."""
    url = f"{base.rstrip('/')}/api/v1/ai/memo/{index}"
    headers = {"Accept": "application/json"}
    k = _key()
    if len(k) >= 16:
        headers["Authorization"] = f"Bearer {k}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


class LocalNode:
    """R320 — nœud ARTCB réel sur une socket TCP locale (pas un stub en mémoire).

    On veut une **vraie** requête HTTP : socket, en-têtes, corps binaire. Le fait
    que la machine soit la même que celle du test est dit explicitement dans le
    rapport (``network_proof_scope``) : ce n'est pas revendiqué comme une preuve
    multi-hôte.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.base = ""
        self._server = None
        self._thread = None

    def start(self) -> str:
        import socket
        import threading

        import uvicorn

        os.environ["ARTCB_DATA_DIR"] = str(self.data_dir)
        os.environ["ARTCB_LOG_DIR"] = str(self.data_dir / "logs")
        os.environ.setdefault("ARTCB_WALLET_PASSPHRASE", "c2d-r320-local-node-passphrase!")
        os.environ.setdefault(
            "ARTCB_NODE_WALLET_ADDRESS", "artcb1testnode000000000000000000000000000"
        )
        os.environ["ARTCB_BOOTSTRAP_NODE"] = "false"
        os.environ["ARTCB_SKIP_SEED_DISCOVERY"] = "1"
        os.environ["ARTCB_SKIP_CLOUD_METADATA"] = "1"
        os.environ["ARTCB_ALLOW_LOCAL_PEERS"] = "1"
        os.environ["ARTCB_ALLOW_MULTI_WALLET"] = "true"
        os.environ["ARTCB_MIN_BLOCK_INTERVAL_SEC"] = "0"

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

        from src.api.main import create_app

        config = uvicorn.Config(create_app(), log_level="warning")
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(
            target=self._server.run, kwargs={"sockets": [sock]}, daemon=True
        )
        self._thread.start()
        self.base = f"http://127.0.0.1:{port}"
        for _ in range(200):
            try:
                with urllib.request.urlopen(f"{self.base}/live", timeout=2):
                    break
            except Exception:  # noqa: BLE001
                time.sleep(0.05)
        return self.base

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=10)

    def session_token(self, name: str) -> str:
        """Wallet + login sur le nœud local → Bearer de session pour publier."""
        pwd = "pwd_r320_c2d_publisher"
        for path, body in (
            ("/api/v1/wallet/create", {"name": name, "password": pwd}),
            ("/api/v1/auth/login", {"name": name, "password": pwd}),
        ):
            req = urllib.request.Request(
                f"{self.base}{path}",
                data=json.dumps(body).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                payload = json.loads(resp.read().decode())
        return str(payload["session_token"])


def run_c2_a() -> dict:
    t0 = time.perf_counter_ns()
    vehicle_ids = {lang: _ids(word)[0] if _ids(word) else "" for lang, word in VEHICLE.items()}
    codes = {lang: object_codes(word) for lang, word in VEHICLE.items()}
    same_k = len(set(vehicle_ids.values())) == 1 and bool(next(iter(vehicle_ids.values())))
    same_code = all(LEXICON_CODE_VEHICLE in (codes[l] or []) for l in VEHICLE)
    avion = _ids("avion")
    false_equiv = EXPECTED_VEHICLE_KID not in avion and vehicle_ids.get("fr") not in avion
    verificar = _ids("verificar")
    substring_ok = EXPECTED_VEHICLE_KID not in verificar
    # R321: automobile synonym closed (was GAP in R319).
    automobile = _ids("automobile")
    synonym_converges = EXPECTED_VEHICLE_KID in automobile
    status = (
        "PASS"
        if (same_k and same_code and false_equiv and substring_ok and synonym_converges)
        else "FAIL"
    )
    return {
        "level": "C2-A",
        "status": status,
        "lexicon_object_code": LEXICON_CODE_VEHICLE,
        "concept_id": vehicle_ids.get("fr"),
        "expected_concept_id": EXPECTED_VEHICLE_KID,
        "namespace_note": "C2=lexicon code; K…=ConceptID; C2-A=test level",
        "vehicle_ids": vehicle_ids,
        "object_codes": codes,
        "adversarial": {
            "avion_ne_vehicle": false_equiv,
            "verificar_no_car_substring": substring_ok,
            "automobile_synonym_converges": synonym_converges,
            "automobile_note": "R321: synonym layer closed; still not full ontology",
            "auto_not_in_autonomie": "C2" not in object_codes("autonomie"),
        },
        "ui_locales_in_frontend": list(UI_LOCALES),
        "ui_locales_semantically_probed": list(VEHICLE.keys()),
        "philology_langs": list(VEHICLE.keys()),
        "dur_ns": time.perf_counter_ns() - t0,
    }


def run_c2_b() -> dict:
    t0 = time.perf_counter_ns()
    per = {lang: _ids(text) for lang, text in PHRASES.items()}
    # L4 bag ConceptID (U1C2E3) — not the bare vehicle O1C2 id
    l4_in = {lang: EXPECTED_L4_KID in ids for lang, ids in per.items()}
    overlap = set.intersection(*(set(v) for v in per.values())) if per else set()
    status = "PASS" if all(l4_in.values()) and EXPECTED_L4_KID in overlap else "PARTIAL"
    if not all(l4_in.values()):
        status = "FAIL"
    return {
        "level": "C2-B",
        "status": status,
        "phrases": PHRASES,
        "ids": per,
        "l4_in_each": l4_in,
        "expected_l4_concept_id": EXPECTED_L4_KID,
        "intersection": sorted(overlap),
        "note": "8-lang L4 bag via lexicon hits — not a translation-chain proof",
        "dur_ns": time.perf_counter_ns() - t0,
    }


def run_c2_c(tmp: Path) -> dict:
    t0 = time.perf_counter_ns()
    store = ConceptStore(tmp / "c2c")
    ch = AgentChannel(agent_id="reasoner", store=store)
    learned = []
    for lang, text in RELATION.items():
        r = ch.learn_from_text(text)
        learned.append({"lang": lang, "concept_ids": r.concept_ids, "graph_id": r.graph_id})
    # Reasoning without human text: packet of concept_ids only
    all_ids = []
    for row in learned:
        all_ids.extend(row["concept_ids"])
    packet = encode_concept_packet(all_ids)
    decoded = decode_concept_packet(packet)
    assert b"charge" not in packet and b"consommation" not in packet
    known = [cid for cid in decoded if ch.knows(cid)]
    graphs = store.recall_by_concept_ids(decoded)
    # Combine: derive a new local knowledge from union of known ids
    derived = ch.learn_from_text(
        "Optimisation: reduire consommation sous contrainte de capacite."
    )
    status = "PASS" if known and graphs and derived.concept_ids else "FAIL"
    return {
        "level": "C2-C",
        "status": status,
        "learned": learned,
        "packet_sha256": hashlib.sha256(packet).hexdigest(),
        "packet_bytes": len(packet),
        "known_from_packet": len(known),
        "graphs_recalled": len(graphs),
        "derived_concept_ids": derived.concept_ids,
        "derived_graph_id": derived.graph_id,
        "note": "Local AgentChannel — proves IR+store+packet, not yet multi-node network",
        "dur_ns": time.perf_counter_ns() - t0,
    }


def run_c2_d(tmp: Path, *, live_memo: bool, base: str) -> dict:
    """A learns → packet → B (shared prior OR seeded store) + optional live memo anchor."""
    t0 = time.perf_counter_ns()
    store_a = ConceptStore(tmp / "agent_a")
    store_b = ConceptStore(tmp / "agent_b")
    a = AgentChannel(agent_id="agent_a", store=store_a)
    b = AgentChannel(agent_id="agent_b", store=store_b)

    problem = (
        "Une machine consomme beaucoup d'energie sous charge IA. "
        "Strategie: optimiser capacite pour reduire consommation sans tuer le debit."
    )
    learn_a = a.learn_from_text(problem)
    packet = learn_a.packet
    packet_sha = hashlib.sha256(packet).hexdigest()

    # Without transferring .arcb, B cannot recall — measure this honestly first
    recall_cold = b.receive_packet(packet)
    cold_ok = len(recall_cold.found_graphs) > 0 and not recall_cold.missing_concept_ids

    # Seed B with same semantic prior (independent learn — network would sync .arcb)
    b.learn_from_text(problem)
    recall_warm = b.receive_packet(packet)
    warm_ok = (
        recall_warm.requested_concept_ids == learn_a.concept_ids
        and not recall_warm.missing_concept_ids
    )

    # B own knowledge + combine
    b_own = b.learn_from_text("Debit cible maintenu sous contrainte energetique.")
    combined = b.learn_from_text(
        "Combinaison: charge + capacite + optimisation => nouvelle strategie K9."
    )

    # Optional: anchor packet hash + concept_ids on live ARTCB (not full .arcb sync)
    memo = None
    memo_err = None
    if live_memo:
        payload = json.dumps(
            {
                "c2_level": "C2-D",
                "agent": "agent_a",
                "concept_ids": learn_a.concept_ids,
                "graph_id": learn_a.graph_id,
                "packet_sha256": packet_sha,
                "problem_sha256": hashlib.sha256(problem.encode()).hexdigest(),
            },
            sort_keys=True,
        )
        try:
            memo = _post_memo(base, payload, private=False)
        except Exception as exc:  # noqa: BLE001
            memo_err = str(exc)[:200]

    # ── R320 : chemin RÉSEAU réel (socket TCP) ───────────────────────────────
    # C'est le maillon qui manquait à R319. B part d'un ConceptStore vide et ne
    # reçoit AUCUN texte humain : il n'a que le paquet ACPT + le réseau.
    net: dict = {"attempted": True}
    node = LocalNode(tmp / "node")
    store_cold = ConceptStore(tmp / "agent_b_cold_net")
    b_net = AgentChannel(agent_id="agent_b_cold_net", store=store_cold)
    net_cold_before = b_net.receive_packet(packet)
    net["b_missing_before_network"] = list(net_cold_before.missing_concept_ids)
    try:
        t_net = time.perf_counter_ns()
        net["base"] = node.start()
        token = node.session_token("c2d_publisher")
        bundle = a.export_bundle(learn_a.concept_ids)
        net["bundle_bytes"] = len(bundle)
        net["bundle_sha256"] = bundle_sha256(bundle)
        net["bundle_has_no_human_text"] = (
            b"consomme" not in bundle and b"machine" not in bundle
        )
        net["publish"] = publish_bundle(node.base, bundle, api_key=token)
        resolver = HttpConceptResolver(node.base)
        recall_net = b_net.receive_packet(packet, resolver=resolver)
        net["resolve_http_status"] = resolver.last_status
        net["resolve_bundle_sha256"] = resolver.last_bundle_sha256
        net["resolve_missing_reported"] = resolver.last_missing
        net["graphs_ingested_from_network"] = b_net.last_resolved_from_network
        net["b_missing_after_network"] = list(recall_net.missing_concept_ids)
        net["b_found_graphs"] = len(recall_net.found_graphs)
        # Deuxième réception SANS résolveur : B a-t-il vraiment appris ?
        persisted = b_net.receive_packet(packet)
        net["b_persists_without_network"] = not persisted.missing_concept_ids
        net["ok"] = (
            not recall_net.missing_concept_ids
            and len(recall_net.found_graphs) > 0
            and net["b_persists_without_network"]
        )
        net["dur_ns"] = time.perf_counter_ns() - t_net
    except Exception as exc:  # noqa: BLE001
        net["ok"] = False
        net["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
    finally:
        node.stop()

    # ── R320 : le nœud LIVE distant connaît-il déjà ces routes ? ─────────────
    live_net: dict = {"base": base}
    try:
        probe = HttpConceptResolver(base, api_key=_key(), timeout=20)
        probe(learn_a.concept_ids)
        live_net["resolve_http_status"] = probe.last_status
        live_net["deployed"] = probe.last_status == 200
        live_net["note"] = (
            "routes /concepts présentes sur le nœud live"
            if probe.last_status == 200
            else "nœud live pas encore sur ce SHA — honnête, pas de PASS revendiqué"
        )
    except Exception as exc:  # noqa: BLE001
        live_net["deployed"] = False
        live_net["error"] = f"{type(exc).__name__}: {str(exc)[:200]}"

    # Copy A's arcb into B as simulated network concept sync (measured separately)
    sync_dir = tmp / "agent_b_synced"
    if (tmp / "agent_a").exists():
        shutil.copytree(tmp / "agent_a", sync_dir, dirs_exist_ok=True)
    store_sync = ConceptStore(sync_dir)
    ch_sync = AgentChannel(agent_id="agent_b_synced", store=store_sync)
    recall_synced = ch_sync.receive_packet(packet)
    synced_ok = len(recall_synced.found_graphs) > 0

    # R320 — relecture du mémo : une ancre non relue n'est pas une preuve.
    memo_readback = None
    if memo:
        idx = memo.get("block_index", memo.get("index"))
        if isinstance(idx, int):
            try:
                read = _get_memo(base, idx)
                blob = json.dumps(read, ensure_ascii=False)
                memo_readback = {
                    "block_index": idx,
                    "http": 200,
                    "packet_sha256_found": packet_sha in blob,
                    "concept_ids_found": all(cid in blob for cid in learn_a.concept_ids),
                }
            except Exception as exc:  # noqa: BLE001
                memo_readback = {"block_index": idx, "error": str(exc)[:200]}

    # R320 — le verdict suit la mesure réseau, plus la copie disque.
    if net.get("ok") or cold_ok:
        net_status = "PASS"
    elif warm_ok:
        net_status = "PARTIAL"
    else:
        net_status = "FAIL"

    return {
        "level": "C2-D",
        "status": net_status,
        "a_concept_ids": learn_a.concept_ids,
        "a_graph_id": learn_a.graph_id,
        "a_output_hash": packet_sha,
        "b_cold_found": len(recall_cold.found_graphs),
        "b_cold_missing": recall_cold.missing_concept_ids,
        "b_warm_ok": warm_ok,
        "b_own_concept_ids": b_own.concept_ids,
        "b_combined_k9_ids": combined.concept_ids,
        "b_combined_graph_id": combined.graph_id,
        "arcb_sync_sim_ok": synced_ok,
        "live_memo": memo,
        "live_memo_error": memo_err,
        "live_memo_readback": memo_readback,
        # R320
        "network_sync": net,
        "live_node_concepts_api": live_net,
        "network_proof_scope": (
            "HTTP réel (socket TCP 127.0.0.1) entre deux ConceptStore séparés ; "
            "multi-hôte à re-mesurer après déploiement des routes /concepts"
        ),
        "honest_gaps": [
            "cold B without prior/store sync cannot reconstruct graphs from packet alone",
            "live memo anchors hashes/ids — does not yet ship .arcb concept blobs over P2P",
            "C2-D PASS only if cold path OR full concept-store sync over network is proven",
            "R320: chemin réseau prouvé sur une socket locale ; nœuds live à re-prober après deploy",
        ],
        "dur_ns": time.perf_counter_ns() - t0,
    }


def main() -> int:
    _dns_install()
    ap = argparse.ArgumentParser()
    ap.add_argument("--live-memo", action="store_true")
    ap.add_argument("--base", default=os.environ.get("ARTCB_API_URL", "https://artcb.me"))
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="artcb_c2_"))
    try:
        report = {
            "ts_ns": time.time_ns(),
            "git_hint": "R320",
            "certified_100": False,
            "ui_locales": list(UI_LOCALES),
            "C2-A": run_c2_a(),
            "C2-B": run_c2_b(),
            "C2-C": run_c2_c(tmp),
            "C2-D": run_c2_d(tmp, live_memo=args.live_memo, base=args.base),
        }
        levels = [report[k]["status"] for k in ("C2-A", "C2-B", "C2-C", "C2-D")]
        report["ladder_summary"] = {
            "statuses": levels,
            "serious_e2e_claim": report["C2-D"]["status"] == "PASS",
            "note": "Only C2-D PASS is a serious E2E langage claim; lexical alone is insufficient",
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    text = json.dumps(report, indent=2, ensure_ascii=False)
    print(text)
    out = Path(args.out) if args.out else ROOT / "logs" / f"320_c2_langage_{time.strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {out}", file=sys.stderr)
    # Exit 0 even on PARTIAL — honest measurement, not CI gate yet
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
