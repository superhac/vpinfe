import unittest

from common.values import is_truthy


class IsTruthyTests(unittest.TestCase):
    def test_it_accepts_the_spellings_config_files_actually_use(self) -> None:
        for value in ("1", "true", "TRUE", " Yes ", "on", True):
            with self.subTest(value=value):
                self.assertTrue(is_truthy(value))

    def test_everything_else_is_false(self) -> None:
        for value in ("0", "false", "no", "off", "maybe", 0, False):
            with self.subTest(value=value):
                self.assertFalse(is_truthy(value))

    def test_absent_means_the_default_not_false(self) -> None:
        """A missing setting can still be opted in by its caller."""
        for value in (None, "", "   "):
            with self.subTest(value=value):
                self.assertFalse(is_truthy(value))
                self.assertTrue(is_truthy(value, default=True))

    def test_a_real_bool_ignores_the_default(self) -> None:
        self.assertFalse(is_truthy(False, default=True))


if __name__ == "__main__":
    unittest.main()
