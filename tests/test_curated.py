"""T9 — the curated layer: strict about evidence, otherwise it refuses to load."""
import pytest
import yaml

from discovery.adapters.curated import CuratedError, load_curated
from discovery.config import REPO_ROOT
from tests.fakes import addr


def test_real_curated_file_loads():
    c = load_curated(REPO_ROOT / "curated.yaml")
    assert {"ethena_labs", "circle", "pendle", "morpho", "chainlink"} <= set(c.entities)
    assert all(e["evidence_url"].startswith("https://") for e in c.entities.values())
    assert c.relations, "Ethena's off-chain relations must be present"


def _write(tmp_path, data):
    p = tmp_path / "curated.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


BASE = {"key": "acme", "type": "issuer", "label": "Acme", "evidence_url": "https://acme.example", "as_of": "2026-10-10"}


@pytest.mark.parametrize("entity,needle", [
    ({**BASE, "evidence_url": ""}, "evidence_url"),
    ({**BASE, "evidence_url": "http://insecure.example"}, "evidence_url"),
    ({**BASE, "as_of": "yesterday"}, "as_of"),
    ({**BASE, "type": "asset"}, "type"),
    ({**BASE, "key": "Acme Corp"}, "snake_case"),
])
def test_entity_without_proper_evidence_is_refused(tmp_path, entity, needle):
    with pytest.raises(CuratedError, match=needle):
        load_curated(_write(tmp_path, {"entities": [entity]}))


def test_known_contract_must_reference_existing_issuer(tmp_path):
    data = {"entities": [BASE], "known_contracts": [
        {"address": addr(1), "issuer": "ghost", "match": "address", "evidence_url": "https://x.example", "as_of": "2026-10-10"}]}
    with pytest.raises(CuratedError, match="issuer"):
        load_curated(_write(tmp_path, data))


def test_issuer_edge_by_address_and_by_factory(tmp_path):
    data = {"entities": [BASE], "known_contracts": [
        {"address": addr(1), "issuer": "acme", "match": "address", "role": "Token A",
         "evidence_url": "https://acme.example/a", "as_of": "2026-10-10"},
        {"address": addr(2), "issuer": "acme", "match": "factory", "role": "Factory B",
         "evidence_url": "https://acme.example/b", "as_of": "2026-10-10"}]}
    c = load_curated(_write(tmp_path, data))
    e1 = c.issuer_edge("k1", addr(1), None, 100, "TokenA")
    assert e1.to_key == "issuer:acme" and e1.source == "curated" and "https://acme.example/a" in e1.evidence
    e2 = c.issuer_edge("k2", addr(3), addr(2), 100, "PT")
    assert e2 is not None and "factory()" in e2.evidence and "#100" in e2.evidence
    assert c.issuer_edge("k3", addr(4), None, 100, "X") is None      # unknown → no invented edge
