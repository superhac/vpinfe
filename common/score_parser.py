import configparser
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from dataclasses import asdict
from pathlib import Path
from typing import BinaryIO


@dataclass
class ParsedEntry:
    section: str
    rank: int | None
    initials: str
    score: int | None = None
    value_suffix: str | None = None
    extra_lines: list[str] = field(default_factory=list)


logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")

rom_aliases = {
    "alpok_b6": "alpok_l2",
    "arena": "amazon3a",
    "bcats_l5": "bcats_l2",
    "afm_113b": "afm_113",
}

def load_roms() -> dict:
    roms_path = Path(__file__).with_name("resources") / "roms.json"
    with roms_path.open("r", encoding="utf-8") as f:
        return json.load(f)


roms = load_roms()


def bcd_to_int(byte_vals: list[int]) -> int:
    """Convert a sequence of BCD bytes into one integer score."""
    score = 0

    for byte_val in byte_vals:
        high = (byte_val >> 4) & 0xF
        low = byte_val & 0xF

        if high > 9 or low > 9:
            raise ValueError(f"Invalid BCD byte: 0x{byte_val:02X}")

        score = score * 100 + (high * 10 + low)

    return score

def read_offsets(f: BinaryIO, offsets: list[int], one_based: bool = False) -> list[int]:
    read_values = []
    for offset in offsets:
            seek_offset = offset - 1 if one_based else offset
            f.seek(seek_offset)
            b = f.read(1)
            if len(b) != 1:
                raise ValueError(f"Could not read byte at offset {offset}")
            read_values.append(b[0])
    return read_values

def bytes_to_text(byte_vals: list[int]) -> str:
    """Convert a sequence of byte values into an ASCII string."""
    return "".join(chr(byte_val) for byte_val in byte_vals)

def low_nibble_pairs_to_text(byte_vals: list[int]) -> str:
    """Decode packed initials from pairs of low nibbles."""
    if len(byte_vals) % 2 != 0:
        raise ValueError("Packed nibble text requires an even number of bytes")

    chars = []
    for index in range(0, len(byte_vals), 2):
        char_code = ((byte_vals[index] & 0x0F) << 4) | (byte_vals[index + 1] & 0x0F)
        chars.append(chr(char_code))

    return "".join(chars)

def atlantis_initials_to_text(byte_vals: list[int]) -> str:
    """Decode Atlantis initials where 79 is space and other values map via +48."""
    chars = []
    for byte_val in byte_vals:
        chars.append(chr(32 if byte_val == 79 else byte_val + 48))
    return "".join(chars)

def austin_name_to_text(byte_vals: list[int]) -> str:
    """Decode Austin Powers names, handling bracket-as-space padding and short names."""
    chars = [chr(32 if byte_val == 91 else byte_val) for byte_val in byte_vals]

    if chars[4:] == [" "] * 6 and byte_vals[3] == byte_vals[2]:
        return "".join(chars[:3]).rstrip()

    return "".join(chars).rstrip()

def clean_text(text: str) -> str:
    """Strip common NVRAM padding characters from decoded text."""
    text = text.split("\x00", 1)[0]
    return text.rstrip("\xff ")

def bytes_to_int(byte_vals: list[int]) -> int:
    """Convert a sequence of bytes into one big-endian integer."""
    value = 0

    for byte_val in byte_vals:
        value = (value << 8) + byte_val

    return value

def digit_bytes_to_int(byte_vals: list[int], digit_offset: int = 0) -> int:
    """Convert a sequence of digit bytes into an integer."""
    value = 0

    for byte_val in byte_vals:
        digit = byte_val - digit_offset
        if digit < 0 or digit > 9:
            raise ValueError(f"Invalid digit byte: {byte_val} with offset {digit_offset}")
        value = value * 10 + digit

    return value

def high_nibble_bytes_to_int(byte_vals: list[int], zero_byte: int | None = None) -> int:
    """Convert bytes whose high nibbles represent digits into an integer."""
    value = 0

    for byte_val in reversed(byte_vals):
        if zero_byte is not None and byte_val == zero_byte:
            digit = 0
        else:
            digit = (byte_val >> 4) & 0x0F
        if digit < 0 or digit > 9:
            raise ValueError(f"Invalid high-nibble digit byte: {byte_val}")
        value = value * 10 + digit

    return value

