"""Benchmark réel ARTCB — mesures des performances sur machine locale.
Résultats utilisés pour le rapport 106.
Exécuter depuis le répertoire racine du projet :
  python3 -m scripts.bench_artcb_real
"""
from __future__ import annotations
import sys, os, time, statistics, json, datetime, tempfile
from pathlib import Path

# Racine projet dans PYTHONPATH (les modules utilisent "from src.artcb.*")
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from src.artcb.crypto.pqc import generate_keypair, sign_message, verify_message
from src.artcb.crypto.kem import generate_kem_keypair, encapsulate, decapsulate, _oqs_available
from src.artcb.chain.manager import ChainManager
from src.artcb.wallet.manager import WalletManager

ROUNDS = 50

def bench(label, fn, rounds=ROUNDS):
    times = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    avg_ms = statistics.mean(times) * 1000
    med_ms = statistics.median(times) * 1000
    min_ms = min(times) * 1000
    max_ms = max(times) * 1000
    print(f"  {label:<50} avg={avg_ms:7.2f}ms  med={med_ms:7.2f}ms  min={min_ms:6.2f}  max={max_ms:6.2f}  n={rounds}")
    return {"label": label, "avg_ms": round(avg_ms,3), "med_ms": round(med_ms,3),
            "min_ms": round(min_ms,3), "max_ms": round(max_ms,3), "rounds": rounds}

results = []

# ── PQC ML-DSA-65 ──────────────────────────────────────────────────────────
print("\n=== PQC ML-DSA-65 (liboqs natif) ===")
sk, pk = generate_keypair()
msg = b"ARTCB benchmark payload test message " * 8  # ~296 bytes

results.append(bench("ML-DSA-65 generate_keypair()", generate_keypair))
results.append(bench("ML-DSA-65 sign_message(296B)", lambda: sign_message(msg, sk)))
sig = sign_message(msg, sk)
results.append(bench("ML-DSA-65 verify_message(296B)", lambda: verify_message(msg, sig, pk)))

# ── KEM ──────────────────────────────────────────────────────────────────────
print("\n=== KEM ML-KEM-768 / X25519-fallback ===")
kem_available = _oqs_available()
print(f"  liboqs KEM natif disponible : {kem_available}")
_sk_kem, pk_kem = generate_kem_keypair()
results.append(bench("KEM generate_kem_keypair()", generate_kem_keypair))
ct, _ss = encapsulate(pk_kem)
results.append(bench("KEM encapsulate()", lambda: encapsulate(pk_kem)))
results.append(bench("KEM decapsulate()", lambda: decapsulate(ct, _sk_kem)))

# ── ChainManager ARTCB ───────────────────────────────────────────────────────
print("\n=== ChainManager ARTCB (PoL + signatures hybrides) ===")
with tempfile.TemporaryDirectory() as tmpdir:
    blocks_path = Path(tmpdir) / "chain.jsonl"
    key_path    = Path(tmpdir) / "chain.key"
    chain = ChainManager(blocks_path=blocks_path, key_path=key_path, enable_security=False)

    # Warm-up
    chain.append_block(graph_id="warmup", graph_root="abc123", pol_score=0.5, source="bench")

    def _add_block():
        chain.append_block(
            graph_id=f"g_{time.time_ns()}",
            graph_root="benchhash0123456789abcdef",
            pol_score=0.75,
            source="bench",
        )

    results.append(bench("append_block() sans sécurité", _add_block, rounds=30))

    # Vérification chaîne
    for i in range(80):
        chain.append_block(graph_id=f"blk_{i}", graph_root=f"root_{i:04x}", pol_score=float(i)/100, source="bench")

    nb_blocks = len(chain.list_blocks())
    results.append(bench("verify() chaîne complète", lambda: chain.verify(), rounds=20))
    print(f"  Longueur chaîne test : {nb_blocks} blocs")

