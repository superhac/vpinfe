from __future__ import annotations

import json
import logging

from common.games.collections_service import (
    filter_games_by_collection,
    get_collection_names,
    save_filter_collection,
)
from common.games.game_metadata import (
    game_title,
    get_or_create_user_meta,
    load_game_meta,
    normalize_meta,
    normalize_rating,
    persist_game_meta,
    reorder_leading_article,
    section,
    vpinfe_section,
)
from common.games.gamelistfilters import GameListFilters
from common.media_paths import game_media_payload
from common.shared_assets import manufacturer_logo_web_path
from frontend.theme_contract import CURRENT_CONTRACT, project

logger = logging.getLogger("vpinfe.frontend.game_state")




def default_filter_state():
    return {
        "letter": None,
        "theme": None,
        "type": None,
        "manufacturer": None,
        "year": None,
        "rating": None,
        "rating_or_higher": False,
    }


def default_sort_order(sort_type):
    return "Descending"


def normalize_sort_order(order_by, sort_type="Alpha"):
    value = str(order_by or "").strip().lower()
    if value in ("ascending", "asc"):
        return "Ascending"
    if value in ("descending", "desc"):
        return "Descending"
    return default_sort_order(sort_type)


def games_json(games, contract: int = CURRENT_CONTRACT) -> str:
    result = []
    logo_cache: dict[str, str | None] = {}
    for game in games:
        # A copy: what follows adds fields the theme contract defines, and writing those
        # into the shared metaConfig would put a dropped section back on disk at the next
        # rebuild.
        meta = dict(normalize_meta(game.metaConfig))

        vpinfe = vpinfe_section(meta)
        info = section(meta, "Info")
        used_alttitle = False
        if str(vpinfe.get("alt_vpsid", "") or "").strip() and str(vpinfe.get("alt_title", "") or "").strip():
            info["Title"] = str(vpinfe.get("alt_title", "") or "").strip()
            meta["Info"] = info
            used_alttitle = True

        # Reorder a leading "The " on the canonical Info.Title so the theme
        # displays and sorts by the second word, e.g. "The Addams Family" ->
        # "Addams Family, The". A user-set alttitle is left exactly as entered.
        # Idempotent, so the in-place mutation of the shared meta dict is safe.
        if not used_alttitle and info.get("Title"):
            info["Title"] = reorder_leading_article(info["Title"])
            meta["Info"] = info

        row = {
            "tableDirName": game.tableDirName,
            "fullPathTable": game.fullPathTable,
            "fullPathVPXfile": game.fullPathVPXfile,
            "pupPackExists": game.pupPackExists,
            "altColorExists": game.altColorExists,
            "altSoundExists": game.altSoundExists,
            "meta": meta,
        }
        row.update(game_media_payload(game))
        maker = str(info.get("Manufacturer", "") or "")
        if maker not in logo_cache:
            logo_cache[maker] = manufacturer_logo_web_path(maker)
        row["ManufacturerLogoPath"] = logo_cache[maker]
        result.append(project(row, contract))
    return json.dumps(result)


def apply_collection(api, collection):
    api.current_collection = collection
    filtered, filters = filter_games_by_collection(api.allGames, collection)
    api.filteredGames = filtered
    if filters is None:
        api.current_filters = default_filter_state()
        return

    api.current_filters = {
        "letter": filters["letter"],
        "theme": filters["theme"],
        "type": filters["table_type"],
        "manufacturer": filters["manufacturer"],
        "year": filters["year"],
        "rating": filters.get("rating", "All"),
        "rating_or_higher": str(filters.get("rating_or_higher", "false")).lower() in ("1", "true", "yes", "on"),
    }
    api.current_sort = filters["sort_by"]
    api.current_order = normalize_sort_order(filters.get("order_by"), filters["sort_by"])
    api.apply_sort(filters["sort_by"], api.current_order)


def save_current_filter_collection(api, name, letter, theme, game_type, manufacturer, year, sort_by, rating, rating_or_higher, order_by="Descending"):
    save_filter_collection(name, letter, theme, game_type, manufacturer, year, rating, rating_or_higher, sort_by, order_by)
    return {"success": True, "message": f"Filter collection '{name}' saved successfully"}


def filter_options(games):
    filters = GameListFilters(games)
    return {
        "letters": filters.get_available_letters(),
        "themes": filters.get_available_themes(),
        "types": filters.get_available_types(),
        "manufacturers": filters.get_available_manufacturers(),
        "years": filters.get_available_years(),
    }


