"""Build and acknowledge signed Host Agent fact batches without order semantics."""
from __future__ import annotations

from typing import Any, Mapping

from .coordinator_fact_auth import build_signed_fact_envelope
from .coordinator_outbox import LocalOutbox, OutboxError
from .host_fact_identity import HostFactCredential


class FactDeliveryError(RuntimeError):
    pass


def build_pending_envelope(
    outbox: LocalOutbox,
    credential: HostFactCredential,
    *,
    now_epoch: float | None = None,
    ttl_seconds: float = 60.0,
    limit: int = 100,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    """Return one signed batch and its immutable event ID list.

    The caller may send this envelope over HTTPS. This function itself has no
    network, QMT, Redis, lease, or order dependency.
    """
    pending = outbox.pending(limit=limit)
    if not pending:
        return None, ()
    event_ids = tuple(str(item["event_id"]) for item in pending)
    envelope = build_signed_fact_envelope(
        credential.host_id, credential.key_id, credential.secret,
        {"events": pending}, now_epoch=now_epoch, ttl_seconds=ttl_seconds,
    )
    return envelope, event_ids


def acknowledge_fact_batch(outbox: LocalOutbox, sent_event_ids: tuple[str, ...], response: Mapping[str, Any]) -> int:
    """ACK only IDs explicitly accepted, or a safely replayed exact batch."""
    sent = tuple(dict.fromkeys(str(item) for item in sent_event_ids if str(item)))
    status = str(response.get("status") or "").upper()
    if status == "REPLAYED":
        # A replayed request means the Coordinator already committed this
        # exact request. The caller must provide the original batch IDs.
        return outbox.acknowledge(sent)
    if status != "ACCEPTED":
        return 0
    accepted = {str(item) for item in (response.get("accepted") or [])}
    duplicates = {str(item) for item in (response.get("duplicates") or [])}
    acknowledged = accepted | duplicates
    if not acknowledged.issubset(set(sent)):
        raise FactDeliveryError("Coordinator acknowledged an event not in this batch")
    return outbox.acknowledge(acknowledged)
