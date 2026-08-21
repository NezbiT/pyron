from pyron._bridge import Router


def test_static_beats_param():
    r = Router()
    r.add("GET", "/users/me", 1)
    r.add("GET", "/users/{id}", 2)
    rid, params = r.find("GET", "/users/me")
    assert rid == 1
    rid, params = r.find("GET", "/users/9")
    assert rid == 2
    assert params["id"] == "9"


def test_catchall():
    r = Router()
    r.add("GET", "/files/{*path}", 7)
    rid, params = r.find("GET", "/files/a/b.txt")
    assert rid == 7
    assert params["path"] == "a/b.txt"


def test_method_not_allowed():
    r = Router()
    r.add("GET", "/only", 1)
    found = r.find("POST", "/only")
    assert found is not None
    assert found[0] is None
    assert "GET" in found[1]


def test_not_found():
    r = Router()
    r.add("GET", "/x", 1)
    assert r.find("GET", "/nope") is None


def test_head_falls_back_to_get():
    r = Router()
    r.add("GET", "/page", 4)
    rid, _ = r.find("HEAD", "/page")
    assert rid == 4


def test_batch():
    r = Router()
    r.add("GET", "/a", 1)
    r.add("POST", "/b", 2)
    out = r.find_batch([("GET", "/a"), ("POST", "/b"), ("GET", "/missing")])
    assert out[0][0] == 1
    assert out[1][0] == 2
    assert out[2] is None


def test_duplicate_raises():
    r = Router()
    r.add("GET", "/x", 1)
    try:
        r.add("GET", "/x", 2)
        raised = False
    except (ValueError, Exception):
        raised = True
    assert raised
