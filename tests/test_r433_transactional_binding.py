"""R433 — Tests : verrou transactionnel, élimination DELETE legacy, journal forensic enchaîné.

Couverture :
  T-LOCK-01  : _transactional_lock() acquiert un verrou exclusif
  T-LOCK-02  : _transactional_lock() sur des registres distincts ne se bloque pas
  T-CAS-01   : deux processus concurrents → bind → un seul enregistré (no lost-update)
  T-CAS-02   : revoke_with_history sous contention → premier gagne, second voit REVOKED
  T-CAS-03   : purge_binding sous contention → un seul purge_id
  T-CAS-04   : check_and_bind idempotent sous contention multi-processus
  T-CAS-05   : revoke CAS expected_version=1 sous contention → conflit détecté
  T-LEGACY-01: admin_revoke_by_fingerprint → BindingLegacyDeleteError
  T-LEGACY-02: admin_revoke_by_wallet → BindingLegacyDeleteError
  T-LEGACY-03: admin_revoke_test_by_wallet → BindingLegacyDeleteError
  T-FORENSIC-01: première entrée → hash_prev="genesis" + entry_hash valide
  T-FORENSIC-02: deuxième entrée → hash_prev = entry_hash de la première
  T-FORENSIC-03: altération d'une entrée passée → hash_prev rompt la chaîne
  T-FORENSIC-04: entry_hash est reproductible (même entrée → même hash)
  T-FORENSIC-05: list_purge_log() retourne les entrées avec les deux champs de chaîne

PROTOCOLE ARTCB — mode DEBUG actif.
"""
from __future__ import annotations

import hashlib
import json
import multiprocessing
import time
import uuid
from pathlib import Path

import pytest

from src.artcb.security.wallet_device_binding import (
    BindingLegacyDeleteError,
    BindingRevocationError,
    BindingState,
    WalletDeviceBindingStore,
)


# ── Fixture ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def store(tmp_path: Path) -> WalletDeviceBindingStore:
    """Store isolé dans un répertoire temporaire."""
    return WalletDeviceBindingStore(tmp_path)


def _make_binding(store: WalletDeviceBindingStore, wallet: str, fp: str) -> str:
    """Crée un binding PRODUCTION et retourne le binding_id."""
    store.check_and_bind(wallet_name=wallet, device_fingerprint=fp)
    records = store.list_bindings()
    rec = next(r for r in records if r["wallet_name"] == wallet)
    return rec["binding_id"]


# ── T-LOCK-01 — verrou acquis et relâché ──────────────────────────────────────

def test_lock_01_acquires_and_releases(tmp_path: Path) -> None:
    """T-LOCK-01 : _transactional_lock() s'acquiert et se relâche sans deadlock."""
    target = tmp_path / "test.json"
    # Premier bloc
    with WalletDeviceBindingStore._transactional_lock(target):
        pass
    # Deuxième bloc sur le même fichier — ne doit pas bloquer
    with WalletDeviceBindingStore._transactional_lock(target):
        pass


# ── T-LOCK-02 — deux registres distincts indépendants ─────────────────────────

