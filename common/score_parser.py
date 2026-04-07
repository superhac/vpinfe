import configparser
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from dataclasses import asdict
from pathlib import Path
from typing import BinaryIO

try:
    from platformdirs import user_config_dir
except ImportError:
    def user_config_dir(appname: str, appauthor: str | None = None) -> str:
        return str(Path.home() / ".config" / appname)


@dataclass
class ParsedEntry:
    section: str
    rank: int | None
    initials: str
    score: int | None = None
    value_prefix: str | None = None
    value_suffix: str | None = None
    value_format: str | None = None
    extra_lines: list[str] = field(default_factory=list)
    multiline: bool = False


logging.basicConfig(level=logging.ERROR, format="%(levelname)s: %(message)s")

USER_ROMS_PATH = Path(user_config_dir("vpinfe", "vpinfe")) / "roms.json"

# alias, rom name in roms.json 
rom_aliases = {
    "alpok_b6": "alpok_l2",
    "arena": "amazon3a",
    "bcats_l5": "bcats_l2",
    "afm_113b": "afm_113",
    "btmn_106": "btmn_101",
    "cftbl_l4": "cftbl_l3",
    "cp_16": "cp_15",
    "eatpm_l4": "eatpm_l1",
    "fg_1200af":"fg_1200al",
    "eightbll": "evelknie",
    "frpwr_b7": "frpwr_b6",
    "hook_501":"hook_408",
    "im_185ve": "im_185",
    "im_183ve": "im_185",
    "jd_l1": "jd_l7",
    "jupk_600":"jupk_513",
    "kpb105":"kpv106",
    "lah_113":"lah_112",
    "lca2":"lca",
    "mb_106b":"mb_106",
    "mm_109b":"mm_109c",
    "rab_320":"rab_103",
    "sc_18n11":"sc_180",
    "ss_15":"ss_14",
    "twenty4_150": "twenty4_144",
    "ww_lh6": "ww_lh5",
    "wwfr_106":"wwfr_103",

}

def get_roms_path() -> Path:
    candidate_paths: list[Path] = [
        USER_ROMS_PATH,
        Path(__file__).with_name("resources") / "roms.json",
    ]

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate_paths.append(Path(meipass) / "common" / "resources" / "roms.json")

    exe_dir = Path(sys.executable).resolve().parent
    candidate_paths.extend(
        [
            exe_dir / "common" / "resources" / "roms.json",
            exe_dir / "_internal" / "common" / "resources" / "roms.json",
            exe_dir.parent / "Resources" / "common" / "resources" / "roms.json",
        ]
    )

    candidates = list(dict.fromkeys(candidate_paths))

    for path in candidates:
        if path.exists():
            return path

    raise FileNotFoundError(
        "Could not find roms.json. Checked: "
        + ", ".join(str(path) for path in candidates)
    )

def load_roms() -> dict:
    roms_path = get_roms_path()
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

def high_nibble_pairs_to_text(byte_vals: list[int]) -> str:
    """Decode packed initials from pairs of high nibbles, with FF meaning space."""
    if len(byte_vals) % 2 != 0:
        raise ValueError("Packed nibble text requires an even number of bytes")

    chars = []
    for index in range(0, len(byte_vals), 2):
        high = (byte_vals[index] >> 4) & 0x0F
        low = (byte_vals[index + 1] >> 4) & 0x0F
        if high == 0x0F and low == 0x0F:
            chars.append(" ")
            continue
        chars.append(chr((high << 4) | low))

    return "".join(chars)

def atlantis_initials_to_text(byte_vals: list[int]) -> str:
    """Decode Atlantis initials where 79 is space and other values map via +48."""
    chars = []
    for byte_val in byte_vals:
        chars.append(chr(32 if byte_val == 79 else byte_val + 48))
    return "".join(chars)

def hvymetal_initials_to_text(byte_vals: list[int]) -> str:
    """Decode Heavy Metal initials where 79/255 are spaces, others map via +48, then reverse."""
    chars = []
    for byte_val in byte_vals:
        chars.append(chr(32 if byte_val in (79, 255) else byte_val + 48))
    return "".join(reversed(chars))

def dd_l2_initials_to_text(byte_vals: list[int]) -> str:
    """Decode Dr Dude Team initials where 0 is space and other values map via +54."""
    chars = []
    for byte_val in byte_vals:
        chars.append(chr(32 if byte_val == 0 else byte_val + 54))
    return "".join(chars)

