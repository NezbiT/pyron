from pyron._bridge import dumps, dumps_batch, loads, loads_batch


def test_roundtrip_object():
    payload = {"ok": True, "n": 3, "items": ["a", "b"]}
    raw = dumps(payload)
    assert isinstance(raw, (bytes, bytearray))
    assert loads(raw) == payload


def test_loads_str():
    assert loads('{"a": 1}')["a"] == 1


def test_batch():
    blobs = dumps_batch([{"i": 1}, {"i": 2}])
    out = loads_batch(blobs)
    assert [x["i"] for x in out] == [1, 2]


def test_null():
    assert loads(dumps(None)) is None
