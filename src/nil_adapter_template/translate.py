"""The translation core: NIL verb args ⇄ your backend's native documents. GENERATED skeleton.

Pure mapping, no I/O — the only module (besides system.py) that knows backend specifics. Fill each
`to_native` / `run` stub. The NIL edge in `edge.py` never changes when you add a verb.

PARKED verbs (deprecated in the standard) are intentionally ABSENT below — the standard says do not
implement them, so the shim cannot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from nil_adapter_template.system import SystemClient

Bilingual = dict[str, str]


@dataclass(frozen=True)
class WriteVerb:
    verb: str
    tier: str
    doctype: str  # native target type (rename per your backend's vocabulary)
    required: tuple[str, ...]
    to_native: Callable[[dict[str, Any]], dict[str, Any]]
    preview: Callable[[dict[str, Any]], Bilingual]
    entity_type: str

    def missing(self, args: dict[str, Any]) -> list[str]:
        return [field for field in self.required if not args.get(field)]


@dataclass(frozen=True)
class QueryVerb:
    verb: str
    run: Callable[[SystemClient, dict[str, Any]], dict[str, Any]]

def _to_native_create_coupon(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.create_coupon'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_create_coupon: build the native doc for commerce.create_coupon")

def _to_native_create_product(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.create_product'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_create_product: build the native doc for commerce.create_product")

def _to_native_delete_product(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.delete_product'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_delete_product: build the native doc for commerce.delete_product")

def _to_native_process_refund(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.process_refund'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_process_refund: build the native doc for commerce.process_refund")

def _to_native_record_fulfillment(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.record_fulfillment'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_record_fulfillment: build the native doc for commerce.record_fulfillment")

def _to_native_record_payment(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.record_payment'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_record_payment: build the native doc for commerce.record_payment")

def _to_native_send_message(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.send_message'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_send_message: build the native doc for commerce.send_message")

def _to_native_update_product(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.update_product'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_update_product: build the native doc for commerce.update_product")

def _to_native_update_product_quantity(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native commerce document for 'commerce.update_product_quantity'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_update_product_quantity: build the native doc for commerce.update_product_quantity")

def _to_native_create_client(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native services document for 'services.create_client'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_create_client: build the native doc for services.create_client")

def _to_native_create_invoice(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native services document for 'services.create_invoice'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_create_invoice: build the native doc for services.create_invoice")

def _to_native_create_payment_link(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native services document for 'services.create_payment_link'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_create_payment_link: build the native doc for services.create_payment_link")

def _to_native_draft_proposal(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native services document for 'services.draft_proposal'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_draft_proposal: build the native doc for services.draft_proposal")

def _to_native_send_followup(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native services document for 'services.send_followup'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_send_followup: build the native doc for services.send_followup")

def _to_native_send_proposal(args: dict[str, Any]) -> dict[str, Any]:
    # TODO: map NIL args -> a native services document for 'services.send_proposal'.
    # Hidden requirements (company, accounts, …) are pre-filled from the manifest — see manifest.py.
    raise NotImplementedError("fill _to_native_send_proposal: build the native doc for services.send_proposal")

def _run_list_clients(client: SystemClient, args: dict[str, Any]) -> dict[str, Any]:
    # TODO: read business truth fresh for 'services.list_clients' via client.list(...).
    raise NotImplementedError("fill _run_list_clients: read-through for services.list_clients")


WRITE_VERBS: dict[str, WriteVerb] = {
    "commerce.create_coupon": WriteVerb(
        verb="commerce.create_coupon",
        tier="MEDIUM",
        doctype="Coupon",  # TODO: your backend's native type
        required=('code', 'discount_type', 'discount_value'),
        to_native=_to_native_create_coupon,
        preview=lambda a: {"en": "commerce.create_coupon", "ar": "commerce.create_coupon"},  # TODO: human preview
        entity_type="create_coupon",
    ),
    "commerce.create_product": WriteVerb(
        verb="commerce.create_product",
        tier="MEDIUM",
        doctype="Product",  # TODO: your backend's native type
        required=('name',),
        to_native=_to_native_create_product,
        preview=lambda a: {"en": "commerce.create_product", "ar": "commerce.create_product"},  # TODO: human preview
        entity_type="create_product",
    ),
    "commerce.delete_product": WriteVerb(
        verb="commerce.delete_product",
        tier="HIGH",
        doctype="Product",  # TODO: your backend's native type
        required=('product_id',),
        to_native=_to_native_delete_product,
        preview=lambda a: {"en": "commerce.delete_product", "ar": "commerce.delete_product"},  # TODO: human preview
        entity_type="delete_product",
    ),
    "commerce.process_refund": WriteVerb(
        verb="commerce.process_refund",
        tier="HIGH",
        doctype="Refund",  # TODO: your backend's native type
        required=('refund_target',),
        to_native=_to_native_process_refund,
        preview=lambda a: {"en": "commerce.process_refund", "ar": "commerce.process_refund"},  # TODO: human preview
        entity_type="process_refund",
    ),
    "commerce.record_fulfillment": WriteVerb(
        verb="commerce.record_fulfillment",
        tier="MEDIUM",
        doctype="Fulfillment",  # TODO: your backend's native type
        required=('order_id', 'event'),
        to_native=_to_native_record_fulfillment,
        preview=lambda a: {"en": "commerce.record_fulfillment", "ar": "commerce.record_fulfillment"},  # TODO: human preview
        entity_type="record_fulfillment",
    ),
    "commerce.record_payment": WriteVerb(
        verb="commerce.record_payment",
        tier="HIGH",
        doctype="Payment",  # TODO: your backend's native type
        required=('order_id', 'event'),
        to_native=_to_native_record_payment,
        preview=lambda a: {"en": "commerce.record_payment", "ar": "commerce.record_payment"},  # TODO: human preview
        entity_type="record_payment",
    ),
    "commerce.send_message": WriteVerb(
        verb="commerce.send_message",
        tier="HIGH",
        doctype="Message",  # TODO: your backend's native type
        required=('phone', 'text'),
        to_native=_to_native_send_message,
        preview=lambda a: {"en": "commerce.send_message", "ar": "commerce.send_message"},  # TODO: human preview
        entity_type="send_message",
    ),
    "commerce.update_product": WriteVerb(
        verb="commerce.update_product",
        tier="MEDIUM",
        doctype="Product",  # TODO: your backend's native type
        required=('product_id', 'updates'),
        to_native=_to_native_update_product,
        preview=lambda a: {"en": "commerce.update_product", "ar": "commerce.update_product"},  # TODO: human preview
        entity_type="update_product",
    ),
    "commerce.update_product_quantity": WriteVerb(
        verb="commerce.update_product_quantity",
        tier="MEDIUM",
        doctype="Product Quantity",  # TODO: your backend's native type
        required=('product_id', 'quantity'),
        to_native=_to_native_update_product_quantity,
        preview=lambda a: {"en": "commerce.update_product_quantity", "ar": "commerce.update_product_quantity"},  # TODO: human preview
        entity_type="update_product_quantity",
    ),
    "services.create_client": WriteVerb(
        verb="services.create_client",
        tier="MEDIUM",
        doctype="Client",  # TODO: your backend's native type
        required=('name', 'phone'),
        to_native=_to_native_create_client,
        preview=lambda a: {"en": "services.create_client", "ar": "services.create_client"},  # TODO: human preview
        entity_type="create_client",
    ),
    "services.create_invoice": WriteVerb(
        verb="services.create_invoice",
        tier="HIGH",
        doctype="Invoice",  # TODO: your backend's native type
        required=('party_id', 'amount', 'currency'),
        to_native=_to_native_create_invoice,
        preview=lambda a: {"en": "services.create_invoice", "ar": "services.create_invoice"},  # TODO: human preview
        entity_type="create_invoice",
    ),
    "services.create_payment_link": WriteVerb(
        verb="services.create_payment_link",
        tier="HIGH",
        doctype="Payment Link",  # TODO: your backend's native type
        required=('invoice_id',),
        to_native=_to_native_create_payment_link,
        preview=lambda a: {"en": "services.create_payment_link", "ar": "services.create_payment_link"},  # TODO: human preview
        entity_type="create_payment_link",
    ),
    "services.draft_proposal": WriteVerb(
        verb="services.draft_proposal",
        tier="MEDIUM",
        doctype="Proposal",  # TODO: your backend's native type
        required=('party_id', 'title', 'amount', 'currency'),
        to_native=_to_native_draft_proposal,
        preview=lambda a: {"en": "services.draft_proposal", "ar": "services.draft_proposal"},  # TODO: human preview
        entity_type="draft_proposal",
    ),
    "services.send_followup": WriteVerb(
        verb="services.send_followup",
        tier="MEDIUM",
        doctype="Followup",  # TODO: your backend's native type
        required=('party_id', 'message'),
        to_native=_to_native_send_followup,
        preview=lambda a: {"en": "services.send_followup", "ar": "services.send_followup"},  # TODO: human preview
        entity_type="send_followup",
    ),
    "services.send_proposal": WriteVerb(
        verb="services.send_proposal",
        tier="MEDIUM",
        doctype="Proposal",  # TODO: your backend's native type
        required=('biz_proposal_id',),
        to_native=_to_native_send_proposal,
        preview=lambda a: {"en": "services.send_proposal", "ar": "services.send_proposal"},  # TODO: human preview
        entity_type="send_proposal",
    ),
}


QUERY_VERBS: dict[str, QueryVerb] = {
    "services.list_clients": QueryVerb(verb="services.list_clients", run=_run_list_clients),
}


# PARKED — do not implement (deprecated in the standard):
#   commerce.update_order_status (GAP-001)


def entity_ref(verb: WriteVerb, created: dict[str, Any]) -> dict[str, Any]:
    name = created.get("name", "")
    slug = verb.doctype.lower().replace(" ", "-")
    return {"type": verb.entity_type, "id": name, "url": f"/{slug}/{name}"}