def grand_l4_initials_to_text(byte_vals: list[int]) -> str:
    """Decode Grand Lizard initials where values above 96 are stored with +128."""
    chars = []
    for byte_val in byte_vals:
        chars.append(chr(byte_val - 128 if byte_val > 96 else byte_val))
    return "".join(chars)

def austin_name_to_text(byte_vals: list[int]) -> str:
    """Decode Austin Powers names, handling bracket-as-space padding and short names."""
    chars = [chr(32 if byte_val == 91 else byte_val) for byte_val in byte_vals]

    if chars[4:] == [" "] * 6 and byte_vals[3] == byte_vals[2]:
        return "".join(chars[:3]).rstrip()

    return "".join(chars).rstrip()

def monopoly_name_to_text(byte_vals: list[int]) -> str:
    """Decode Monopoly names, where some entries are 3 initials plus a token id."""
    token_names = {
        0: "BATTLESHIP",
        1: "THIMBLE",
        2: "SACK OF MONEY",
        3: "IRON",
        4: "CANNON",
        5: "DOG",
        6: "HORSE AND RIDER",
        7: "SHOE",
        8: "TOP HAT",
        9: "WHEELBARROW",
        10: "RACECAR",
        11: "PLD LOGO",
    }

    token_id = byte_vals[3]
    if token_id in token_names:
        initials = "".join(chr(byte_val) for byte_val in byte_vals[:3]).rstrip()
        return f"{initials} {token_names[token_id]}".rstrip()

    return clean_text(bytes_to_text(byte_vals))

def ff_blank_initials_to_text(byte_vals: list[int]) -> str:
    """Decode ASCII initials where 255 bytes should be treated as blanks."""
    chars = []
    for byte_val in byte_vals:
        chars.append("\x00" if byte_val == 255 else chr(byte_val))
    return "".join(chars)

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

def digit_bytes_to_int(
    byte_vals: list[int],
    digit_offset: int = 0,
    zero_byte: int | None = None,
) -> int:
    """Convert a sequence of digit bytes into an integer."""
    value = 0

    for byte_val in byte_vals:
        if zero_byte is not None and byte_val == zero_byte:
            digit = 0
        else:
            digit = byte_val - digit_offset
        if digit < 0 or digit > 9:
            raise ValueError(f"Invalid digit byte: {byte_val} with offset {digit_offset}")
        value = value * 10 + digit

    return value

def high_nibble_bytes_to_int(
    byte_vals: list[int],
    zero_byte: int | None = None,
    zero_if_gte: int | None = None,
) -> int:
    """Convert bytes whose high nibbles represent digits into an integer."""
    value = 0

    for byte_val in reversed(byte_vals):
        if zero_if_gte is not None and byte_val >= zero_if_gte:
            digit = 0
        elif zero_byte is not None and byte_val == zero_byte:
            digit = 0
        else:
            digit = (byte_val >> 4) & 0x0F
        if digit < 0 or digit > 9:
            raise ValueError(f"Invalid high-nibble digit byte: {byte_val}")
        value = value * 10 + digit

    return value

def decode_initials(byte_vals: list[int], name_decoder: str | None = None) -> str:
    if name_decoder == "ascii_upper":
        return clean_text(bytes_to_text(byte_vals)).upper()
    if name_decoder == "low_nibble_pairs_ascii":
        return clean_text(low_nibble_pairs_to_text(byte_vals))
    if name_decoder == "high_nibble_pairs_ascii":
        return clean_text(high_nibble_pairs_to_text(byte_vals))
    if name_decoder == "atlantis_initials":
        return clean_text(atlantis_initials_to_text(byte_vals))
    if name_decoder == "hvymetal_initials":
        return clean_text(hvymetal_initials_to_text(byte_vals))
    if name_decoder == "dd_l2_initials":
        return clean_text(dd_l2_initials_to_text(byte_vals))
    if name_decoder == "grand_l4_initials":
        return clean_text(grand_l4_initials_to_text(byte_vals))
    if name_decoder == "austin_name":
        return clean_text(austin_name_to_text(byte_vals))
    if name_decoder == "monopoly_name":
        return clean_text(monopoly_name_to_text(byte_vals))
    if name_decoder == "ff_blank_ascii":
        return clean_text(ff_blank_initials_to_text(byte_vals))

    return clean_text(bytes_to_text(byte_vals))

def decode_single_bcd_score(filename: str, rom_config: dict) -> int:
    with open(filename, "rb") as f:
        bytes_read = read_offsets(
            f,
            rom_config["offsets"],
            one_based=rom_config.get("one_based", False),
        )
    return bcd_to_int(bytes_read)

