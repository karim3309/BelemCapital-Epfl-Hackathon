"""T1/T2 — the disk cache and the cached RPC provider."""
import pytest

from discovery.cache import CacheMissError, DiskCache, cache_key
from discovery.rpc import CachedHTTPProvider, OfflineError, RpcError, _is_pinned


def test_cache_key_is_stable_and_order_independent():
    assert cache_key({"a": 1, "b": [1, 2]}) == cache_key({"b": [1, 2], "a": 1})
    assert cache_key({"a": 1}) != cache_key({"a": 2})


def test_put_then_get_roundtrip(tmp_path):
    c = DiskCache(tmp_path)
    payload = {"method": "eth_call", "params": [{"to": "0x1"}, "0x10"]}
    assert c.get("rpc", payload) is None
    c.put("rpc", payload, {"result": "0xabc"})
    entry = c.get("rpc", payload)
    assert entry["response"] == {"result": "0xabc"}
    assert entry["request"] == payload            # the request is stored: the cache is readable
    assert c.stats.hits == 1 and c.stats.misses == 1 and c.stats.writes == 1
    assert not list(tmp_path.rglob("*.tmp"))       # atomic write: no leftover temporary file


def test_offline_miss_raises(tmp_path):
    with pytest.raises(CacheMissError):
        DiskCache(tmp_path, offline=True).get("rpc", {"method": "eth_call"})


@pytest.mark.parametrize("method,params,pinned", [
    ("eth_chainId", [], True),
    ("eth_call", [{"to": "0x1"}, "0x1a"], True),
    ("eth_call", [{"to": "0x1"}, "latest"], False),
    ("eth_getCode", ["0x1", "0x1a"], True),
    ("eth_blockNumber", [], False),
    ("eth_getBlockByNumber", ["0x1a", False], True),
    ("eth_getBlockByNumber", ["latest", False], False),
])
def test_only_block_pinned_calls_are_cacheable(method, params, pinned):
    assert _is_pinned(method, params) is pinned


class _ScriptedProvider(CachedHTTPProvider):
    """Provider whose "network" returns answers written in advance."""

    def __init__(self, cache, script):
        super().__init__("http://fake.invalid", cache)
        self.script = script
        self.network_calls = 0

    def _network(self, method, params):
        self.network_calls += 1
        return {"jsonrpc": "2.0", "id": 1, **self.script[method]}


def test_provider_caches_pinned_results_and_reverts(tmp_path):
    cache = DiskCache(tmp_path)
    p = _ScriptedProvider(cache, {
        "eth_call": {"result": "0x01"},
        "eth_getCode": {"error": {"code": 3, "message": "execution reverted"}},
    })
    params = [{"to": "0x1"}, "0x10"]
    assert p.make_request("eth_call", params)["result"] == "0x01"
    assert p.make_request("eth_call", params)["result"] == "0x01"
    assert p.network_calls == 1                                   # 2nd call served by the cache
    p.make_request("eth_getCode", ["0x1", "0x10"])
    p.make_request("eth_getCode", ["0x1", "0x10"])
    assert p.network_calls == 2                                   # the revert is cached too


def test_provider_does_not_cache_real_errors(tmp_path):
    p = _ScriptedProvider(DiskCache(tmp_path), {"eth_call": {"error": {"code": -32000, "message": "header not found"}}})
    with pytest.raises(RpcError, match="archive"):
        p.make_request("eth_call", [{"to": "0x1"}, "0x10"])
    assert not list(tmp_path.rglob("*.json"))


def test_offline_forbids_moving_calls(tmp_path):
    p = CachedHTTPProvider(None, DiskCache(tmp_path, offline=True))
    with pytest.raises(OfflineError):
        p.make_request("eth_blockNumber", [])