# ── ChainManager avec sécurité (tempdir isolé — pas le livre live) ──────────
print("\n=== ChainManager ARTCB (sécurité ON — Anti-Sybil + Slashing) ===")
print("  Isolated tempdir only. Does not append to live blocks.jsonl.")
os.environ.setdefault("ARTCB_MIN_BLOCK_INTERVAL_SEC", "0")
try:
    with tempfile.TemporaryDirectory() as tmpdir2:
        blocks2 = Path(tmpdir2) / "chain.jsonl"
        key2    = Path(tmpdir2) / "chain.key"
        chain2  = ChainManager(blocks_path=blocks2, key_path=key2, enable_security=True)

        contributors = [
            {"address": "artcb1test0001aaaa", "pol_score": 0.8, "role": "miner"},
            {"address": "artcb1test0002bbbb", "pol_score": 0.6, "role": "contributor"},
        ]
        chain2.append_block(graph_id="w0", graph_root="root0", pol_score=0.75,
                            contributors=contributors, source="ai:bench")

        results.append(bench("append_block() + Anti-Sybil (2 contributors)",
                             lambda: chain2.append_block(
                                 graph_id=f"s_{time.time_ns()}",
                                 graph_root="secured_root_ab",
                                 pol_score=0.8,
                                 contributors=contributors,
                                 source="ai:bench",
                             ), rounds=20))
except Exception as exc:  # noqa: BLE001 — official machine campaign must still write JSON
    print(f"  SKIP anti-sybil burst: {type(exc).__name__}: {exc}")
    results.append({"label": "append_block() + Anti-Sybil (2 contributors)", "skipped": True, "error": type(exc).__name__})

# ── Wallet ──────────────────────────────────────────────────────────────────
print("\n=== Wallet ARTCB (création + hybrid keypair) ===")
try:
    wm = WalletManager()
    results.append(bench("WalletManager.create_wallet()", lambda: wm.create_wallet(name=f"bench_{time.time_ns()}"), rounds=20))
except Exception as exc:  # noqa: BLE001
    print(f"  SKIP wallet: {type(exc).__name__}: {exc}")
    results.append({"label": "WalletManager.create_wallet()", "skipped": True, "error": type(exc).__name__})

# ── TPS simulation ──────────────────────────────────────────────────────────
print("\n=== TPS simulation ARTCB ===")
with tempfile.TemporaryDirectory() as tmpdir_tps:
    chain_tps = ChainManager(
        blocks_path=Path(tmpdir_tps) / "chain.jsonl",
        key_path=Path(tmpdir_tps) / "chain.key",
        enable_security=False,
    )
    N_BLOCKS = 200
    t_start = time.perf_counter()
    for i in range(N_BLOCKS):
        chain_tps.append_block(graph_id=f"tx_{i}", graph_root=f"root_{i}", pol_score=0.5, source="bench")
    elapsed = time.perf_counter() - t_start
    tps_blocks = N_BLOCKS / elapsed
    print(f"  {N_BLOCKS} blocs créés en {elapsed*1000:.1f}ms → {tps_blocks:.0f} blocs/s")
    results.append({
        "label": f"TPS isolated tempdir ({N_BLOCKS} appends, security OFF)",
        "tps": round(tps_blocks, 1),
        "elapsed_ms": round(elapsed * 1000, 1),
        "n_blocks": N_BLOCKS,
        "not_distributed_mainnet": True,
        "not_wan": True,
    })

# ── Résumé JSON ──────────────────────────────────────────────────────────────
ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
out = {
    "timestamp": ts,
    "python": sys.version.split()[0],
    "platform": sys.platform,
    "pqc_algo": "ML-DSA-65",
    "kem_algo": "ML-KEM-768" if kem_available else "X25519-fallback",
    "kem_native": kem_available,
    "results": results,
    "tps_blocks": round(tps_blocks, 1),
    "tps_is_isolated_tempdir_not_distributed_mainnet": True,
}
os.makedirs("logs", exist_ok=True)
fname = f"logs/bench_artcb_{ts}.json"
with open(fname, "w") as f:
    json.dump(out, f, indent=2)
print(f"\n✅ Résultats JSON → {fname}")
print("\n=== RÉSUMÉ ===")
for r in results:
    if "avg_ms" in r:
        print(f"  {r['label']:<50} {r['avg_ms']:8.3f} ms/op")
    elif "tps" in r:
        print(f"  {r['label']:<50} {r['tps']:8.1f} blocs/s")