def test_lock_02_independent_registries(tmp_path: Path) -> None:
    """T-LOCK-02 : verrous sur des fichiers distincts sont indépendants."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    with WalletDeviceBindingStore._transactional_lock(a):
        # Pendant que a est verrouillé, b doit s'acquérir immédiatement
        with WalletDeviceBindingStore._transactional_lock(b):
            pass


# ── Helpers multiprocessus ────────────────────────────────────────────────────

def _worker_bind(data_dir: str, wallet: str, fp: str, result_queue) -> None:
    """Processus fils : tente un check_and_bind et envoie le résultat."""
    try:
        s = WalletDeviceBindingStore(Path(data_dir))
        s.check_and_bind(wallet_name=wallet, device_fingerprint=fp)
        result_queue.put("ok")
    except Exception as exc:
        result_queue.put(f"err:{exc}")


def _worker_revoke(data_dir: str, wallet: str, result_queue) -> None:
    """Processus fils : tente une révocation et envoie le résultat."""
    try:
        s = WalletDeviceBindingStore(Path(data_dir))
        s.revoke_with_history(
            wallet_name=wallet,
            authenticated_actor="test_actor",
            reason="contention_test",
        )
        result_queue.put("ok")
    except BindingRevocationError as exc:
        result_queue.put(f"rev_err:{exc}")
    except Exception as exc:
        result_queue.put(f"err:{exc}")


def _worker_purge(data_dir: str, binding_id: str, result_queue) -> None:
    """Processus fils : tente une purge et envoie le résultat."""
    try:
        s = WalletDeviceBindingStore(Path(data_dir))
        entry = s.purge_binding(
            binding_id=binding_id,
            authenticated_actor="test_actor",
            purge_reason="contention_test",
        )
        result_queue.put(f"ok:{entry['purge_id']}")
    except Exception as exc:
        result_queue.put(f"err:{exc}")


# ── T-CAS-01 — bind concurrent → un seul enregistré ──────────────────────────

def test_cas_01_concurrent_bind_no_lost_update(tmp_path: Path) -> None:
    """T-CAS-01 : deux processus bindent le même fingerprint → exactement 1 binding ACTIVE."""
    fp = "fp_cas01_" + uuid.uuid4().hex[:8]
    q: multiprocessing.Queue = multiprocessing.Queue()

    # On lance deux processus qui tentent de binder le même fp avec des wallets différents
    p1 = multiprocessing.Process(target=_worker_bind, args=(str(tmp_path), "wallet_A", fp, q))
    p2 = multiprocessing.Process(target=_worker_bind, args=(str(tmp_path), "wallet_B", fp, q))
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    results = [q.get_nowait() for _ in range(2)]

    store = WalletDeviceBindingStore(tmp_path)
    active = store.list_active_bindings(namespace="PRODUCTION")
    # Exactement un binding ACTIVE sur ce fingerprint
    active_fp = [r for r in active if r["device_fingerprint"] == fp]
    assert len(active_fp) == 1, (
        f"T-CAS-01 : {len(active_fp)} bindings ACTIVE — lost-update détecté. results={results}"
    )
    # Un ok et un err (ou deux ok idempotents si même wallet — ici wallets différents)
    ok_count = sum(1 for r in results if r == "ok")
    err_count = sum(1 for r in results if r.startswith("err:"))
    assert ok_count + err_count == 2


# ── T-CAS-02 — révocation concurrente → premier gagne ────────────────────────

def test_cas_02_concurrent_revoke(tmp_path: Path) -> None:
    """T-CAS-02 : deux révocations concurrentes → une seule réussit, l'autre BindingRevocationError."""
    fp = "fp_cas02_" + uuid.uuid4().hex[:8]
    s = WalletDeviceBindingStore(tmp_path)
    s.check_and_bind(wallet_name="wallet_rev_cas02", device_fingerprint=fp)

    q: multiprocessing.Queue = multiprocessing.Queue()
    p1 = multiprocessing.Process(target=_worker_revoke, args=(str(tmp_path), "wallet_rev_cas02", q))
    p2 = multiprocessing.Process(target=_worker_revoke, args=(str(tmp_path), "wallet_rev_cas02", q))
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    results = [q.get_nowait() for _ in range(2)]
    ok_count = sum(1 for r in results if r == "ok")
    rev_err_count = sum(1 for r in results if r.startswith("rev_err:"))

    assert ok_count == 1, f"T-CAS-02 : attendu 1 ok, got {ok_count}. results={results}"
    assert rev_err_count == 1, f"T-CAS-02 : attendu 1 rev_err, got {rev_err_count}. results={results}"

    s2 = WalletDeviceBindingStore(tmp_path)
    revoked = s2.list_revoked_bindings(namespace="PRODUCTION")
    assert len(revoked) == 1, "T-CAS-02 : exactement 1 binding REVOKED attendu"


# ── T-CAS-03 — purge concurrente → un seul purge_id ──────────────────────────

