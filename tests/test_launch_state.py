import threading
import unittest

from common import events
from common.host import launch_state


class LaunchStateTests(unittest.TestCase):
    def setUp(self) -> None:
        launch_state.clear()
        events.clear()
        self.addCleanup(events.clear)
        self.addCleanup(launch_state.clear)

    def test_starts_idle(self) -> None:
        state = launch_state.current()

        self.assertFalse(state.launching)
        self.assertIsNone(state.table_name)

    def test_set_launching_records_the_game(self) -> None:
        launch_state.set_launching("Medieval Madness", source=launch_state.SOURCE_REMOTE)

        state = launch_state.current()
        self.assertTrue(state.launching)
        self.assertEqual(state.table_name, "Medieval Madness")

    def test_the_state_records_who_asked(self) -> None:
        """The frontend has to tell its own launches from everyone else's, and
        every other consumer needs the state to be true either way."""
        launch_state.set_launching("Medieval Madness", source=launch_state.SOURCE_FRONTEND)

        self.assertEqual(launch_state.current().source, "frontend")

    def test_clear_returns_to_idle(self) -> None:
        launch_state.set_launching("Medieval Madness", source=launch_state.SOURCE_REMOTE)

        launch_state.clear()

        self.assertEqual(launch_state.current().as_dict(),
                         {"launching": False, "table_name": None, "source": None})

    def test_clearing_when_idle_is_harmless(self) -> None:
        """The remote page clears in a finally and in an except; both can run."""
        launch_state.clear()
        launch_state.clear()

        self.assertFalse(launch_state.current().launching)

    def test_state_is_immutable_from_the_outside(self) -> None:
        """Readers get a snapshot, not a handle on the live state."""
        launch_state.set_launching("Medieval Madness", source=launch_state.SOURCE_REMOTE)
        snapshot = launch_state.current()

        launch_state.clear()

        self.assertTrue(snapshot.launching, "the snapshot must not change underneath")
        self.assertFalse(launch_state.current().launching)

    def test_concurrent_writes_leave_a_coherent_state(self) -> None:
        """The page writes from a worker thread while the API reads from the loop."""
        errors = []

        def hammer(name):
            try:
                for _ in range(200):
                    launch_state.set_launching(name, source=launch_state.SOURCE_REMOTE)
                    state = launch_state.current()
                    # never a half-written pair: launching implies a name
                    if state.launching and state.table_name is None:
                        errors.append(state)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=hammer, args=(f"Table {i}",)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])


class LaunchStateEventTests(unittest.TestCase):
    """Every change is announced, so a consumer can be told instead of polling."""

    def setUp(self) -> None:
        launch_state.clear()
        events.clear()
        self.addCleanup(events.clear)
        self.addCleanup(launch_state.clear)
        self.seen = []
        events.subscribe(events.PLAY_STATE_CHANGED, lambda **p: self.seen.append(p["state"]))

    def test_a_launch_is_announced(self) -> None:
        launch_state.set_launching("Medieval Madness", source=launch_state.SOURCE_REMOTE)

        self.assertEqual(self.seen, [{"launching": True, "table_name": "Medieval Madness",
                           "source": "remote"}])

    def test_clearing_is_announced(self) -> None:
        launch_state.set_launching("Medieval Madness", source=launch_state.SOURCE_REMOTE)
        launch_state.clear()

        self.assertEqual(self.seen[-1], {"launching": False, "table_name": None, "source": None})

    def test_an_unchanged_state_is_not_announced(self) -> None:
        """The remote page clears in both a finally and an except; both can run."""
        launch_state.clear()
        launch_state.clear()

        self.assertEqual(self.seen, [], "nothing changed, so nothing to say")

    def test_each_event_carries_the_whole_state(self) -> None:
        """A consumer that missed one is still correct after the next."""
        launch_state.set_launching("A", source=launch_state.SOURCE_REMOTE)
        launch_state.set_launching("B", source=launch_state.SOURCE_API)

        self.assertEqual(self.seen[-1],
                         {"launching": True, "table_name": "B", "source": "api"})

    def test_a_handler_may_read_the_state_back(self) -> None:
        """The event goes out after the lock is released, so this cannot deadlock."""
        read_back = []
        events.subscribe(events.PLAY_STATE_CHANGED,
                         lambda **_: read_back.append(launch_state.current().table_name))

        launch_state.set_launching("Medieval Madness", source=launch_state.SOURCE_REMOTE)

        self.assertEqual(read_back, ["Medieval Madness"])

    def test_a_broken_listener_cannot_break_a_launch(self) -> None:
        def explode(**_):
            raise RuntimeError("bad listener")

        events.subscribe(events.PLAY_STATE_CHANGED, explode)

        with self.assertLogs("vpinfe.common.events", level="ERROR"):
            launch_state.set_launching("Medieval Madness", source=launch_state.SOURCE_REMOTE)

        self.assertTrue(launch_state.current().launching)


if __name__ == "__main__":
    unittest.main()
