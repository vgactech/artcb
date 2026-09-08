#!/usr/bin/env bash
# Real packet impairment on THIS node's default IPv4 iface. Process stays up.
# Usage: apply IFACE "netem ..." | clear IFACE | iface
set -euo pipefail
COMMENT="artcb271-netem"

iface() {
  ip -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}'
}

cmd="${1:-iface}"
dev="${2:-}"
spec="${3:-}"
case "$cmd" in
  iface) iface ;;
  apply)
    [[ -n "$dev" && -n "$spec" ]] || { echo "usage: $0 apply IFACE 'delay 100ms loss 10%'" >&2; exit 2; }
    sudo tc qdisc del dev "$dev" root 2>/dev/null || true
    sudo tc qdisc add dev "$dev" root netem $spec
    echo "NETEM_ON dev=$dev spec=$spec"
    tc qdisc show dev "$dev"
    ;;
  clear)
    [[ -n "$dev" ]] || { echo "usage: $0 clear IFACE" >&2; exit 2; }
    sudo tc qdisc del dev "$dev" root 2>/dev/null || true
    echo "NETEM_OFF dev=$dev"
    tc qdisc show dev "$dev" || true
    ;;
  *) echo "usage: $0 iface|apply|clear" >&2; exit 2 ;;
esac
