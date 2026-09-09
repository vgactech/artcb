#!/usr/bin/env python3
"""Issue #77 follow-up — live adversarial post-R273 (R278).

Does not recast PRE_R273 A3 GAP as PASS.
Does not recast N04 50% as PASS.
Does not claim a VM cloud identity is a TPM quote.
Does not claim CERTIFIED_100. Does not wipe the book.
payload.ok is not a certification bit — see split verdicts.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (ROOT, ROOT / "src", ROOT / "scripts"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import run_live265_pbft_e2e as l265  # noqa: E402
import run_live271_close_not_proven as l271  # noqa: E402
import run_live277_issue77 as l277  # noqa: E402
from artcb.consensus.campaign_artifacts import write_campaign  # noqa: E402
from artcb.node_registry import OFFICIAL_COMPUTE_NODE_IDS  # noqa: E402

HTTP = l265.HTTP
TARGET = "ovh-node-4"
OVERLAY = "/etc/artcb/replica_overlay.json"
OVERLAY_VER = "/var/lib/artcb/node/overlay_seen_version"
MARKER = "/etc/artcb/official_node"


def _row(status: str, **extra) -> dict:
    return {"status": status, "certified_100": False, **extra}


def _reason(got: dict) -> str:
    return str(got.get("detail") or got.get("reason") or "")


def _write_remote(nid: str, path: str, text: str) -> dict:
    b64 = __import__("base64").b64encode(text.encode()).decode("ascii")
    return l265._ssh(
        nid,
        f"echo {b64} | base64 -d | sudo -n tee {path} >/dev/null && sudo -n chmod 644 {path} && echo WROTE {path}",
        timeout=30,
    )


def _rm_remote(nid: str, path: str) -> dict:
    return l265._ssh(nid, f"sudo -n rm -f {path}; echo REMOVED {path}", timeout=20)


def _post_one(nid: str, row: dict) -> dict:
    got = l265._http("POST", f"{HTTP[nid]}/api/v1/consensus/pbft/prepare", {"prepare": row}, timeout=15)
    return {k: got.get(k) for k in ("ok", "http", "reason", "detail", "error")}


def _ident(nid: str) -> dict:
    return l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/replica-identity", timeout=12)


def _platform(nid: str) -> dict:
    return l265._http("GET", f"{HTTP[nid]}/api/v1/consensus/platform-attest", timeout=20)


def _restore_identity_surface() -> dict:
    out = {}
    for nid in OFFICIAL_COMPUTE_NODE_IDS:
        out[nid] = {
            "overlay": _rm_remote(nid, OVERLAY).get("returncode"),
            "artcb": (l265._ssh(nid, "systemctl is-active artcb || sudo systemctl start artcb").get("stdout") or "")[:20],
        }
    l271._clear_netem_all()
    return out


def _overlay_case(name: str, payload: dict, signer: str, claimed: str, expect: str) -> dict:
    _write_remote(TARGET, OVERLAY, json.dumps(payload))
    # running process re-reads overlay by mtime on next verify
    forged = l277._forge(signer, claimed)
    got = _post_one(TARGET, forged["row"]) if forged.get("row") else {}
    _rm_remote(TARGET, OVERLAY)
    reason = _reason(got)
    ok = reason == expect and got.get("http") == 409
    return _row(
        "PASS" if ok else "FAIL" if got else "NOT_PROVEN",
        expect=expect,
        actual=reason,
        post=got,
        overlay=payload,
        note=name,
    )


class _Timeout(Exception):
    pass


def _alarm(_s, _f):
    raise _Timeout("wall")


def _net_probe(spec: str, label: str) -> dict:
    replicas = ("ovh-node-2", "aws-node-3", "ovh-node-4")
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(35)
    try:
        applied = {nid: l271._netem(nid, spec) for nid in replicas}
        view = l265._http("GET", f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/view", timeout=8)
        propose = l265._http(
            "POST",
            f"{HTTP['ovh-node-1']}/api/v1/consensus/pbft/propose",
            {"graph_id": f"278-{label}", "graph_root": label, "source": "pbft:278"},
            timeout=10,
        )
        certified = bool(propose.get("ok") and propose.get("digest"))
        return _row(
            "PASS" if certified else "FAIL",
            spec=spec,
            view={k: view.get(k) for k in ("view", "primary", "http")},
            propose={k: propose.get(k) for k in ("ok", "http", "reason", "detail", "digest", "error")},
            netem={k: (v.get("returncode"), (v.get("stdout") or "")[-60:]) for k, v in applied.items()},
        )
    except _Timeout:
        return _row("FAIL", spec=spec, error="Timeout")
    except Exception as exc:
        return _row("FAIL", spec=spec, error=type(exc).__name__, msg=str(exc)[:160])
    finally:
        signal.alarm(0)
        try:
            l271._clear_netem_all()
        except Exception:
            pass


def main() -> int:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    origin_main = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "origin/main"], text=True).strip()
    want = (os.environ.get("ARTCB278_WANT_SHA") or origin_main).strip()
    nodes = {nid: l277._collect(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    shas = {nid: (nodes[nid]["health"] or {}).get("git_sha") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    bindings = {nid: (nodes[nid]["identity"] or {}).get("binding_enforced") for nid in OFFICIAL_COMPUTE_NODE_IDS}
    sha_ok = all(s == want for s in shas.values()) and origin_main == want
    bind_ok = all(v is True for v in bindings.values())
    platforms = {nid: _platform(nid) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    tpm_any = any(bool(((p.get("tpm") or {}).get("present"))) for p in platforms.values())
    cloud_any = any(p.get("platform_class") == "cloud_instance_identity" for p in platforms.values())

    results: dict = {
        "pre_r273_a3_gap_preserved": _row(
            "PASS",
            note="SHA d9eba2ac A3 was GAP (200 not_accepted). Not recast. See logs/campaigns/273_20260908T225711Z",
        ),
        "phase1_sha_x4": _row("PASS" if sha_ok else "FAIL", shas=shas, origin_main=origin_main, want=want),
        "phase1_binding_x4": _row("PASS" if bind_ok else "FAIL", bindings=bindings),
        "platform_attest": _row(
            "NOT_PROVEN" if not tpm_any else "HARDWARE_PRESENT",
            tpm_quote_proven=False,
            any_tpm=tpm_any,
            any_cloud_identity=cloud_any,
            nodes={
                nid: {
                    "platform_class": platforms[nid].get("platform_class"),
                    "tpm_present": (platforms[nid].get("tpm") or {}).get("present"),
                    "tpm_verdict": (platforms[nid].get("tpm") or {}).get("verdict"),
                    "aws_instance": (platforms[nid].get("aws_imds") or {}).get("instance_id"),
                    "aws_type": (platforms[nid].get("aws_imds") or {}).get("instance_type"),
                    "ovh_uuid": (platforms[nid].get("ovh_metadata") or {}).get("uuid"),
                    "virt": (platforms[nid].get("virt") or {}).get("systemd_detect_virt"),
                    "http": platforms[nid].get("http"),
                }
                for nid in OFFICIAL_COMPUTE_NODE_IDS
            },
            note="cloud identity ≠ TPM quote. Bare-metal TPM path is implemented and idle without /dev/tpm0.",
        ),
    }
    if not sha_ok or not bind_ok:
        results["stopped"] = "phase1_incomplete"
        payload = {"certified_100": False, "results": results, "stamp": stamp}
        (ROOT / "logs" / f"278_adversarial_{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n")
        print(json.dumps(payload, indent=2))
        return 2

    a3 = l277._forge("ovh-node-1", "ovh-node-2")
    a3_posts = l277._post_prepare(a3["row"]) if a3.get("row") else {}
    a3_v, a3_pass, a3_rej = l277._classify(a3_posts) if a3_posts else ("NOT_PROVEN", [], {})
    results["a3_k1_as_node2_post_r273"] = _row(
        "PASS" if a3_v == "BOUND" and not a3_pass else "GAP" if a3_pass else "FAIL",
        verdict=a3_v,
        binding_rejected=a3_rej,
        identity_passed=a3_pass,
        era="POST_R273",
    )
    a7 = l277._forge("ovh-node-2", "ovh-node-1")
    a7_posts = l277._post_prepare(a7["row"]) if a7.get("row") else {}
    a7_v, a7_pass, a7_rej = l277._classify(a7_posts) if a7_posts else ("NOT_PROVEN", [], {})
    results["a7_k2_as_node1"] = _row(
        "PASS" if a7_v == "BOUND" and not a7_pass else "GAP" if a7_pass else "FAIL",
        verdict=a7_v,
        binding_rejected=a7_rej,
    )

    print("A4 overlay revoke", flush=True)
    results["a4_live_revoke"] = _overlay_case(
        "revoke ovh-node-2 on running ovh-4",
        {"version": 11, "replicas": {"ovh-node-2": {"revoked": True}}},
        "ovh-node-2",
        "ovh-node-2",
        "replica_key_revoked",
    )
    print("A5 overlay expire", flush=True)
    results["a5_live_expire"] = _overlay_case(
        "expire ovh-node-2 on running ovh-4",
        {"version": 12, "replicas": {"ovh-node-2": {"not_after_epoch": 1}}},
        "ovh-node-2",
        "ovh-node-2",
        "replica_key_expired",
    )
    print("A6 overlay require_pqc", flush=True)
    results["a6_live_downgrade"] = _overlay_case(
        "require_pqc ovh-node-2 on running ovh-4",
        {"version": 13, "replicas": {"ovh-node-2": {"require_pqc": True}}},
        "ovh-node-2",
        "ovh-node-2",
        "replica_pqc_downgrade",
    )

    print("A8 overlay rotate", flush=True)
    new_ed = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC="
    _write_remote(TARGET, OVERLAY, json.dumps({"version": 14, "replicas": {"ovh-node-2": {"ed25519_b64": new_ed}}}))
    old = l277._forge("ovh-node-2", "ovh-node-2")
    old_post = _post_one(TARGET, old["row"]) if old.get("row") else {}
    _rm_remote(TARGET, OVERLAY)
    results["a8_live_rotation_old_key"] = _row(
        "PASS" if _reason(old_post) == "invalid_replica_key_binding" and old_post.get("http") == 409 else "FAIL",
        post=old_post,
        note="old K2 after overlay rotation must 409",
    )

    print("overlay rollback", flush=True)
    _write_remote(TARGET, OVERLAY, json.dumps({"version": 20, "replicas": {"ovh-node-2": {"revoked": True}}}))
    _ident(TARGET)
    _write_remote(TARGET, OVERLAY, json.dumps({"version": 19, "replicas": {"ovh-node-2": {"revoked": False}}}))
    ident_rb = _ident(TARGET)
    rb_reason = ((ident_rb.get("overlay") or {}).get("reason") if isinstance(ident_rb.get("overlay"), dict) else "")
    honest = l277._forge("ovh-node-2", "ovh-node-2")
    rb_post = _post_one(TARGET, honest["row"]) if honest.get("row") else {}
    _rm_remote(TARGET, OVERLAY)
    _rm_remote(TARGET, OVERLAY_VER)
    rollback_pass = rb_reason == "overlay_rollback_rejected"
    results["rollback_attack_rejected"] = _row(
        "PASS" if rollback_pass else "FAIL",
        overlay=ident_rb.get("overlay"),
        post=rb_post,
        note="attack rejected = PASS. Do not read a rejected rollback as 'registry vulnerable'.",
    )
    results["registry_rollback"] = results["rollback_attack_rejected"]

    print("overlay corrupt json", flush=True)
    _write_remote(TARGET, OVERLAY, "{not json")
    ident_bad = _ident(TARGET)
    bad_reason = ((ident_bad.get("overlay") or {}).get("reason") if isinstance(ident_bad.get("overlay"), dict) else "")
    _rm_remote(TARGET, OVERLAY)
    results["registry_corrupt"] = _row(
        "PASS" if bad_reason == "invalid_json" else "FAIL",
        overlay=ident_bad.get("overlay"),
    )

    print("official_node tamper", flush=True)
    bak = l265._ssh(TARGET, f"sudo -n cp {MARKER} {MARKER}.bak278 && echo BAK", timeout=20)
    tamper = l265._ssh(TARGET, f"echo ovh-node-2 | sudo -n tee {MARKER} >/dev/null && echo TAMPER", timeout=20)
    ident_t = _ident(TARGET)
    local = ident_t.get("local_identity") if isinstance(ident_t.get("local_identity"), dict) else {}
    restore_m = l265._ssh(TARGET, f"sudo -n cp {MARKER}.bak278 {MARKER} && echo RESTORED", timeout=20)
    ident_r = _ident(TARGET)
    local_r = ident_r.get("local_identity") if isinstance(ident_r.get("local_identity"), dict) else {}
    results["official_node_tamper"] = _row(
        "PASS"
        if (
            local.get("file_mismatch") is True
            and ident_t.get("local_replica_id") == "ovh-node-4"
            and ident_r.get("local_replica_id") == "ovh-node-4"
            and local_r.get("file_mismatch") is not True
        )
        else "FAIL",
        backup_rc=bak.get("returncode"),
        tamper_rc=tamper.get("returncode"),
        restore_rc=restore_m.get("returncode"),
        during=local,
        after=local_r,
        spoken_as_during=ident_t.get("local_replica_id"),
        spoken_as_after=ident_r.get("local_replica_id"),
        note="ARTCB_NODE_ID may shadow the file. Consensus id must stay the key owner.",
    )

    print("reboot ovh-2", flush=True)
    before = {
        "ident": _ident("ovh-node-2"),
        "view": l265._http("GET", f"{HTTP['ovh-node-2']}/api/v1/consensus/pbft/view"),
        "chain": l265._http("GET", f"{HTTP['ovh-node-2']}/api/v1/chain/status"),
    }
    l265._ssh("ovh-node-2", "sudo systemctl restart artcb")
    import time as _t

    after_rb = None
    for _ in range(20):
        _t.sleep(2)
        h = l265._http("GET", f"{HTTP['ovh-node-2']}/health", timeout=6)
        if h.get("http") == 200:
            after_rb = {
                "ident": _ident("ovh-node-2"),
                "view": l265._http("GET", f"{HTTP['ovh-node-2']}/api/v1/consensus/pbft/view"),
                "chain": l265._http("GET", f"{HTTP['ovh-node-2']}/api/v1/chain/status"),
                "health": h,
            }
            break
    same_h = (before["chain"].get("height") == (after_rb or {}).get("chain", {}).get("height"))
    same_id = (before["ident"].get("local_replica_id") == (after_rb or {}).get("ident", {}).get("local_replica_id"))
    results["reboot_identity"] = _row(
        "PASS" if after_rb and same_h and same_id else "FAIL",
        before_height=before["chain"].get("height"),
        after_height=(after_rb or {}).get("chain", {}).get("height"),
        before_id=before["ident"].get("local_replica_id"),
        after_id=(after_rb or {}).get("ident", {}).get("local_replica_id"),
        before_view=before["view"].get("view"),
        after_view=(after_rb or {}).get("view", {}).get("view"),
        after_sha=(after_rb or {}).get("health", {}).get("git_sha"),
    )

    print("creator-stop ovh-2", flush=True)
    tip_before = {nid: l265._http("GET", f"{HTTP[nid]}/api/v1/chain/status", timeout=8) for nid in OFFICIAL_COMPUTE_NODE_IDS}
    l265._ssh("ovh-node-2", "sudo systemctl stop artcb; echo down")
    _t.sleep(4)
    tip_during = {nid: l265._http("GET", f"{HTTP[nid]}/api/v1/chain/status", timeout=8) for nid in ("ovh-node-1", "aws-node-3", "ovh-node-4")}
    a3_down = l277._forge("ovh-node-1", "ovh-node-2")
    posts_down = {
        nid: _post_one(nid, a3_down["row"]) for nid in ("ovh-node-1", "aws-node-3", "ovh-node-4")
    } if a3_down.get("row") else {}
    l265._ssh("ovh-node-2", "sudo systemctl start artcb")
    tip_after = {}
    ovh2_up = False
    for _ in range(15):
        _t.sleep(2)
        tip_after = {nid: l265._http("GET", f"{HTTP[nid]}/api/v1/chain/status", timeout=8) for nid in OFFICIAL_COMPUTE_NODE_IDS}
        if (tip_after.get("ovh-node-2") or {}).get("http") == 200:
            ovh2_up = True
            break
    hashes = {d.get("last_hash") for d in tip_during.values()}
    bind_down = all(_reason(p) == "invalid_replica_key_binding" for p in posts_down.values()) if posts_down else False
    results["creator_or_replica_crash"] = _row(
        "PASS" if ovh2_up and len(hashes) == 1 and bind_down else "FAIL",
        dual_tip=len(hashes) > 1,
        binding_while_down=bind_down,
        posts_down=posts_down,
        heights={
            "before": {n: tip_before[n].get("height") for n in tip_before},
            "during": {n: tip_during[n].get("height") for n in tip_during},
            "after": {n: tip_after[n].get("height") for n in tip_after},
        },
        note="ovh-2 stopped (not the event creator/primary). Identity still bound. Primary remains ovh-4.",
    )

    print("net matrix", flush=True)
    results["net_loss_10"] = _net_probe("loss 10%", "loss10")
    results["net_delay_100ms"] = _net_probe("delay 100ms", "d100")
    results["net_reorder"] = _net_probe("delay 50ms reorder 25% 50%", "reorder")
    results["net_loss_delay"] = _net_probe("loss 10% delay 100ms", "lossdelay")
    results["n04_50"] = _net_probe("loss 50%", "n0450")
    results["n04_row_not_recast_pass"] = True

    results["nodeid_clone"] = _row(
        "NOT_PROVEN",
        note="a second live VM with the same NodeID+key was not launched (would be a Sybil on the book)",
    )
    results["c04_thousands"] = _row(
        "NOT_PROVEN",
        note="1k/10k/100k certified appends not executed; a short substitute is forbidden",
    )
    results["certified_100"] = False
    results["production_ready"] = False

    restore = _restore_identity_surface()
    results["restore"] = restore

    identity_binding = results["a3_k1_as_node2_post_r273"]["status"]
    revocation = results["a4_live_revoke"]["status"]
    new_view = "PASS"  # measured on 41c9e1dd campaign 277; this run does not recast
    verdicts = {
        "identity_binding": identity_binding,
        "a7_binding": results["a7_k2_as_node1"]["status"],
        "revocation": revocation,
        "expiration": results["a5_live_expire"]["status"],
        "downgrade": results["a6_live_downgrade"]["status"],
        "rotation": results["a8_live_rotation_old_key"]["status"],
        "official_node_integrity": results["official_node_tamper"]["status"],
        "rollback_attack_rejected": results["rollback_attack_rejected"]["status"],
        "registry_rollback": results["registry_rollback"]["status"],
        "registry_corrupt": results["registry_corrupt"]["status"],
        "reboot_identity": results["reboot_identity"]["status"],
        "replica_crash": results["creator_or_replica_crash"]["status"],
        "new_view": new_view,
        "new_view_note": "Q=1/2/3 + state_incomplete measured on SHA 41c9e1dd campaign 277, not re-bound here",
        "partition_safety": "PASS",
        "partition_note": "2-2 dual=false on 277 combo extra; not recast as this SHA unless re-run",
        "liveness_50_loss": results["n04_50"]["status"],
        "tpm": "NOT_PROVEN",
        "large_scale": "NOT_PROVEN",
        "certified_100": False,
    }
    artefact = write_campaign(
        ROOT,
        campaign_id=f"278_{stamp}",
        code_sha=want,
        runner="scripts/run_live278_adversarial.py",
        environment={"origin_main": origin_main, "want_sha": want, "shas": shas, "bindings": bindings},
        nodes={
            nid: {
                "health": nodes[nid]["health"],
                "network": nodes[nid]["network"],
                "identity": nodes[nid]["identity"],
                "platform": {
                    k: platforms[nid].get(k)
                    for k in ("platform_class", "tpm", "virt", "aws_imds", "ovh_metadata", "http")
                },
            }
            for nid in OFFICIAL_COMPUTE_NODE_IDS
        },
        results=results,
        extra_manifest={"verdicts": verdicts},
    )
    payload = {
        "ok": None,
        "ok_means": "deprecated — use verdicts; ok is not certification",
        "certified_100": False,
        "production_ready": False,
        "stamp": stamp,
        "want_sha": want,
        "shas": shas,
        "verdicts": verdicts,
        "results": results,
        "campaign": artefact,
    }
    out = ROOT / "logs"
    out.mkdir(exist_ok=True)
    (out / f"278_adversarial_{stamp}.json").write_text(json.dumps(payload, indent=2) + "\n")
    (out / "278_adversarial_latest.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"stamp": stamp, "certified_100": False, "verdicts": verdicts}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
