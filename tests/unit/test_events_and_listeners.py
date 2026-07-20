"""Event bus isolation + the three listeners (logging, metrics, alerts)."""

from components.listeners.alert_listener import AlertListener
from components.listeners.metrics_listener import MetricsListener
from core.events.bus import EventBus
from core.events.types import (
    BLOCK_DETECTED,
    RECORD_EXTRACTED,
    RECORD_SAVED,
    STAGE_COMPLETED,
    VALIDATION_FAILED,
    Event,
)


class TestEventBusIsolation:
    def test_sync_listener_receives_events(self):
        bus = EventBus()
        seen = []
        bus.subscribe("*", lambda e: seen.append(e.type))
        bus.publish(Event("job.started"))
        assert seen == ["job.started"]

    def test_type_specific_subscription(self):
        bus = EventBus()
        seen = []
        bus.subscribe(BLOCK_DETECTED, lambda e: seen.append(e.type))
        bus.publish(Event("job.started"))
        bus.publish(Event(BLOCK_DETECTED))
        assert seen == [BLOCK_DETECTED]

    def test_crashing_listener_is_isolated_and_counted(self):
        bus = EventBus()
        good = []

        def bad(event):
            raise RuntimeError("listener bug")

        bus.subscribe("*", bad)
        bus.subscribe("*", lambda e: good.append(e.type))
        bus.publish(Event("job.started"))  # must not raise
        assert good == ["job.started"]  # the good listener still ran
        assert bus.listener_errors == 1

    async def test_async_listener_scheduled_and_drained(self):
        bus = EventBus()
        seen = []

        async def async_listener(event):
            seen.append(event.type)

        bus.subscribe("*", async_listener)
        bus.publish(Event("job.started"))
        await bus.drain()
        assert seen == ["job.started"]

    async def test_crashing_async_listener_isolated(self):
        bus = EventBus()

        async def bad(event):
            raise RuntimeError("async bug")

        bus.subscribe("*", bad)
        bus.publish(Event("job.started"))
        await bus.drain()
        assert bus.listener_errors == 1


class TestMetricsListener:
    def test_counts_records_blocks_and_validation_fields(self):
        m = MetricsListener()
        m(Event(RECORD_EXTRACTED, {"plugin": "shop"}))
        m(Event(RECORD_SAVED, {"plugin": "shop"}))
        m(Event(BLOCK_DETECTED, {"plugin": "shop"}))
        m(Event(STAGE_COMPLETED, {"plugin": "shop", "stage": "fetch"}))
        m(Event(VALIDATION_FAILED, {"plugin": "shop", "fields": ["price", "title"]}))
        assert m.value(m.records_extracted, plugin="shop") == 1
        assert m.value(m.records_saved, plugin="shop") == 1
        assert m.value(m.blocks, plugin="shop") == 1
        assert m.value(m.fetches, plugin="shop") == 1
        assert m.value(m.validation_failures, plugin="shop", field="price") == 1
        assert m.value(m.validation_failures, plugin="shop", field="title") == 1


class TestAlertListener:
    def test_block_rate_spike_fires_once(self):
        sent = []
        alert = AlertListener(sent.append, block_threshold=3)
        for _ in range(5):
            alert(Event(BLOCK_DETECTED, {"plugin": "shop"}))
        assert len(sent) == 1  # fires once when threshold crossed, not repeatedly
        assert "block-rate spike for shop" in sent[0]

    def test_validation_spike_fires(self):
        sent = []
        alert = AlertListener(sent.append, validation_threshold=4)
        alert(Event(VALIDATION_FAILED, {"plugin": "shop", "fields": ["a", "b", "c"]}))
        alert(Event(VALIDATION_FAILED, {"plugin": "shop", "fields": ["d", "e"]}))
        assert len(sent) == 1
        assert "validation-failure spike" in sent[0]

    def test_below_threshold_stays_quiet(self):
        sent = []
        alert = AlertListener(sent.append, block_threshold=10)
        for _ in range(3):
            alert(Event(BLOCK_DETECTED, {"plugin": "shop"}))
        assert sent == []
