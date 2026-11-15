"""Boot the shim against the in-memory FakeSystem (a smoke run, no live backend)."""

from __future__ import annotations

import os

from nil_adapter_template.edge import CapturingEmitter, HttpEventEmitter, create_app, parse_service_key
from nil_adapter_template.system import FakeSystem


def build_demo_app():
    return create_app(FakeSystem(), CapturingEmitter(), bearer=None)


def build_app():
    """Events go to NIL_EVENTS_WEBHOOK, signed v2 with NIL_SERVICE_KEY (kid:secret). A webhook with no
    key stops the boot (EventKeyUnset); the shared events secret signs nothing."""
    webhook = os.environ.get("NIL_EVENTS_WEBHOOK", "")
    emitter = (
        HttpEventEmitter(webhook, service_key=parse_service_key(os.environ.get("NIL_SERVICE_KEY", "")),
                         source="nil-template-adapter")
        if webhook else CapturingEmitter()
    )
    return create_app(FakeSystem(), emitter, bearer=os.environ.get("NIL_BEARER"))


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(build_demo_app(), host="127.0.0.1", port=8099)