def decode_single_bcd_score_x10(filename: str, rom_config: dict) -> int:
    return decode_single_bcd_score(filename, rom_config) * 10

def decode_single_digit_score(filename: str, rom_config: dict) -> int:
    with open(filename, "rb") as f:
        bytes_read = read_offsets(
            f,
            rom_config["offsets"],
            one_based=rom_config.get("one_based", False),
        )
    if rom_config.get("reverse_digits", False):
        bytes_read = list(reversed(bytes_read))
    return digit_bytes_to_int(
        bytes_read,
        rom_config.get("digit_offset", 0),
        rom_config.get("zero_byte"),
    )

def decode_single_digit_score_x10(filename: str, rom_config: dict) -> int:
    return decode_single_digit_score(filename, rom_config) * 10

def decode_single_high_nibble_score(filename: str, rom_config: dict) -> int:
    with open(filename, "rb") as f:
        bytes_read = read_offsets(
            f,
            rom_config["offsets"],
            one_based=rom_config.get("one_based", False),
        )
    return high_nibble_bytes_to_int(
        bytes_read,
        rom_config.get("zero_byte"),
        rom_config.get("zero_if_gte"),
    )

def decode_single_high_nibble_score_x10(filename: str, rom_config: dict) -> int:
    return decode_single_high_nibble_score(filename, rom_config) * 10

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

def decode_score_bytes(
    score_bytes: list[int],
    score_decoder: str,
    entry: dict | None = None,
) -> int:
    entry = entry or {}

    if score_decoder == "bcd":
        return bcd_to_int(score_bytes)
    if score_decoder == "bcd_x10":
        return bcd_to_int(score_bytes) * 10
    if score_decoder == "big_endian":
        return bytes_to_int(score_bytes)
    if score_decoder == "big_endian_x10":
        return bytes_to_int(score_bytes) * 10
    if score_decoder == "byte_pair_100_1":
        return score_bytes[0] * 100 + score_bytes[1]
    if score_decoder == "low_nibble_100_bcd":
        return (score_bytes[0] & 0x0F) * 100 + bcd_to_int([score_bytes[1]])
    if score_decoder == "high_nibble_digits":
        return high_nibble_bytes_to_int(
            score_bytes,
            entry.get("zero_byte", 255),
            entry.get("zero_if_gte"),
        )
    if score_decoder == "raw_digits":
        return digit_bytes_to_int(
            score_bytes,
            entry.get("digit_offset", 0),
            entry.get("zero_byte"),
        )
    if score_decoder == "raw_digits_x10":
        return digit_bytes_to_int(
            score_bytes,
            entry.get("digit_offset", 0),
            entry.get("zero_byte"),
        ) * 10
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
    elif "label" not in entry:
        line = value_text
    else:
        line = f"{entry['label']} = {value_text}"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[line],
    )

def decode_since_date_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
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

    month = month_names.get(data_bytes[0], str(data_bytes[0]))
    day = data_bytes[1]
    year = data_bytes[2] * 256 + data_bytes[3]

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[f"SINCE {month}. {day}, {year}"],
    )

def decode_x_y_seconds_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[f"{data_bytes[0]}.{data_bytes[1]} SECONDS"],
    )

def decode_mm_ss_cc_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    total = data_bytes[0] * 256 + data_bytes[1]
    minutes = round(total / 6000.0)
    seconds = round((total - minutes * 6000) / 100.0)
    centiseconds = total - minutes * 6000 - seconds * 100

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[f"{minutes:02d}:{seconds:02d}.{centiseconds:02d}"],
    )

def decode_crowned_datetime_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    crown_count = read_offsets(f, [entry["extra_offsets"]["crown_count"]], one_based=one_based)[0]

    if crown_count == 0:
        return ParsedEntry(section="", rank=entry["rank"], initials="")

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
    ordinal_suffix = {1: "st", 2: "nd", 3: "rd"}.get(crown_count, "th")
    month = month_names.get(data_bytes[2], str(data_bytes[2]))
    hour = data_bytes[4]
    suffix = " AM"
    if hour > 12:
        hour -= 12
        suffix = " PM"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[
            f"CROWNED FOR THE {crown_count}{ordinal_suffix} TIME",
            f"{data_bytes[3]} {month}, {data_bytes[0] * 256 + data_bytes[1]} {hour}:{data_bytes[5]:02d}{suffix}",
        ],
    )

def decode_datetime_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)

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

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[
            f"{data_bytes[3]} {month}, {data_bytes[0] * 256 + data_bytes[1]} {hour}:{data_bytes[5]:02d}{suffix}",
        ],
        multiline=True,
    )