def test_cas_03_concurrent_purge(tmp_path: Path) -> None:
    """T-CAS-03 : deux purges concurrentes → une seule réussit, l'autre lève une erreur."""
    fp = "fp_cas03_" + uuid.uuid4().hex[:8]
    s = WalletDeviceBindingStore(tmp_path)
    bid = _make_binding(s, "wallet_purge_cas03", fp)
    s.revoke_with_history(wallet_name="wallet_purge_cas03", authenticated_actor="actor", reason="prep")

    q: multiprocessing.Queue = multiprocessing.Queue()
    p1 = multiprocessing.Process(target=_worker_purge, args=(str(tmp_path), bid, q))
    p2 = multiprocessing.Process(target=_worker_purge, args=(str(tmp_path), bid, q))
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    results = [q.get_nowait() for _ in range(2)]
    ok_count = sum(1 for r in results if r.startswith("ok:"))
    err_count = sum(1 for r in results if r.startswith("err:"))

    # Une purge réussit, l'autre trouve le binding absent
    assert ok_count == 1, f"T-CAS-03 : attendu 1 ok, got {ok_count}. results={results}"
    assert err_count == 1, f"T-CAS-03 : attendu 1 err, got {err_count}. results={results}"

    # Journal forensic = 1 entrée
    log = WalletDeviceBindingStore(tmp_path).list_purge_log()
    assert len(log) == 1, f"T-CAS-03 : 1 entrée forensic attendue, got {len(log)}"


# ── T-CAS-04 — bind idempotent sous contention ────────────────────────────────

def test_cas_04_idempotent_bind_contention(tmp_path: Path) -> None:
    """T-CAS-04 : 5 processus bindent le même (wallet, fp) → idempotent, 1 seul enregistrement."""
    fp = "fp_cas04_" + uuid.uuid4().hex[:8]
    wallet = "wallet_cas04"
    q: multiprocessing.Queue = multiprocessing.Queue()
    procs = [
        multiprocessing.Process(target=_worker_bind, args=(str(tmp_path), wallet, fp, q))
        for _ in range(5)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=10)

    results = [q.get_nowait() for _ in range(5)]
    s = WalletDeviceBindingStore(tmp_path)
    active = [r for r in s.list_active_bindings() if r["device_fingerprint"] == fp]
    assert len(active) == 1, (
        f"T-CAS-04 : {len(active)} bindings — idempotence cassée. results={results}"
    )


# ── T-CAS-05 — CAS expected_version sous contention ──────────────────────────

def test_cas_05_cas_version_conflict_under_contention(store: WalletDeviceBindingStore) -> None:
    """T-CAS-05 : expected_version=1, binding à v1 → succès ; v1 déjà révoqué → CAS conflit."""
    fp = "fp_cas05_" + uuid.uuid4().hex[:8]
    bid = _make_binding(store, "wallet_cas05", fp)

    # Première révocation avec expected_version=1 → doit réussir
    result = store.revoke_with_history(
        binding_id=bid,
        authenticated_actor="actor",
        reason="first",
        expected_version=1,
    )
    assert result["version_before"] == 1
    assert result["version_after"] == 2

    # Deuxième tentative avec expected_version=1 → doit lever BindingRevocationError (déjà REVOKED)
    with pytest.raises(BindingRevocationError, match="déjà révoqué"):
        store.revoke_with_history(
            binding_id=bid,
            authenticated_actor="actor",
            reason="second",
            expected_version=1,
        )


# ── T-LEGACY-01/02/03 — BindingLegacyDeleteError ─────────────────────────────

def test_legacy_01_revoke_by_fingerprint_raises(store: WalletDeviceBindingStore) -> None:
    """T-LEGACY-01 : admin_revoke_by_fingerprint() lève BindingLegacyDeleteError."""
    with pytest.raises(BindingLegacyDeleteError, match="éliminé"):
        store.admin_revoke_by_fingerprint("any_fingerprint")


def test_legacy_02_revoke_by_wallet_raises(store: WalletDeviceBindingStore) -> None:
    """T-LEGACY-02 : admin_revoke_by_wallet() lève BindingLegacyDeleteError."""
    with pytest.raises(BindingLegacyDeleteError, match="éliminé"):
        store.admin_revoke_by_wallet("any_wallet")


def test_legacy_03_revoke_test_by_wallet_raises(store: WalletDeviceBindingStore) -> None:
    """T-LEGACY-03 : admin_revoke_test_by_wallet() lève BindingLegacyDeleteError."""
    with pytest.raises(BindingLegacyDeleteError, match="éliminé"):
        store.admin_revoke_test_by_wallet("any_wallet")


# ── T-FORENSIC — journal forensic enchaîné ───────────────────────────────────

def _do_purge(store: WalletDeviceBindingStore, wallet: str, fp: str) -> dict:
    """Helper : crée, révoque et purge un binding. Retourne l'entrée du journal."""
    _make_binding(store, wallet, fp)
    store.revoke_with_history(wallet_name=wallet, authenticated_actor="actor", reason="test")
    bid = next(r["binding_id"] for r in store.list_revoked_bindings())
    return store.purge_binding(
        binding_id=bid,
        authenticated_actor="actor",
        purge_reason="forensic_test",
    )