def decode_initials(byte_vals: list[int], name_decoder: str | None = None) -> str:
    if name_decoder == "low_nibble_pairs_ascii":
        return clean_text(low_nibble_pairs_to_text(byte_vals))
    if name_decoder == "atlantis_initials":
        return clean_text(atlantis_initials_to_text(byte_vals))
    if name_decoder == "austin_name":
        return clean_text(austin_name_to_text(byte_vals))

    return clean_text(bytes_to_text(byte_vals))

def decode_single_bcd_score(filename: str, rom_config: dict) -> int:
    with open(filename, "rb") as f:
        bytes_read = read_offsets(
            f,
            rom_config["offsets"],
            one_based=rom_config.get("one_based", False),
        )
    return bcd_to_int(bytes_read)

def decode_single_digit_score(filename: str, rom_config: dict) -> int:
    with open(filename, "rb") as f:
        bytes_read = read_offsets(
            f,
            rom_config["offsets"],
            one_based=rom_config.get("one_based", False),
        )
    if rom_config.get("reverse_digits", False):
        bytes_read = list(reversed(bytes_read))
    return digit_bytes_to_int(bytes_read, rom_config.get("digit_offset", 0))

def decode_single_high_nibble_score(filename: str, rom_config: dict) -> int:
    with open(filename, "rb") as f:
        bytes_read = read_offsets(
            f,
            rom_config["offsets"],
            one_based=rom_config.get("one_based", False),
        )
    return high_nibble_bytes_to_int(bytes_read, rom_config.get("zero_byte"))

def decode_leaderboard_bcd(filename: str, rom_config: dict) -> list[ParsedEntry]:
    entries: list[ParsedEntry] = []
    one_based = rom_config.get("one_based", False)

    with open(filename, "rb") as f:
        for entry in rom_config["entries"]:
            initials = decode_initials(
                read_offsets(f, entry["name_offsets"], one_based=one_based),
                entry.get("name_decoder"),
            )
            score = bcd_to_int(
                read_offsets(f, entry["score_offsets"], one_based=one_based)
            )
            entries.append(
                ParsedEntry(
                    section=entry["title"],
                    rank=entry["rank"],
                    initials=initials,
                    score=score,
                )
            )

    return entries

def decode_score_bytes(score_bytes: list[int], score_decoder: str) -> int:
    if score_decoder == "bcd":
        return bcd_to_int(score_bytes)
    if score_decoder == "big_endian":
        return bytes_to_int(score_bytes)
    if score_decoder == "big_endian_x10":
        return bytes_to_int(score_bytes) * 10
    if score_decoder == "raw_digits_x10":
        return digit_bytes_to_int(score_bytes) * 10
    if score_decoder == "raw_byte":
        return score_bytes[0]

    raise ValueError(f"Unknown score decoder: {score_decoder}")

def decode_afm_ruler_of_the_universe_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    term_byte = read_offsets(f, [entry["extra_offsets"]["term"]], one_based=one_based)[0]
    month_names = {
        1: "JAN",
        2: "FEB",
        3: "MAR",
        4: "APR",
        5: "MAY",
        6: "JUN",
        7: "JUL",
        8: "AUG",
        9: "SEP",
        10: "OCT",
        11: "NOV",
        12: "DEC",
    }

    month = month_names.get(data_bytes[2], str(data_bytes[2]))
    hour = data_bytes[4]
    suffix = " AM"
    if hour > 12:
        hour -= 12
        suffix = " PM"

    minute = f"{data_bytes[5]:02d}"
    year = data_bytes[0] * 256 + data_bytes[1]
    term_text = "INAUGURATED" if term_byte == 0 else f"RE-ELECTION #{term_byte:X}"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[
            term_text,
            f"{data_bytes[3]} {month}, {year} {hour}:{minute}{suffix}",
        ],
    )

def decode_andrett4_lap_time_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    lap_byte = read_offsets(f, entry["data_offsets"], one_based=one_based)[0]
    high = lap_byte >> 4
    low = lap_byte & 0x0F
    low_text = format(low, "X") if lap_byte != 0 else "0"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[f"{high}.{low_text}0"],
    )

def decode_apollo13_multiball_entry(
    entry: dict,
    initials: str,
) -> ParsedEntry:
    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=["PLAYED 13-BALL MULTIBALL"],
    )

def decode_labeled_single_value_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    value_byte = read_offsets(f, entry["data_offsets"], one_based=one_based)[0]
    if entry.get("value_format") == "hex":
        value_text = format(value_byte, "X")
    else:
        value_text = str(value_byte)

    if "value_suffix" in entry and "label" not in entry:
        line = f"{value_text} {entry['value_suffix']}".rstrip()
    else:
        line = f"{entry['label']} = {value_text}"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[line],
    )

