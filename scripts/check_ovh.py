"""Script de vérification OVH — teste les clés API et la connectivité serveur.

Les clés API sont lues depuis l'environnement (jamais codées en dur) :
  OVH_APPLICATION_KEY, OVH_APPLICATION_SECRET, OVH_CONSUMER_KEY
  OVH_SERVER_IP (défaut : 152.228.144.34 — instance artcb-node-1, GRA11)
"""
import urllib.request, urllib.parse, json, time, hashlib, subprocess, socket
import os
import sys

OVH_APP_KEY = os.environ.get("OVH_APPLICATION_KEY", "")
OVH_APP_SECRET = os.environ.get("OVH_APPLICATION_SECRET", "")
OVH_CONSUMER_KEY = os.environ.get("OVH_CONSUMER_KEY", "")
if not (OVH_APP_KEY and OVH_APP_SECRET and OVH_CONSUMER_KEY):
    print("❌ Variables OVH_APPLICATION_KEY / OVH_APPLICATION_SECRET / OVH_CONSUMER_KEY absentes de l'environnement.")
    sys.exit(1)
OVH_ENDPOINT_BASE = "https://eu.api.ovh.com/1.0"
OVH_SERVER_IP = os.environ.get("OVH_SERVER_IP", "152.228.144.34")
OVH_SERVER_USER = os.environ.get("OVH_SERVER_USER", "ubuntu")

RESULTS = []

def chk(label, ok, detail=""):
    icon = "✅" if ok else "❌"
    print(f"{icon} {label}: {detail}")
    RESULTS.append((label, ok, detail))


# 1 — Ping serveur
try:
    r = subprocess.run(["ping", "-c", "2", "-W", "3", OVH_SERVER_IP],
                       capture_output=True, text=True, timeout=8)
    ok = r.returncode == 0
    latency = ""
    for line in r.stdout.splitlines():
        if "rtt" in line or "round-trip" in line:
            latency = line.split()[-1] if line.split() else ""
    chk("01_ping_serveur", ok, f"IP={OVH_SERVER_IP} {latency}")
except Exception as e:
    chk("01_ping_serveur", False, str(e)[:60])


# 2 — Port SSH 22 ouvert
try:
    s = socket.create_connection((OVH_SERVER_IP, 22), timeout=5)
    banner = s.recv(256).decode(errors="ignore").strip()
    s.close()
    chk("02_ssh_port_22", True, f"Banner: {banner[:60]}")
except Exception as e:
    chk("02_ssh_port_22", False, str(e)[:60])


# 3 — OVH API temps (sans auth)
server_time = None
try:
    req = urllib.request.urlopen(f"{OVH_ENDPOINT_BASE}/auth/time", timeout=5)
    server_time = int(json.loads(req.read()))
    delta = server_time - int(time.time())
    chk("03_ovh_api_time", True, f"server_time={server_time} delta={delta}s")
except Exception as e:
    chk("03_ovh_api_time", False, str(e)[:60])


# 4 — OVH API auth /me (signature HMAC-SHA1 correcte)
if server_time:
    method = "GET"
    url = f"{OVH_ENDPOINT_BASE}/me"
    body = ""
    ts = str(server_time)
    # Official OVH: "$1$" + sha1(AS+"+"+CK+"+"+METHOD+"+"+URL+"+"+BODY+"+"+TS)
    sig_input = "+".join([OVH_APP_SECRET, OVH_CONSUMER_KEY, method, url, body, ts])
    sig_hash = hashlib.sha1(sig_input.encode("utf-8")).hexdigest()
    sig = "$1$" + sig_hash

    headers = {
        "X-Ovh-Application": OVH_APP_KEY,
        "X-Ovh-Timestamp": ts,
        "X-Ovh-Signature": sig,
        "X-Ovh-Consumer": OVH_CONSUMER_KEY,
        "Accept": "application/json",
    }
    req2 = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req2, timeout=5)
        data = json.loads(resp.read())
        name = f"{data.get('firstname', '')} {data.get('name', '')}".strip()
        email = data.get("email", "?")
        nichandle = data.get("nichandle", "?")
        state = data.get("state", "?")
        chk("04_ovh_api_me", True, f"nichandle={nichandle} name={name} email={email} state={state}")
    except urllib.error.HTTPError as e:
        body_err = e.read().decode()
        chk("04_ovh_api_me", False, f"HTTP {e.code}: {body_err[:120]}")
    except Exception as e:
        chk("04_ovh_api_me", False, str(e)[:80])
else:
    chk("04_ovh_api_me", False, "SKIP — pas de server_time")


# 5 — Liste des instances OVH Cloud (si Consumer Key a les droits)
if server_time:
    # Lister les services (cloud projects)
    method2 = "GET"
    url2 = f"{OVH_ENDPOINT_BASE}/cloud/project"
    ts2 = str(int(time.time()) + (server_time - int(time.time())))
    # Recalcul avec nouveau ts
    req_time = urllib.request.urlopen(f"{OVH_ENDPOINT_BASE}/auth/time", timeout=5)
    ts2 = str(int(json.loads(req_time.read())))
    sig_input2 = "+".join([OVH_APP_SECRET, OVH_CONSUMER_KEY, method2, url2, "", ts2])
    sig2 = "$1$" + hashlib.sha1(sig_input2.encode("utf-8")).hexdigest()
    headers2 = {
        "X-Ovh-Application": OVH_APP_KEY,
        "X-Ovh-Timestamp": ts2,
        "X-Ovh-Signature": sig2,
        "X-Ovh-Consumer": OVH_CONSUMER_KEY,
        "Accept": "application/json",
    }
    req3 = urllib.request.Request(url2, headers=headers2)
    try:
        resp3 = urllib.request.urlopen(req3, timeout=5)
        projects = json.loads(resp3.read())
        chk("05_cloud_projects", True, f"projects={projects}")
    except urllib.error.HTTPError as e:
        body_err = e.read().decode()
        chk("05_cloud_projects", False, f"HTTP {e.code}: {body_err[:120]}")
    except Exception as e:
        chk("05_cloud_projects", False, str(e)[:80])


# 6 — Test HTTP sur le serveur dédié (si nginx/apache tourne)
try:
    req4 = urllib.request.urlopen(f"http://{OVH_SERVER_IP}", timeout=5)
    chk("06_http_server", True, f"HTTP {req4.status} — serveur web actif")
except urllib.error.HTTPError as e:
    chk("06_http_server", True, f"HTTP {e.code} — serveur répond (attendu)")
except Exception as e:
    chk("06_http_server", False, f"Pas de serveur HTTP: {str(e)[:60]}")


# ── Résumé
print()
print("=" * 55)
ok_n = sum(1 for _, ok, _ in RESULTS if ok)
print(f"  OVH : {ok_n}/{len(RESULTS)} OK")
fails = [(l, d) for l, ok, d in RESULTS if not ok]
if fails:
    print()
    print("  PROBLÈMES :")
    for l, d in fails:
        print(f"    ❌ {l}: {d[:70]}")
print("=" * 55)
