"""TEMPLATE-EVENTS-V2: every event the template sends is signed v2 with its own service key, or not sent."""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx
import pytest

from nil_adapter_template import run
from nil_adapter_template.edge import EventKeyUnset, HttpEventEmitter, parse_service_key

ENV = {"nil": "0.1", "id": "e1", "performative": "EVENT", "workspace": "ws_a", "body": {"event": "x"}}
VECTOR = {  # pinned by the control plane (service_keys.EVENT_V2_TEST_VECTOR)
    "secret": "0123456789abcdef0123456789abcdef",
    "body": b'{"workspace":"ws_a","body":{"event":"test.vector"}}',
    "ts": 1761350400,
    "nonce": "nonce-example_0001",
    "signature": "3ec18d50368eb3adbab4fc31765245ce2db4ef4e9c70fb2ce456da80fbf8f577",
}


def _capture(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    sent: list[dict[str, Any]] = []
    monkeypatch.setattr(httpx, "post", lambda url, **kw: sent.append({"url": url, **kw}))
    return sent


def test_sent_event_carries_v2_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture(monkeypatch)
    HttpEventEmitter("http://cp/events/ingest", service_key=("kid-1", "s3cret"), source="t").emit(ENV, 7)
    h = sent[0]["headers"]
    assert h["X-NIL-Signature"].startswith("v2=")
    assert h["X-NIL-Key-Id"] == "kid-1" and h["X-NIL-Sequence"] == "7"
    assert h["X-NIL-Timestamp"].isdigit() and len(h["X-NIL-Nonce"]) >= 16


def test_v2_signature_matches_independent_recomputation(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture(monkeypatch)
    HttpEventEmitter("http://cp", service_key=("kid-1", "s3cret"), source="t").emit(ENV, 1)
    h, body = sent[0]["headers"], sent[0]["content"]
    msg = b"nil.event.v2\n" + h["X-NIL-Timestamp"].encode() + b"\n" + h["X-NIL-Nonce"].encode() \
        + b"\n" + hashlib.sha256(body).hexdigest().encode()
    assert h["X-NIL-Signature"] == "v2=" + hmac.new(b"s3cret", msg, hashlib.sha256).hexdigest()


def test_sign_v2_matches_the_control_plane_pinned_vector() -> None:
    v = VECTOR
    assert HttpEventEmitter.sign_v2(v["secret"], v["body"], v["ts"], v["nonce"]) == v["signature"]


@pytest.mark.parametrize("key", [None, ("", ""), ("kid", ""), ("", "s")])
def test_no_key_nothing_sent_named_refusal(monkeypatch: pytest.MonkeyPatch, key: Any) -> None:
    sent = _capture(monkeypatch)
    with pytest.raises(EventKeyUnset, match="EVENT_KEY_UNSET"):
        HttpEventEmitter("http://cp", service_key=key, source="t").emit(ENV, 1)
    assert sent == []


def test_planted_shared_only_configuration_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    sent = _capture(monkeypatch)
    monkeypatch.setenv("NIL_EVENTS_WEBHOOK", "http://cp/events/ingest")
    monkeypatch.setenv("NIL_EVENTS_SECRET", "shared")
    monkeypatch.delenv("NIL_SERVICE_KEY", raising=False)
    with pytest.raises(EventKeyUnset):
        run.build_app()
    assert sent == []
    with pytest.raises(TypeError):
        HttpEventEmitter("http://cp", "shared")  # type: ignore[call-arg]  # no positional secret path


def test_parse_service_key() -> None:
    assert parse_service_key("k:abc") == ("k", "abc")
    with pytest.raises(EventKeyUnset):
        parse_service_key("nocolon")
