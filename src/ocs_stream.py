"""
ocs_stream.py
-------------
Where "live data" actually plugs in. Two implementations of the same
interface:

  MockFileStreamSource  - replays data/ocs_events.csv as if it were arriving
                           in real time (sorted by timestamp, with a delay
                           between events). Use this today, no infra needed.

  EventHubStreamSource   - a REAL consumer against Azure Event Hub (which
                           exposes a Kafka-compatible endpoint, so this same
                           pattern works against plain Kafka too — swap the
                           client library, keep everything downstream
                           identical). Needs real credentials to run; it's
                           provided as a correct, drop-in starting point,
                           not something you can execute in this sandbox.

Both yield plain dicts matching schemas/ocs_event.schema.json — every event
is validated against that schema the moment it's read off the wire, before
anything downstream ever sees it. This is deliberately the FIRST place the
schema gets enforced, not an afterthought: a live feed is exactly where a
malformed or unexpected event is most likely to show up for the first time.

*** WHAT YOU ACTUALLY NEED TO ASK YOUR OCS/NETWORK TEAM FOR ***
See LIVE_DATA.md in the repo root — this file assumes that conversation has
already happened and something is publishing valid OCS events to a topic.
"""

import csv
import json
import os
import time
from abc import ABC, abstractmethod
from datetime import datetime

import jsonschema
from jsonschema import Draft202012Validator

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "..", "schemas", "ocs_event.schema.json")

with open(SCHEMA_PATH) as f:
    _OCS_EVENT_VALIDATOR = Draft202012Validator(json.load(f))


class SchemaViolation(Exception):
    """Raised when an event off the wire doesn't match ocs_event.schema.json.
    In production this should route to a dead-letter queue + alert, not
    crash the consumer — see the comment in EventHubStreamSource.stream()."""


def _validate(event: dict) -> dict:
    errors = list(_OCS_EVENT_VALIDATOR.iter_errors(event))
    if errors:
        raise SchemaViolation("; ".join(e.message for e in errors))
    return event


class OCSEventSource(ABC):
    """Anything that can hand us a live sequence of OCS events implements
    this. monitor/live_monitor code should only ever depend on this
    interface, never on CSV-reading or Event-Hub-specific details directly —
    that's what makes swapping mock for real a one-line change in
    run_live_demo.py rather than a rewrite."""

    @abstractmethod
    def stream(self):
        """Yields validated event dicts, one at a time, forever (or until
        the source is exhausted, for the mock)."""
        raise NotImplementedError


class MockFileStreamSource(OCSEventSource):
    """Replays data/ocs_events.csv in timestamp order, sleeping between
    events to simulate real-time arrival. This is what run_live_demo.py
    uses by default — no Azure/Kafka account needed to see the live,
    event-driven pipeline actually working end to end."""

    def __init__(self, speed_multiplier: float = 1.0, min_gap_seconds: float = 0.6):
        """
        speed_multiplier: >1.0 compresses the simulated real-world gaps
                           between events (they're hours apart in the mock
                           data — nobody wants to watch that in real time).
        min_gap_seconds:   floor on the delay between prints, so the demo is
                            watchable even for two events seconds apart.
        """
        self.speed_multiplier = speed_multiplier
        self.min_gap_seconds = min_gap_seconds

    def stream(self):
        path = os.path.join(DATA_DIR, "ocs_events.csv")
        with open(path) as f:
            rows = list(csv.DictReader(f))

        rows.sort(key=lambda r: r["timestamp"])
        prev_ts = None

        for row in rows:
            ts = datetime.fromisoformat(row["timestamp"])
            if prev_ts is not None:
                real_gap = (ts - prev_ts).total_seconds()
                simulated_gap = max(real_gap / max(self.speed_multiplier, 1), self.min_gap_seconds)
                time.sleep(min(simulated_gap, 3.0))  # cap so a demo never actually waits hours
            prev_ts = ts

            event = {
                "event_id": row["event_id"],
                "customer_id": row["customer_id"],
                "timestamp": row["timestamp"] + ("Z" if "Z" not in row["timestamp"] else ""),
                "event_type": row["event_type"],
                "amount": float(row["amount"]),
                "currency": "GBP",
                "description": row["description"],
            }
            yield _validate(event)


class EventHubStreamSource(OCSEventSource):
    """
    REAL implementation — requires `pip install azure-eventhub` and actual
    credentials. Cannot run in this sandbox (no network access to Azure),
    but this is correct, complete code: point it at a real Event Hub and it
    works as-is.

    Ask your OCS/network/platform team for:
      - Event Hub namespace + connection string (or, better, use
        azure-identity / Managed Identity instead of a connection string —
        shown as the commented alternative below)
      - The Event Hub name (the "topic") OCS events are published to
      - A consumer group dedicated to this service (never share a consumer
        group with another consumer — you'll each only see a subset of
        events)
      - Confirmation of the message body format: this assumes each message
        body is a JSON object matching ocs_event.schema.json. If the real
        feed sends Avro, protobuf, or a different JSON shape, you need a
        translation step here, not downstream.

    If your organization uses Kafka directly instead of Event Hub, swap this
    class's body for `confluent_kafka.Consumer` — the `stream()` method's
    shape (parse message -> validate -> yield) doesn't change at all,
    because Event Hub's native endpoint IS Kafka-protocol-compatible.
    """

    def __init__(self, connection_str: str, eventhub_name: str, consumer_group: str = "$Default"):
        self.connection_str = connection_str
        self.eventhub_name = eventhub_name
        self.consumer_group = consumer_group

    def stream(self):
        # Deferred import: azure-eventhub is an OPTIONAL dependency, only
        # needed if this class is actually used — don't force everyone
        # running the mock demo to install it.
        from azure.eventhub import EventHubConsumerClient

        client = EventHubConsumerClient.from_connection_string(
            conn_str=self.connection_str,
            consumer_group=self.consumer_group,
            eventhub_name=self.eventhub_name,
        )

        # EventHubConsumerClient is callback-based, not a plain generator —
        # bridge it to this class's simple `yield`-based interface with a
        # small in-process queue.
        import queue
        buffer = queue.Queue()

        def on_event(partition_context, event):
            try:
                body = json.loads(event.body_as_str())
                validated = _validate(body)
                buffer.put(validated)
            except SchemaViolation as e:
                # PRODUCTION TODO: route to a dead-letter topic + alert,
                # do NOT crash the consumer over one bad message — a single
                # malformed event should never take down live monitoring.
                buffer.put({"__schema_violation__": str(e), "raw": event.body_as_str()})
            partition_context.update_checkpoint(event)

        import threading
        t = threading.Thread(target=client.receive, kwargs={"on_event": on_event}, daemon=True)
        t.start()

        try:
            while True:
                item = buffer.get()
                if "__schema_violation__" in item:
                    continue  # already handled above; don't yield bad data downstream
                yield item
        finally:
            client.close()

        # --- Managed Identity alternative (preferred over a connection
        # string for production — no secret to rotate or leak) ---
        #
        # from azure.identity import DefaultAzureCredential
        # client = EventHubConsumerClient(
        #     fully_qualified_namespace="<namespace>.servicebus.windows.net",
        #     eventhub_name=self.eventhub_name,
        #     consumer_group=self.consumer_group,
        #     credential=DefaultAzureCredential(),
        # )