def decode_mixed_leaderboard(
    filename: str,
    rom_config: dict,
    settings: dict | None = None,
) -> list[ParsedEntry]:
    results: list[ParsedEntry] = []
    one_based = rom_config.get("one_based", False)
    merged_settings = dict(rom_config.get("settings", {}))

    if settings:
        merged_settings.update(settings)

    with open(filename, "rb") as f:
        for section in rom_config["sections"]:
            enabled_setting = section.get("enabled_setting")
            if enabled_setting and not merged_settings.get(enabled_setting, False):
                continue

            for entry in section["entries"]:
                initials = decode_initials(
                    read_offsets(f, entry["name_offsets"], one_based=one_based),
                    entry.get("name_decoder"),
                )
                if "score_offsets" not in entry and "entry_decoder" not in entry:
                    results.append(
                        ParsedEntry(
                            section=section["title"],
                            rank=entry["rank"],
                            initials=initials,
                        )
                    )
                    continue
                if "entry_decoder" in entry:
                    if entry["entry_decoder"] == "afm_ruler_of_the_universe":
                        decoded_entry = decode_afm_ruler_of_the_universe_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "andrett4_lap_time":
                        decoded_entry = decode_andrett4_lap_time_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "apollo13_multiball":
                        decoded_entry = decode_apollo13_multiball_entry(
                            entry,
                            initials,
                        )
                    elif entry["entry_decoder"] == "labeled_single_value":
                        decoded_entry = decode_labeled_single_value_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    else:
                        raise ValueError(f"Unknown entry decoder: {entry['entry_decoder']}")
                    decoded_entry.section = section["title"]
                    results.append(decoded_entry)
                    continue

                score_bytes = read_offsets(
                    f,
                    entry["score_offsets"],
                    one_based=one_based,
                )
                results.append(
                    ParsedEntry(
                        section=section["title"],
                        rank=entry["rank"],
                        initials=initials,
                        score=decode_score_bytes(score_bytes, entry["score_decoder"]),
                        value_suffix=entry.get("value_suffix"),
                    )
                )

    return results

def parse_ini_score(value: str) -> int:
    normalized = value.strip().replace(",", "")
    return int(normalized)

def build_ini_section_name(section_name: str, group_name: str) -> str:
    group_name = group_name.strip()
    return group_name or section_name

def decode_ini_file(filename: str) -> list[ParsedEntry]:
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    read_files = parser.read(filename, encoding="utf-8")
    if not read_files:
        raise FileNotFoundError(filename)

    entries: list[ParsedEntry] = []
    paired_keys: set[str] = set()
    trailing_name_pattern = re.compile(r"^(?P<score_key>.+?\d+)Name$")
    split_name_pattern = re.compile(r"^(?P<prefix>.+?)Score(?P<rank>\d+)$")

    for section_name in parser.sections():
        section_items = dict(parser.items(section_name))

        for key, value in section_items.items():
            if key in paired_keys:
                continue

            trailing_name_match = trailing_name_pattern.match(key)
            if trailing_name_match:
                score_key = trailing_name_match.group("score_key")
                score_value = section_items.get(score_key)
                if score_value is None:
                    continue

                rank_match = re.search(r"(\d+)$", score_key)
                rank = int(rank_match.group(1)) if rank_match else None
                group_name = re.sub(r"\d+$", "", score_key)
                entries.append(
                    ParsedEntry(
                        section=build_ini_section_name(section_name, group_name),
                        rank=rank,
                        initials=clean_text(value),
                        score=parse_ini_score(score_value),
                    )
                )
                paired_keys.update({key, score_key})
                continue

            split_name_match = split_name_pattern.match(key)
            if split_name_match:
                group_name = split_name_match.group("prefix")
                rank_text = split_name_match.group("rank")
                name_key = f"{group_name}Name{rank_text}"
                name_value = section_items.get(name_key)
                if name_value is None:
                    continue

                entries.append(
                    ParsedEntry(
                        section=build_ini_section_name(section_name, group_name),
                        rank=int(rank_text),
                        initials=clean_text(name_value),
                        score=parse_ini_score(value),
                    )
                )
                paired_keys.update({key, name_key})

    return entries

DECODERS = {
    "single_bcd_score": decode_single_bcd_score,
    "single_digit_score": decode_single_digit_score,
    "single_high_nibble_score": decode_single_high_nibble_score,
    "leaderboard_bcd": decode_leaderboard_bcd,
    "mixed_leaderboard": decode_mixed_leaderboard,
}