def decode_team_wins_rings_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    rings = bcd_to_int([data_bytes[0]])
    wins = bcd_to_int([data_bytes[1]]) * 100 + bcd_to_int([data_bytes[2]])

    if rings == 0:
        line = f"{wins}"
    elif rings == 1:
        line = f"{wins} 1-RING"
    else:
        line = f"{wins} {rings}-RINGS"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[line],
    )

def decode_static_text_entry(
    entry: dict,
    initials: str,
) -> ParsedEntry:
    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials=initials,
        extra_lines=[entry["text"]],
    )

def decode_name_text_entry(
    entry: dict,
    initials: str,
) -> ParsedEntry:
    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials="",
        extra_lines=[f"{initials}   {entry['text']}"],
    )

def decode_labeled_score_entry(
    f: BinaryIO,
    entry: dict,
    one_based: bool,
) -> ParsedEntry:
    score_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    score = decode_score_bytes(score_bytes, entry["score_decoder"], entry)
    line = f"{entry['label']}   {score:,}"
    if entry.get("value_suffix"):
        line = f"{line} {entry['value_suffix']}"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials="",
        extra_lines=[line],
    )

def decode_got_to_year_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_byte = read_offsets(f, entry["data_offsets"], one_based=one_based)[0]
    year = entry.get("base_year", 1993) - bcd_to_int([data_byte]) * 100

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials="",
        extra_lines=[f"{initials} GOT TO {year}"],
    )

def decode_label_name_value_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    value = decode_score_bytes(data_bytes, entry["score_decoder"], entry)
    if entry.get("value_format") == "hex":
        value_text = format(value, "X")
    else:
        value_text = str(value)
    if entry.get("value_prefix"):
        value_text = f"{entry['value_prefix']}{value_text}"
    if entry.get("value_suffix"):
        value_text = f"{value_text} {entry['value_suffix']}"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials="",
        extra_lines=[entry["label"], initials, value_text],
        multiline=True,
    )

def decode_name_value_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    value = decode_score_bytes(data_bytes, entry["score_decoder"], entry)
    if entry.get("value_format") == "hex":
        value_text = format(value, "X")
    else:
        value_text = str(value)
    if entry.get("value_prefix"):
        value_text = f"{entry['value_prefix']}{value_text}"
    if entry.get("value_suffix"):
        value_text = f"{value_text} {entry['value_suffix']}"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials="",
        extra_lines=[initials, value_text],
        multiline=True,
    )

