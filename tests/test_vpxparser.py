import unittest

from common.vpxparser import VPXParser


class TestVPXParser(unittest.TestCase):
    def test_extract_rom_name_ignores_single_quote_commented_cgamename_lines(self) -> None:
        parser = VPXParser()
        values = {
            "gameData": (
                "'Const cGameName = \"mm_10\" 'Williams official rom\n"
                "'Const cGameName = \"mm_109\" 'free play only\n"
                "'Const cGameName=\"mm_109b\" 'unofficial\n"
                "Const cGameName=\"mm_109c\" 'unofficial profanity rom"
            )
        }

        parser.extractRomName(values)

        self.assertEqual(values["rom"], "mm_109c")

    def test_extract_rom_name_uses_first_uncommented_cgamename(self) -> None:
        parser = VPXParser()
        values = {
            "gameData": (
                "'Const cGameName = \"commented\"\n"
                "Const cGameName = \"active_first\"\n"
                "Const cGameName = \"active_second\""
            )
        }

        parser.extractRomName(values)

        self.assertEqual(values["rom"], "active_first")

    def test_extract_rom_name_preserves_single_quote_inside_string_literals(self) -> None:
        parser = VPXParser()
        values = {
            "gameData": (
                "Dim tableName\n"
                "tableName = \"It' s fine\"\n"
                "Const cGameName = \"quoted_ok\""
            )
        }

        parser.extractRomName(values)

        self.assertEqual(values["rom"], "quoted_ok")

    def test_extract_rom_name_falls_back_to_opt_rom_after_commented_cgamename(self) -> None:
        parser = VPXParser()
        values = {
            "gameData": (
                "'Const cGameName = \"commented\"\n"
                "Const cOptRom = \"fallback_rom\""
            )
        }

        parser.extractRomName(values)

        self.assertEqual(values["rom"], "fallback_rom")


if __name__ == "__main__":
    unittest.main()
