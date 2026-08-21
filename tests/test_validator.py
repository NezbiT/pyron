import json

from pyron._bridge import SchemaRegistry
from pyron.validation import validate


def test_object_ok_and_missing():
    reg = SchemaRegistry()
    sid = reg.register(
        {
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "price": {"type": "number", "minimum": 0},
            },
            "required": ["title", "price"],
            "additionalProperties": False,
        }
    )
    ok, value = reg.validate(sid, json.dumps({"title": "A", "price": 3}).encode())
    assert ok is True
    assert value["title"] == "A"
    ok, errors = reg.validate(sid, b'{"title": "A"}')
    assert ok is False
    assert any(e["type"] == "missing" for e in errors)


def test_reject_negative_price():
    reg = SchemaRegistry()
    sid = reg.register(
        {
            "type": "object",
            "properties": {"price": {"type": "number", "minimum": 0}},
            "required": ["price"],
        }
    )
    ok, errors = reg.validate(sid, b'{"price": -1}')
    assert ok is False


def test_batch_validate():
    reg = SchemaRegistry()
    sid = reg.register({"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]})
    results = reg.validate_batch(sid, [b'{"n": 1}', b'{}'])
    assert results[0][0] is True
    assert results[1][0] is False


def test_python_validate_helper_raises():
    from pyron.exceptions import ValidationException

    try:
        validate(
            {
                "type": "object",
                "properties": {"title": {"type": "string", "minLength": 2}},
                "required": ["title"],
            },
            {"title": "x"},
        )
        assert False, "expected ValidationException"
    except ValidationException as exc:
        assert exc.status_code == 422