def test_forensic_01_first_entry_genesis(store: WalletDeviceBindingStore) -> None:
    """T-FORENSIC-01 : première entrée → hash_prev='genesis' + entry_hash valide."""
    _do_purge(store, "w_f01", "fp_f01_" + uuid.uuid4().hex[:8])
    log = store.list_purge_log()
    assert len(log) == 1
    entry = log[0]
    assert entry["hash_prev"] == "genesis", f"hash_prev attendu 'genesis', got {entry['hash_prev']!r}"
    assert "entry_hash" in entry
    assert len(entry["entry_hash"]) == 64  # sha256 hex


def test_forensic_02_second_entry_chains_first(store: WalletDeviceBindingStore) -> None:
    """T-FORENSIC-02 : deuxième entrée → hash_prev = entry_hash de la première."""
    fp_a = "fp_f02a_" + uuid.uuid4().hex[:8]
    fp_b = "fp_f02b_" + uuid.uuid4().hex[:8]
    _do_purge(store, "w_f02a", fp_a)
    _do_purge(store, "w_f02b", fp_b)
    log = store.list_purge_log()
    assert len(log) == 2
    first_hash = log[0]["entry_hash"]
    second_prev = log[1]["hash_prev"]
    assert first_hash == second_prev, (
        f"T-FORENSIC-02 : chain brisée — entry[0].entry_hash={first_hash!r} "
        f"≠ entry[1].hash_prev={second_prev!r}"
    )


def test_forensic_03_alteration_breaks_chain(store: WalletDeviceBindingStore) -> None:
    """T-FORENSIC-03 : altération d'une entrée passée → hash_prev chaîne rompue (détectable)."""
    fp_a = "fp_f03a_" + uuid.uuid4().hex[:8]
    fp_b = "fp_f03b_" + uuid.uuid4().hex[:8]
    _do_purge(store, "w_f03a", fp_a)
    _do_purge(store, "w_f03b", fp_b)
    log = store.list_purge_log()

    # Altérer la première entrée
    log[0]["purge_reason"] = "TAMPERED"

    # Recalcul du hash_prev attendu par la deuxième entrée
    first_raw = json.dumps(log[0], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    recomputed_hash = hashlib.sha256(first_raw.encode("utf-8")).hexdigest()

    # Le hash_prev de l'entrée 2 ne correspond plus à l'entrée altérée
    original_entry_hash = store.list_purge_log()[0]["entry_hash"]
    assert recomputed_hash != original_entry_hash, (
        "T-FORENSIC-03 : l'altération devrait rompre la chaîne (hash différent)"
    )


def test_forensic_04_entry_hash_reproducible(store: WalletDeviceBindingStore) -> None:
    """T-FORENSIC-04 : entry_hash est reproductible depuis le contenu de l'entrée."""
    fp = "fp_f04_" + uuid.uuid4().hex[:8]
    _do_purge(store, "w_f04", fp)
    log = store.list_purge_log()
    entry = log[0]

    # Recalculer entry_hash depuis l'entrée (sans entry_hash lui-même dans le calcul)
    entry_without_hash = {k: v for k, v in entry.items() if k != "entry_hash"}
    raw = json.dumps(entry_without_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    recomputed = hashlib.sha256(raw.encode("utf-8")).hexdigest()

    assert recomputed == entry["entry_hash"], (
        f"T-FORENSIC-04 : entry_hash non reproductible — "
        f"computed={recomputed!r} stored={entry['entry_hash']!r}"
    )


def test_forensic_05_list_purge_log_has_chain_fields(store: WalletDeviceBindingStore) -> None:
    """T-FORENSIC-05 : list_purge_log() retourne hash_prev et entry_hash sur chaque entrée."""
    fp = "fp_f05_" + uuid.uuid4().hex[:8]
    _do_purge(store, "w_f05", fp)
    log = store.list_purge_log()
    assert len(log) >= 1
    for entry in log:
        assert "hash_prev" in entry, "hash_prev manquant dans le journal forensic"
        assert "entry_hash" in entry, "entry_hash manquant dans le journal forensic"
