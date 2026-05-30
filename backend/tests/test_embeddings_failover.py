"""Embeddings should fail over to the next key on a quota error."""
from types import SimpleNamespace

import pytest

import app.embeddings as emb
from app.keyring import KeyRing


class _FakeEmbedding:
    def __init__(self, dim):
        self.values = [0.1] * dim


def _make_client(behaviour):
    """behaviour() is called per request: may raise or return a response."""
    def embed_content(model, contents, config):
        behaviour()
        return SimpleNamespace(
            embeddings=[_FakeEmbedding(config.output_dimensionality) for _ in contents]
        )

    return SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))


def test_failover_to_second_key_on_quota(monkeypatch):
    # two keys; first always 429s, second works
    monkeypatch.setattr(emb, "keyring", KeyRing(["bad", "good"]))

    calls = {"bad": 0, "good": 0}

    def client_for(key):
        if key == "bad":
            return _make_client(lambda: (calls.__setitem__("bad", calls["bad"] + 1), _raise_quota())[1])
        return _make_client(lambda: calls.__setitem__("good", calls["good"] + 1))

    monkeypatch.setattr(emb, "_client_for", client_for)

    vecs = emb.embed_documents(["hello world"])
    assert len(vecs) == 1
    assert len(vecs[0]) == emb.settings.embed_dim
    assert calls["bad"] == 1 and calls["good"] == 1  # tried bad, fell over to good


def test_raises_when_all_keys_quota(monkeypatch):
    monkeypatch.setattr(emb, "keyring", KeyRing(["bad1", "bad2"]))
    monkeypatch.setattr(emb, "_client_for", lambda key: _make_client(_raise_quota))
    with pytest.raises(RuntimeError, match="exhausted"):
        emb.embed_documents(["x"])


def _raise_quota():
    raise Exception("429 RESOURCE_EXHAUSTED: quota")
