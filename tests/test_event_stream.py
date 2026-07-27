"""The SSE event stream: what reaches the network, and what a client is promised.

The frames are driven straight out of `httpapi.events._stream` rather than over
HTTP. The stream never ends by design, so a test that read it through a client
would hang on the first regression instead of failing.
"""

import asyncio
import json
import unittest
from types import SimpleNamespace

from starlette.testclient import TestClient

import httpapi
from common import events
from httpapi import auth
from httpapi import events as event_stream

PLAY_STATE = frozenset({events.PLAY_STATE_CHANGED})


def _fields(frame: str) -> dict:
    """One SSE frame as its fields. A keepalive comment lands under the empty key."""
    parsed = {}
    for line in frame.strip().splitlines():
        key, _, value = line.partition(": ")
        parsed[key] = value
    return parsed


def _payload(frame: str) -> dict:
    return json.loads(_fields(frame)["data"])


class StreamTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        events.clear()
        event_stream.reset()
        event_stream.attach()
        self.addCleanup(events.clear)
        self.addCleanup(event_stream.reset)

    def _open(self, wanted=None, last_event_id=None):
        """A connected client, closed when the test ends."""
        stream = event_stream._stream(wanted, last_event_id)

        async def close():
            await stream.aclose()

        self.addAsyncCleanup(close)
        return stream

    async def _next(self, stream) -> str:
        return await asyncio.wait_for(anext(stream), 2.0)

    async def _hello(self, stream) -> dict:
        await self._next(stream)  # retry:
        return _payload(await self._next(stream))

    async def _settle(self) -> None:
        """Let the loop run the deliveries the publisher scheduled."""
        await asyncio.sleep(0.05)

    async def test_a_client_is_told_the_stream_is_open_and_where_it_starts(self) -> None:
        stream = self._open()

        retry = await self._next(stream)
        hello = await self._next(stream)

        self.assertEqual(_fields(retry), {"retry": "3000"})
        self.assertEqual(_fields(hello)["event"], event_stream.HELLO_EVENT)
        self.assertFalse(_payload(hello)["resumed"])
        self.assertNotIn("id", _fields(hello), "hello is not a resume point")

    async def test_a_new_client_is_given_the_current_state(self) -> None:
        """Otherwise a client connecting mid-launch sees nothing until it ends."""
        event_stream.declare_snapshot(
            events.PLAY_STATE_CHANGED,
            lambda: {"state": {"launching": True, "table_name": "Medieval Madness"}})
        stream = self._open()
        await self._hello(stream)

        snapshot = await self._next(stream)

        self.assertEqual(_fields(snapshot)["event"], events.PLAY_STATE_CHANGED)
        self.assertEqual(_payload(snapshot)["state"]["table_name"], "Medieval Madness")
        self.assertNotIn("id", _fields(snapshot), "a snapshot is not a resume point")

    async def test_a_published_event_reaches_a_connected_client(self) -> None:
        stream = self._open()
        await self._hello(stream)

        events.emit(events.PLAY_STATE_CHANGED, state={"launching": True, "table_name": "Taxi"})
        frame = await self._next(stream)

        self.assertEqual(_fields(frame)["event"], events.PLAY_STATE_CHANGED)
        self.assertEqual(_fields(frame)["id"], "1")
        self.assertEqual(_payload(frame), {"state": {"launching": True, "table_name": "Taxi"}})

    async def test_an_event_published_on_another_thread_reaches_the_client(self) -> None:
        """The bus runs handlers on whoever published, which is never this loop."""
        stream = self._open()
        await self._hello(stream)

        await asyncio.to_thread(events.emit, events.PLAY_STATE_CHANGED,
                                state={"launching": False, "table_name": None})
        frame = await self._next(stream)

        self.assertEqual(_payload(frame), {"state": {"launching": False, "table_name": None}})

    async def test_a_table_event_carries_identity_not_the_table(self) -> None:
        """The bus payload is in-process; the Table object and the ini config are not
        things to put on a socket."""
        table = SimpleNamespace(
            tableDirName="Medieval Madness (Williams 1997)",
            metaConfig={"VPinFE": {"id": "6f1c9a4e"}},
        )
        stream = self._open()
        await self._hello(stream)

        events.emit(events.TABLE_SELECTED, table=table, ini_config="secret-ini-config")
        frame = await self._next(stream)

        self.assertEqual(_payload(frame), {
            "table": {
                "id": "6f1c9a4e",
                "name": "Medieval Madness (Williams 1997)",
                # A pointer to the table, not a second answer to what a table is.
                "links": {"self": "/api/v1/tables/6f1c9a4e"},
            },
        })
        self.assertNotIn("secret-ini-config", frame)

    async def test_a_table_with_no_id_yet_is_referenced_without_a_broken_link(self) -> None:
        """Ids are minted on a write path, so a scan can hand us a table without one."""
        stream = self._open()
        await self._hello(stream)

        events.emit(events.TABLE_SELECTED,
                    table=SimpleNamespace(tableDirName="Unidentified", metaConfig={}),
                    ini_config=None)
        frame = await self._next(stream)

        self.assertEqual(_payload(frame)["table"],
                         {"id": "", "name": "Unidentified"})

    async def test_a_table_event_without_a_table_still_streams(self) -> None:
        """The Remote Control page launches without one."""
        stream = self._open()
        await self._hello(stream)

        events.emit(events.TABLE_LAUNCHING, table=None, ini_config="cfg")
        frame = await self._next(stream)

        self.assertEqual(_payload(frame), {"table": None})

    async def test_a_job_event_keeps_the_documented_shape(self) -> None:
        """The shape is a contract, so a caller's extra keyword does not become one."""
        stream = self._open()
        await self._hello(stream)

        events.emit(events.JOB_PROGRESS, job_id="import-7", pct=42, message="Copying",
                    internal_handle=object())
        frame = await self._next(stream)

        self.assertEqual(_payload(frame),
                         {"job_id": "import-7", "pct": 42, "message": "Copying"})

    async def test_a_filter_delivers_only_what_it_names(self) -> None:
        stream = self._open(PLAY_STATE)
        await self._hello(stream)

        events.emit(events.TABLE_SELECTED, table=None, ini_config=None)
        events.emit(events.PLAY_STATE_CHANGED, state={"launching": True, "table_name": "Taxi"})
        frame = await self._next(stream)

        self.assertEqual(_fields(frame)["event"], events.PLAY_STATE_CHANGED)

    async def test_a_reconnect_replays_what_it_missed(self) -> None:
        events.emit(events.PLAY_STATE_CHANGED, state={"launching": True, "table_name": "Taxi"})
        events.emit(events.PLAY_STATE_CHANGED, state={"launching": False, "table_name": None})

        stream = self._open(last_event_id="1")
        hello = await self._hello(stream)
        frame = await self._next(stream)

        self.assertTrue(hello["resumed"])
        self.assertEqual(_fields(frame)["id"], "2")
        self.assertEqual(_payload(frame)["state"], {"launching": False, "table_name": None})

    async def test_a_resumed_client_is_not_sent_a_snapshot(self) -> None:
        """It already holds the state; replaying the gap is the whole answer."""
        event_stream.declare_snapshot(events.PLAY_STATE_CHANGED, lambda: {"state": {}})
        events.emit(events.PLAY_STATE_CHANGED, state={"launching": True, "table_name": "Taxi"})

        stream = self._open(last_event_id="1")
        hello = await self._hello(stream)

        self.assertTrue(hello["resumed"])
        with self.assertRaises(TimeoutError):
            await asyncio.wait_for(anext(stream), 0.2)

    async def test_a_resume_point_beyond_the_history_is_reported_as_a_gap(self) -> None:
        """A client resuming against a restarted instance has to know to resync."""
        events.emit(events.PLAY_STATE_CHANGED, state={"launching": True, "table_name": "Taxi"})

        hello = await self._hello(self._open(last_event_id="99"))

        self.assertFalse(hello["resumed"])

    async def test_an_unreadable_resume_point_is_treated_as_a_fresh_connection(self) -> None:
        hello = await self._hello(self._open(last_event_id="not-a-number"))

        self.assertFalse(hello["resumed"])

    async def test_a_payload_that_will_not_serialize_does_not_reach_the_bus_caller(self) -> None:
        """Publishing must not fail because something downstream speaks JSON."""
        stream = self._open()
        await self._hello(stream)

        with self.assertLogs("vpinfe.httpapi.events", level="ERROR"):
            events.emit(events.PLAY_STATE_CHANGED, state=object())

        events.emit(events.PLAY_STATE_CHANGED, state={"launching": True, "table_name": "Taxi"})
        frame = await self._next(stream)
        self.assertEqual(_fields(frame)["id"], "1", "the dropped event consumed no id")

    async def test_a_client_that_cannot_keep_up_is_dropped(self) -> None:
        """A subscriber must never be able to slow a publisher down."""
        stream = self._open(PLAY_STATE)
        await self._hello(stream)

        overrun = event_stream.QUEUE_LIMIT + 5
        for index in range(overrun):
            events.emit(events.PLAY_STATE_CHANGED,
                        state={"launching": True, "table_name": str(index)})
        await self._settle()

        delivered = []
        with self.assertLogs("vpinfe.httpapi.events", level="WARNING"):
            while True:
                try:
                    delivered.append(await self._next(stream))
                except StopAsyncIteration:
                    break

        self.assertEqual(len(delivered), event_stream.QUEUE_LIMIT,
                         "everything queued before the overrun is still delivered")

    async def test_a_closed_client_stops_receiving(self) -> None:
        stream = self._open(PLAY_STATE)
        await self._hello(stream)
        await stream.aclose()

        events.emit(events.PLAY_STATE_CHANGED, state={"launching": True, "table_name": "Taxi"})
        await self._settle()

        self.assertEqual(event_stream._streams, [])


