#!/usr/bin/env bash
# Isolate ovh-node-4 from the other three official IPv4s on :8000 and :8443.
# The artcb process stays UP. blocks.jsonl is never touched.
# Comment mark: artcb261 — restore deletes ONLY those rules.
#
# Usage (on OVH4): isolate | restore | status
set -euo pipefail
COMMENT="artcb261"
PEERS=(152.228.144.34 151.80.107.29 51.44.222.232)
PORTS="8000,8443"

_rules() {
  local peer
  for peer in "${PEERS[@]}"; do
    echo "INPUT -s ${peer} -p tcp -m multiport --dports ${PORTS} -m comment --comment ${COMMENT} -j DROP"
    echo "OUTPUT -d ${peer} -p tcp -m multiport --dports ${PORTS} -m comment --comment ${COMMENT} -j DROP"
  done
}

isolate() {
  local spec
  while IFS= read -r spec; do
    # shellcheck disable=SC2086
    if ! sudo iptables -C ${spec} 2>/dev/null; then
      # shellcheck disable=SC2086
      sudo iptables -I ${spec}
    fi
  done < <(_rules)
  echo "ISOLATED comment=${COMMENT} peers=${PEERS[*]} dports=${PORTS}"
}

restore() {
  local spec
  while IFS= read -r spec; do
    # shellcheck disable=SC2086
    while sudo iptables -C ${spec} 2>/dev/null; do
      # shellcheck disable=SC2086
      sudo iptables -D ${spec}
    done
  done < <(_rules)
  echo "RESTORED comment=${COMMENT}"
}

status() {
  echo "HOST=$(hostname)"
  echo "ARTCB=$(systemctl is-active artcb || true)"
  echo "BOOK=$(wc -l < /home/ubuntu/artcb/data/chain/blocks.jsonl | tr -d ' ')"
  echo "RULES=$(sudo iptables-save | grep -c "${COMMENT}" || true)"
  sudo iptables-save | grep "${COMMENT}" || true
}

cmd="${1:-status}"
case "$cmd" in
  isolate) isolate; status ;;
  restore) restore; status ;;
  status) status ;;
  *) echo "usage: $0 isolate|restore|status" >&2; exit 2 ;;
esac
