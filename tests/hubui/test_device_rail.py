"""How the devices rail is grouped and ordered.

Both are pure, and both decide what somebody reads about machines they may not be
standing next to - which is where a wrong order is hardest to notice.
"""

import unittest

from hubui import devices

CAB = {"device_id": "a", "display_name": "basement cab", "kind": "vpinfe",
       "last_reachable": "2026-09-03T10:00:00Z"}
DESK = {"device_id": "b", "display_name": "Desktop", "kind": "vpinfe",
        "last_reachable": "2026-09-03T12:00:00Z"}
PHONE = {"device_id": "c", "display_name": "iPhone", "kind": "vpx_mobile",
         "last_reachable": "2026-09-01T09:00:00Z"}
NEVER = {"device_id": "d", "display_name": "aaa never", "kind": "vpinfe",
         "last_reachable": ""}


def _names(devices_):
    return [devices.device_label(d) for d in devices_]


class SortTests(unittest.TestCase):
    def test_by_name_is_a_to_z_and_case_does_not_split_it(self) -> None:
        out = devices.sorted_devices([DESK, CAB], "name")

        self.assertEqual(_names(out), ["basement cab", "Desktop"])

    def test_by_last_seen_is_newest_first(self) -> None:
        """The interesting end of that list is what is still out there."""
        out = devices.sorted_devices([CAB, DESK], "last_seen")

        self.assertEqual(_names(out), ["Desktop", "basement cab"])

    def test_a_device_never_seen_sorts_last_not_first(self) -> None:
        """An empty timestamp is the smallest string there is, so the naive sort leads
        with the one thing nobody has heard from."""
        out = devices.sorted_devices([NEVER, CAB], "last_seen")

        self.assertEqual(_names(out), ["basement cab", "aaa never"])

    def test_by_name_still_includes_one_never_seen(self) -> None:
        out = devices.sorted_devices([CAB, NEVER], "name")

        self.assertEqual(_names(out), ["aaa never", "basement cab"])


class GroupTests(unittest.TestCase):
    def test_kinds_are_separate_groups_in_a_fixed_order(self) -> None:
        """So the groups do not move about as devices come and go."""
        groups = devices.grouped_devices([PHONE, CAB], "name")

        self.assertEqual([kind for kind, _h, _d in groups], ["vpinfe", "vpx_mobile"])

    def test_a_group_with_nothing_in_it_is_not_drawn(self) -> None:
        """A heading over nothing says the hub is missing something."""
        groups = devices.grouped_devices([CAB], "name")

        self.assertEqual(len(groups), 1)

    def test_the_sort_applies_inside_each_group(self) -> None:
        groups = devices.grouped_devices([DESK, CAB, PHONE], "name")

        held = {kind: _names(devices_) for kind, _h, devices_ in groups}
        self.assertEqual(held["vpinfe"], ["basement cab", "Desktop"])
        self.assertEqual(held["vpx_mobile"], ["iPhone"])

    def test_an_entry_with_no_kind_is_an_install(self) -> None:
        """Every device that could announce itself before kind existed was one."""
        groups = devices.grouped_devices([{"device_id": "x", "display_name": "old"}],
                                         "name")

        self.assertEqual(groups[0][0], "vpinfe")

    def test_every_sort_the_control_offers_is_one_the_sorter_knows(self) -> None:
        """An unknown key silently falls through to the default, which is a control that
        does nothing and says nothing."""
        for key, _label in devices.SORTS:
            out = devices.sorted_devices([DESK, CAB], key)
            self.assertEqual(len(out), 2, key)
        self.assertIn(devices.DEFAULT_SORT, {key for key, _ in devices.SORTS})


if __name__ == "__main__":
    unittest.main()
