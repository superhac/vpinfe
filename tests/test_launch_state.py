import threading
import unittest

from common import launch_state


class LaunchStateTests(unittest.TestCase):
    def setUp(self) -> None:
        launch_state.clear()
        self.addCleanup(launch_state.clear)

    def test_starts_idle(self) -> None:
        state = launch_state.current()

        self.assertFalse(state.launching)
        self.assertIsNone(state.table_name)

    def test_set_launching_records_the_table(self) -> None:
        launch_state.set_launching("Medieval Madness")

        state = launch_state.current()
        self.assertTrue(state.launching)
        self.assertEqual(state.table_name, "Medieval Madness")

    def test_clear_returns_to_idle(self) -> None:
        launch_state.set_launching("Medieval Madness")

        launch_state.clear()

        self.assertEqual(launch_state.current().as_dict(),
                         {"launching": False, "table_name": None})

    def test_clearing_when_idle_is_harmless(self) -> None:
        """The remote page clears in a finally and in an except; both can run."""
        launch_state.clear()
        launch_state.clear()

        self.assertFalse(launch_state.current().launching)

    def test_state_is_immutable_from_the_outside(self) -> None:
        """Readers get a snapshot, not a handle on the live state."""
        launch_state.set_launching("Medieval Madness")
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
                    launch_state.set_launching(name)
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


if __name__ == "__main__":
    unittest.main()
