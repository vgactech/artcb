from src.api.ops_routes import peer_restart_message, PEER_RESTART_PROTOCOL

def test_peer_restart_message_stable():
    m = peer_restart_message(from_replica_id="ovh-node-1", ts_ns=1, target_hint="n2.artcb.me")
    assert m.startswith(PEER_RESTART_PROTOCOL)
    assert "ovh-node-1" in m
    assert "n2.artcb.me" in m
