"""Tests de la session en ligne (étape 1 du backend v2).

Les tests par défaut n'utilisent PAS le réseau. Le test marqué `online` ne tourne que si
STACKTRACE_ONLINE_TESTS=1 (il lit le vrai mainnet via ETH_RPC_URL).
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


@pytest.mark.skipif(os.getenv("STACKTRACE_ONLINE_TESTS") != "1", reason="test réseau (STACKTRACE_ONLINE_TESTS=1)")
def test_open_session_live_mainnet():
    s = sess.open_session()
    assert s.chain_id == 1
    assert s.block > 0 and s.block_timestamp > 0
    # le bloc est figé : un second appel au même bloc vient du cache, pas du réseau
    s.w3.eth.get_balance("0x0000000000000000000000000000000000000000", block_identifier=s.block)
    before = s.network_calls
    s.w3.eth.get_balance("0x0000000000000000000000000000000000000000", block_identifier=s.block)
    assert s.network_calls == before