def resolve_rom_name(rom_name: str) -> str:
    return rom_aliases.get(rom_name, rom_name)

def format_entry(entry: ParsedEntry) -> list[str]:
    rank_text = f"{entry.rank} " if entry.rank is not None else ""

    if entry.score is not None:
        value_text = f"{entry.score:,}"
        if entry.value_suffix:
            value_text = f"{value_text} {entry.value_suffix}"
        return [f"{rank_text}{entry.initials} - {value_text}"]

    if entry.extra_lines:
        return [f"{rank_text}{entry.initials} - {' | '.join(entry.extra_lines)}".rstrip()]

    return [f"{rank_text}{entry.initials}".rstrip()]

def format_result(rom_name: str, result: int | list[ParsedEntry]) -> list[str]:
    lines = [f"{rom_name}:"]
    resolved_rom_name = resolve_rom_name(rom_name)

    if isinstance(result, int):
        lines.append(f"{roms[resolved_rom_name]['scoretype']}: {result:,}")
        return lines

    last_section = None
    for entry in result:
        if entry.section != last_section:
            lines.append(entry.section)
            last_section = entry.section
        lines.extend(format_entry(entry))

    return lines

def detect_score_type(rom_name: str, filename: str | None = None) -> str:
    if filename and Path(filename).suffix.lower() == ".ini":
        return "ini"

    resolved_rom_name = resolve_rom_name(rom_name)
    return roms[resolved_rom_name]["scoretype"]

def _has_meaningful_entry(entry: ParsedEntry) -> bool:
    return bool(
        clean_text(entry.initials)
        or entry.score is not None
        or entry.extra_lines
    )


def result_to_jsonable(
    rom_name: str,
    result: int | list[ParsedEntry],
    filename: str | None = None,
) -> dict | None:
    resolved_rom_name = resolve_rom_name(rom_name)
    score_type = detect_score_type(rom_name, filename)

    if isinstance(result, int):
        return {
            "rom": rom_name,
            "resolved_rom": resolved_rom_name,
            "score_type": score_type,
            "value": result,
        }

    filtered_entries = [entry for entry in result if _has_meaningful_entry(entry)]
    if not filtered_entries:
        return None

    return {
        "rom": rom_name,
        "resolved_rom": resolved_rom_name,
        "score_type": score_type,
        "entries": [asdict(entry) for entry in filtered_entries],
    }

def read_rom(
    rom_name: str,
    filename: str,
    settings: dict | None = None,
) -> int | list[ParsedEntry]:
    if Path(filename).suffix.lower() == ".ini":
        return decode_ini_file(filename)

    resolved_rom_name = resolve_rom_name(rom_name)
    rom_config = roms.get(resolved_rom_name)
    if rom_config is None:
        raise KeyError(f"Unknown ROM: {rom_name}")

    decoder_name = rom_config.get("decoder")
    decoder = DECODERS.get(decoder_name)
    if decoder is None:
        raise ValueError(f"No decoder registered for ROM '{resolved_rom_name}': {decoder_name}")

    return decoder(filename, rom_config, settings) if settings is not None else decoder(filename, rom_config)
    
