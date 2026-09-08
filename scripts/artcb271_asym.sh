#!/usr/bin/env bash
# Asymmetric partition: drop OUTPUT to peer :8000/:8443, leave INPUT open.
# Usage: drop PEER_IP | restore PEER_IP | status
set -euo pipefail
COMMENT="artcb271-asym"
PORTS="8000,8443"

cmd="${1:-status}"
peer="${2:-}"
case "$cmd" in
  drop)
    [[ -n "$peer" ]] || { echo "usage: $0 drop PEER_IP" >&2; exit 2; }
    spec="OUTPUT -d ${peer} -p tcp -m multiport --dports ${PORTS} -m comment --comment ${COMMENT} -j DROP"
    if ! sudo iptables -C ${spec} 2>/dev/null; then
      sudo iptables -I ${spec}
    fi
    echo "ASYM_DROP dst=$peer"
    ;;
  restore)
    [[ -n "$peer" ]] || { echo "usage: $0 restore PEER_IP" >&2; exit 2; }
    spec="OUTPUT -d ${peer} -p tcp -m multiport --dports ${PORTS} -m comment --comment ${COMMENT} -j DROP"
    while sudo iptables -C ${spec} 2>/dev/null; do
      sudo iptables -D ${spec}
    done
    echo "ASYM_RESTORE dst=$peer"
    ;;
  status)
    echo "RULES=$(sudo iptables-save | grep -c "${COMMENT}" || true)"
    sudo iptables-save | grep "${COMMENT}" || true
    ;;
  *) echo "usage: $0 drop|restore|status [PEER]" >&2; exit 2 ;;
esac