class BusRegistrationTests(unittest.TestCase):
    def setUp(self) -> None:
        events.clear()
        event_stream.reset()
        self.addCleanup(events.clear)
        self.addCleanup(event_stream.reset)

    def test_the_stream_subscribes_and_never_hooks(self) -> None:
        """A hook can stop a launch. Nobody on the far end of a socket may do that."""
        event_stream.attach()

        for name in event_stream.STREAMED_EVENTS:
            with self.subTest(event=name):
                self.assertEqual(events.registered(name), (0, 1))

    def test_attaching_twice_leaves_one_subscription(self) -> None:
        event_stream.attach()
        event_stream.attach()

        self.assertEqual(events.registered(events.PLAY_STATE_CHANGED), (0, 1))

    def test_history_is_kept_bounded(self) -> None:
        event_stream.attach()

        for index in range(event_stream.HISTORY_LIMIT + 10):
            events.emit(events.JOB_PROGRESS, job_id="j", pct=index, message="")

        self.assertEqual(len(event_stream._history), event_stream.HISTORY_LIMIT)


class EndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = httpapi.create_api_app()
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.addCleanup(events.clear)
        self.addCleanup(event_stream.reset)

    def test_the_route_declares_the_subscribe_scope(self) -> None:
        scopes = {path: auth.route_scope(route)
                  for path, route in auth.iter_api_routes(self.app)}

        self.assertEqual(scopes["/events"], "events:subscribe")

    def test_an_unknown_event_name_is_rejected_in_the_envelope(self) -> None:
        response = self.client.get("/events?events=play.state_changed,table.exploded")
        error = response.json()["error"]

        self.assertEqual(response.status_code, 400)
        self.assertEqual(error["code"], "invalid_request")
        self.assertEqual(error["details"]["unknown"], ["table.exploded"])

    def test_discovery_links_to_the_stream(self) -> None:
        self.assertEqual(self.client.get("/").json()["links"]["events"], "/api/v1/events")

    def test_discovery_declares_the_stream_in_both_roles(self) -> None:
        """It carries library events and launch events alike."""
        declared = {c["name"]: c for c in self.client.get("/").json()["capabilities"]}

        self.assertEqual(declared["events"]["residency"], ["catalog", "play_host"])

    def test_building_the_app_declares_the_play_state_snapshot(self) -> None:
        """A theme subscribing mid-launch has to be told there is one."""
        self.assertIn(events.PLAY_STATE_CHANGED, event_stream._snapshots)


if __name__ == "__main__":
    unittest.main()