if __name__ == "__main__":
    rom_files = {
        "agent777": "/home/superhac/tables/Agents 777 (Game Plan 1984)/pinmame/nvram/agent777.nv",
        "aar_101": "/home/superhac/tables/Aaron Spelling (Data East 1992)/pinmame/nvram/aar_101.nv",
        "bbb109": "/home/superhac/tables/Big Bang Bar (Capcom 1996)/pinmame/nvram/bbb109.nv",
        "badgirls": "/home/superhac/tables/Bad Girls (Gottlieb 1988)/pinmame/nvram/badgirls.nv",
        "baywatch": "/home/superhac/tables/Baywatch (Sega 1995)/pinmame/nvram/baywatch.nv",
        "beav_butt": "/home/superhac/tables/Beavis and Butt-Head Pinballed (Original 2024)/pinmame/nvram/beav_butt.nv",
        "bguns_l8": "/home/superhac/tables/Big Guns (Williams 1987)/pinmame/nvram/bguns_l8.nv",
        "biggame": "/home/superhac/tables/Big Game (Stern 1980)/pinmame/nvram/biggame.nv",
        "bighouse": "/home/superhac/tables/Big House (Gottlieb 1989)/pinmame/nvram/bighouse.nv",
        "bighurt": "/home/superhac/tables/Frank Thomas' Big Hurt (Gottlieb 1995)/pinmame/nvram/bighurt.nv",
        "blkshpsq": "/home/superhac/tables/Black Sheep Squadron (Astro Games 1979)/pinmame/nvram/blkshpsq.nv",
        "bk2k_l4": "/home/superhac/tables/Black Knight 2000 (Williams 1989)/pinmame/nvram/bk2k_l4.nv",
        #"beachbms": "/home/superhac/tables/Beach Bums (Bally 1992)/pinmame/nvram/beachbms.nv",
        #"barbwire": "/home/superhac/tables/Barb Wire (Gottlieb 1996)/pinmame/nvram/barbwire.nv",
        "abv106": "/home/superhac/tables/Airborne (Capcom 1996)/pinmame/nvram/abv106.nv",
        "abv106r": "/home/superhac/tables/Airborne (Capcom 1996)/pinmame/nvram/abv106r.nv",
        "acd_170h": "/home/superhac/tables/AC-DC LUCI Premium VR (Stern 2013)/pinmame/nvram/acd_170h.nv",
        "afm_113b": "/home/superhac/tables/Attack from Mars (Bally 1995)/pinmame/nvram/afm_113b.nv",
        "ali": "/home/superhac/tables/Ali (Stern 1980)/pinmame/nvram/ali.nv",
        "attack": "/home/superhac/tables/Attack (Playmatic 1980)/pinmame/nvram/attack.nv",
        "andretti": "/home/superhac/tables/Mario Andretti (Gottlieb 1995)/pinmame/nvram/andretti.nv",
        "apollo13": "/home/superhac/tables/Apollo 13 (Sega 1995)/pinmame/nvram/apollo13.nv",
        "atlantis": "/home/superhac/tables/Atlantis (Bally 1989)/pinmame/nvram/atlantis.nv",
        "atleta": "/home/superhac/tables/Atleta (Inder 1991)/pinmame/nvram/atleta.nv",
        "black100": "/home/superhac/tables/Blackwater 100 (Bally 1988)/pinmame/nvram/black100.nv",
        #"bbh_160": "/home/superhac/tables/Big Buck Hunter Pro (Stern 2010)/pinmame/nvram/bbh_160.nv",
        "bbh_170": "/home/superhac/tables/Big Buck Hunter Pro (Stern 2010)/pinmame/nvram/bbh_170.nv",
        "bcats_l5": "/home/superhac/tables/Bad Cats (Williams 1989)/pinmame/nvram/bcats_l5.nv",
        "bdk_294": "/home/superhac/tables/Batman (Stern 2008)/pinmame/nvram/bdk_294.nv",
        "avr_200": "/home/superhac/tables/James Cameron's Avatar (Stern 2010)/pinmame/nvram/avr_200.nv",
        "avs_170": "/home/superhac/tables/The Avengers Pro (Stern 2012)/pinmame/nvram/avs_170.nv",
        "austin": "/home/superhac/tables/Austin Powers (Stern 2001)/pinmame/nvram/austin.nv",
        "arena": "/home/superhac/tables/Arena (Gottlieb 1987)/pinmame/nvram/arena.nv",
        #"andrett4": "/home/superhac/tables/Andretti (Gottlieb 1995)/pinmame/nvram/andrett4.nv",
        #"alpok_l2": "/home/superhac/tables/Alien Poker (Williams 1980)/pinmame/nvram/alpok_l2.nv",
        "alpok_b6": "/home/superhac/tables/Alien Poker (Williams 1980)/pinmame/nvram/alpok_b6.nv",
        #"amazon3a": "/home/superhac/tables/Amazon Hunt (Gottlieb 1983)/pinmame/nvram/amazonh.nv",
        "Matrix": "/home/superhac/tables/The Matrix (Original 2026)/user/VPReg.ini",
        "DarkestDungeon": "/home/superhac/tables/The Matrix (Original 2026)/user/VPReg.ini", 
    }

    for rom_name, filename in rom_files.items():
        try:
            result = read_rom(rom_name, filename)
        except FileNotFoundError:
            print(f"{rom_name}: file not found, skipping")
            print()
            continue
        except Exception as exc:
            logging.error("Failed to parse ROM '%s' from '%s': %s", rom_name, filename, exc)
            sys.exit(1)

        for line in format_result(rom_name, result):
            print(line)

        print()
        print(json.dumps(result_to_jsonable(rom_name, result, filename), indent=2))
        print()