def decode_label_value_name_entry(
    f: BinaryIO,
    entry: dict,
    initials: str,
    one_based: bool,
) -> ParsedEntry:
    data_bytes = read_offsets(f, entry["data_offsets"], one_based=one_based)
    value = decode_score_bytes(data_bytes, entry["score_decoder"], entry)
    if entry.get("value_format") == "hex":
        value_text = format(value, "X")
    else:
        value_text = str(value)
    if entry.get("value_prefix"):
        value_text = f"{entry['value_prefix']}{value_text}"
    if entry.get("value_suffix"):
        value_text = f"{value_text} {entry['value_suffix']}"

    return ParsedEntry(
        section="",
        rank=entry["rank"],
        initials="",
        extra_lines=[f"{entry['label']}{value_text}", initials],
        multiline=True,
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
                initials = ""
                if "name_offsets" in entry:
                    initials = decode_initials(
                        read_offsets(f, entry["name_offsets"], one_based=one_based),
                        entry.get("name_decoder"),
                    )
                if "score_offsets" not in entry and "entry_decoder" not in entry:
                    decoded_entry = ParsedEntry(
                        section=section["title"],
                        rank=entry["rank"],
                        initials=initials,
                    )
                    if not _has_meaningful_entry(decoded_entry):
                        continue
                    results.append(decoded_entry)
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
                    elif entry["entry_decoder"] == "since_date":
                        decoded_entry = decode_since_date_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "x_y_seconds":
                        decoded_entry = decode_x_y_seconds_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "mm_ss_cc":
                        decoded_entry = decode_mm_ss_cc_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "crowned_datetime":
                        decoded_entry = decode_crowned_datetime_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "datetime":
                        decoded_entry = decode_datetime_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "team_wins_rings":
                        decoded_entry = decode_team_wins_rings_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "static_text":
                        decoded_entry = decode_static_text_entry(
                            entry,
                            initials,
                        )
                    elif entry["entry_decoder"] == "name_text":
                        decoded_entry = decode_name_text_entry(
                            entry,
                            initials,
                        )
                    elif entry["entry_decoder"] == "labeled_score":
                        decoded_entry = decode_labeled_score_entry(
                            f,
                            entry,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "got_to_year":
                        decoded_entry = decode_got_to_year_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "label_name_value":
                        decoded_entry = decode_label_name_value_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "name_value":
                        decoded_entry = decode_name_value_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    elif entry["entry_decoder"] == "label_value_name":
                        decoded_entry = decode_label_value_name_entry(
                            f,
                            entry,
                            initials,
                            one_based,
                        )
                    else:
                        raise ValueError(f"Unknown entry decoder: {entry['entry_decoder']}")
                    if not _has_meaningful_entry(decoded_entry):
                        continue
                    decoded_entry.section = section["title"]
                    results.append(decoded_entry)
                    continue

                score_bytes = read_offsets(
                    f,
                    entry["score_offsets"],
                    one_based=one_based,
                )
                decoded_score = decode_score_bytes(
                    score_bytes,
                    entry["score_decoder"],
                    entry,
                )
                if decoded_score in entry.get("skip_score_values", []):
                    continue
                results.append(
                    ParsedEntry(
                        section=section["title"],
                        rank=entry.get("rank"),
                        initials=initials,
                        score=decoded_score,
                        value_prefix=entry.get("value_prefix"),
                        value_suffix=entry.get("value_suffix"),
                        value_format=entry.get("value_format"),
                    )
                )

    return results

def parse_ini_score(value: str) -> int:
    normalized = value.strip().replace(",", "")
    return int(normalized)

def build_ini_section_name(section_name: str, group_name: str) -> str:
    group_name = group_name.strip()
    return group_name or section_name

def is_standalone_ini_score_key(key: str) -> bool:
    normalized_key = key.strip().lower()
    return normalized_key in {
        "hiscore",
        "highscore",
        "score",
    }

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
                continue

            if is_standalone_ini_score_key(key):
                entries.append(
                    ParsedEntry(
                        section=section_name,
                        rank=None,
                        initials="",
                        score=parse_ini_score(value),
                    )
                )

    return entries

DECODERS = {
    "single_bcd_score": decode_single_bcd_score,
    "single_bcd_score_x10": decode_single_bcd_score_x10,
    "single_digit_score": decode_single_digit_score,
    "single_digit_score_x10": decode_single_digit_score_x10,
    "single_high_nibble_score": decode_single_high_nibble_score,
    "single_high_nibble_score_x10": decode_single_high_nibble_score_x10,
    "leaderboard_bcd": decode_leaderboard_bcd,
    "mixed_leaderboard": decode_mixed_leaderboard,
}

def resolve_rom_name(rom_name: str) -> str:
    return rom_aliases.get(rom_name, rom_name)

def format_entry(entry: ParsedEntry) -> list[str]:
    rank_text = f"{entry.rank} " if entry.rank is not None else ""

    if entry.score is not None:
        if entry.value_format == "hex":
            value_text = format(entry.score, "X")
        else:
            value_text = f"{entry.score:,}"
        if entry.value_prefix:
            value_text = f"{entry.value_prefix}{value_text}"
        if entry.value_suffix:
            if entry.value_suffix.startswith("-"):
                value_text = f"{value_text}{entry.value_suffix}"
            else:
                value_text = f"{value_text} {entry.value_suffix}"
        if not entry.initials:
            return [f"{rank_text}{value_text}".rstrip()]
        return [f"{rank_text}{entry.initials} - {value_text}"]

    if entry.extra_lines:
        if entry.multiline:
            lines = list(entry.extra_lines)
            if lines and rank_text:
                lines[0] = f"{rank_text}{lines[0]}".rstrip()
            return lines
        if not entry.initials:
            return [f"{rank_text}{' | '.join(entry.extra_lines)}".rstrip()]
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
            if entry.section:
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
        "twenty4_150": "/home/superhac/tables/24 (Stern 2009)/pinmame/nvram/twenty4_150.nv",
        "ww_lh6": "/home/superhac/tables/White Water (Williams 1993)/pinmame/nvram/ww_lh6.nv",
        "wwfr_106":"/home/superhac/tables/WWF Royal Rumble (Data East 1994)/pinmame/nvram/wwfr_106.nv",
        "dvlsdre":"/home/superhac/tables/Devils Dare (Gottlieb 1982)/pinmame/nvram/dvlsdre.nv",
        "dollyptb": "/home/superhac/tables/Dolly Parton (Bally 1979)/pinmame/nvram/dollyptb.nv",
        "comet_l5":"/home/superhac/tables/Miami Vice (Original 2020)/pinmame/nvram/comet_l5.nv",
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
