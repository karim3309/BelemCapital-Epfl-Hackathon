"""Tests of the online session (step 1 of backend v2).

The default tests do NOT use the network. The test marked `online` only runs if
STACKTRACE_ONLINE_TESTS=1 (it reads the real mainnet via ETH_RPC_URL).
"""
import os

import pytest

from stacktrace import session as sess


def test_mask_url_never_leaks_the_key():
    url = "https://abc-def-123.rpc-provider.example/SECRETKEY123456/"
    masked = sess.mask_url(url)
    assert "SECRET" not in masked
    assert masked.startswith("abc-") and masked.endswith(".example")


def test_mask_url_empty():
    assert sess.mask_url(None) == "—"


def test_open_session_without_rpc_url_explains_what_to_do(monkeypatch):
    real = sess.load_config

    def no_url(**kw):
        cfg = real(**kw)
        cfg.rpc_url = None
        return cfg

    monkeypatch.setattr(sess, "load_config", no_url)
    with pytest.raises(sess.SessionError, match=r"\.env"):
        sess.open_session()


@pytest.mark.skipif(os.getenv("STACKTRACE_ONLINE_TESTS") != "1", reason="network test (STACKTRACE_ONLINE_TESTS=1)")
def test_open_session_live_mainnet():
    s = sess.open_session()
    assert s.chain_id == 1
    assert s.block > 0 and s.block_timestamp > 0
    # the block is pinned: a second call at the same block comes from the cache, not the network
    s.w3.eth.get_balance("0x0000000000000000000000000000000000000000", block_identifier=s.block)
    before = s.network_calls
    s.w3.eth.get_balance("0x0000000000000000000000000000000000000000", block_identifier=s.block)
    assert s.network_calls == before


def test_redact_hides_the_key_in_every_shape_of_error_message():
    from discovery.rpc import redact
    full = "429 Client Error: Too Many Requests for url: https://abc.rpc-provider.example/SECRETKEY123/"
    bare = "HTTPSConnectionPool(host='abc.rpc-provider.example', port=443): Max retries exceeded with url: /SECRETKEY123/ (Caused by x)"
    for msg in (full, bare):
        out = redact(msg)
        assert "SECRETKEY" not in out and "abc.rpc-provider.example" in out
