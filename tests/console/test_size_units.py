"""The three `_size` helpers, pinned at the unit boundaries."""

import unittest

from console.import_dialog import _size as import_size
from console.mediasource import _size as source_size
from console.metrics import _size as metrics_size

KB, MB, GB, TB = 1024, 1024**2, 1024**3, 1024**4


class SizeUnitTests(unittest.TestCase):
    def test_import_dialog_tops_out_at_gb(self) -> None:
        for count, said in ((0, "0 B"), (1023, "1023 B"), (KB, "1.0 KB"),
                            (MB, "1.0 MB"), (GB, "1.0 GB"), (TB, "1024.0 GB"),
                            (10**21, "931322574615.5 GB")):
            self.assertEqual(import_size(count), said, count)

    def test_media_source_says_nothing_for_no_size(self) -> None:
        for count, said in ((None, ""), (0, ""), (1023, "1023 B"), (KB, "1.0 KB"),
                            (MB, "1.0 MB"), (GB, "1.0 GB"), (TB, "1024.0 GB"),
                            (10**21, "931322574615.5 GB")):
            self.assertEqual(source_size(count), said, count)

    def test_metrics_goes_one_unit_further(self) -> None:
        for value, said in ((None, "-"), (0, "0 B"), (1023, "1023 B"), (KB, "1.0 KB"),
                            (MB, "1.0 MB"), (GB, "1.0 GB"), (TB, "1.0 TB"),
                            (10**21, "909494701.8 TB")):
            self.assertEqual(metrics_size(value), said, value)


if __name__ == "__main__":
    unittest.main()