def apply_filters(api, letter=None, theme=None, game_type=None, manufacturer=None, year=None, rating=None, rating_or_higher=None):
    api.current_collection = None
    updates = {
        "letter": letter,
        "theme": theme,
        "type": game_type,
        "manufacturer": manufacturer,
        "year": year,
        "rating": rating,
    }
    for key, value in updates.items():
        if value is not None:
            api.current_filters[key] = value
    if rating_or_higher is not None:
        api.current_filters["rating_or_higher"] = str(rating_or_higher).strip().lower() in ("1", "true", "yes", "on")

    api.filteredGames = GameListFilters(api.allGames).apply_filters(
        letter=api.current_filters["letter"],
        theme=api.current_filters["theme"],
        game_type=api.current_filters["type"],
        manufacturer=api.current_filters["manufacturer"],
        year=api.current_filters["year"],
        rating=api.current_filters["rating"],
        rating_or_higher=api.current_filters["rating_or_higher"],
    )
    return len(api.filteredGames)


def apply_sort(games, sort_type, order_by=None):
    reverse = normalize_sort_order(order_by, sort_type) == "Descending"
    if sort_type == "Alpha":
        games.sort(key=lambda game: game_title(game).lower(), reverse=reverse)
    elif sort_type == "Newest":
        games.sort(key=lambda game: game_title(game).lower())
        games.sort(key=lambda game: game.creation_time if game.creation_time is not None else 0, reverse=reverse)
    elif sort_type == "LastRun":
        _sort_by_numeric_meta(games, "LastRun", reverse)
    elif sort_type == "Highest StartCount":
        _sort_by_numeric_meta(games, "StartCount", reverse)
    elif sort_type == "RunTime":
        _sort_by_numeric_meta(games, "RunTime", reverse)
    return len(games)


def _paging_group_key(game):
    # Letter groups for alpha paging. Titles starting with a digit or symbol all
    # land in one '#' bucket so a big collection doesn't take several presses to
    # cross the numeric titles.
    title = game_title(game).strip()
    if title and title[0].isalpha():
        return title[0].upper()
    return "#"


def page_jump_index(games, index, direction, sort_type="Alpha", paging_type="alpha", page_size=10):
    """Return the target wheel index for a joypageup/joypagedown press.

    Alpha paging jumps to the first table of the adjacent letter group in the
    current list order. It only applies when the list is title-ordered (Alpha
    sort); otherwise, or when the whole list is one letter group, it falls back
    to numeric paging. Numeric paging steps by pagingsize, capped at half the
    list so a press never wraps past the starting point. All paging is circular.
    """
    count = len(games)
    if count <= 1:
        return 0 if count else index
    index = index % count
    forward = direction != "prev"

    if paging_type == "alpha" and sort_type == "Alpha":
        keys = [_paging_group_key(game) for game in games]
        if len(set(keys)) > 1:
            step = 1 if forward else -1
            pos = (index + step) % count
            while keys[pos] == keys[index]:
                pos = (pos + step) % count
            if not forward:
                # Walked back onto the previous group's last entry; rewind to its first.
                while keys[(pos - 1) % count] == keys[pos] and (pos - 1) % count != index:
                    pos = (pos - 1) % count
            return pos

    step = min(page_size, max(1, count // 2))
    return (index + step) % count if forward else (index - step) % count


def _sort_by_numeric_meta(games, field, reverse):
    games.sort(key=lambda game: game_title(game).lower())
    games.sort(key=lambda game: _numeric_meta_value(game, field), reverse=reverse)


def _numeric_meta_value(game, field):
    meta = normalize_meta(getattr(game, "metaConfig", {}))
    user = section(meta, "User")
    info = section(meta, "Info")
    try:
        value = int(user.get(field, info.get(field, -1 if field == "LastRun" else 0)))
    except (TypeError, ValueError):
        value = -1 if field == "LastRun" else 0
    return value


def get_table_rating(games, index):
    try:
        game = games[index]
    except Exception:
        return 0
    return normalize_rating(section(load_game_meta(game), "User").get("Rating", 0))


def set_table_rating(games, index, rating):
    game = games[index]
    config = load_game_meta(game)
    user = get_or_create_user_meta(config)
    normalized = normalize_rating(rating)
    user["Rating"] = normalized
    persist_game_meta(game, config)
    return {"success": True, "rating": normalized}
