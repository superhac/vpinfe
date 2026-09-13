"""VPinPlay's cumulative rating, contributed to every entry.

Core makes the call. This used to be the browser's job - the endpoint was handed to the
page and every window on a cabinet asked the same question about the same game, losing
the answers on each reload. A theme reads `entry.ext.vpinplay`, and `item.vpinplay` is
still written from it for the themes that were built before there was an `ext` slot.

Signing in as a guest lives here too: core keeps the theme methods, because published
themes call them and a method that vanishes breaks a theme, and asks this extension for
the answer behind them. With nothing answering - disabled, failed, never installed - core
says what it said before there was an extension.
"""

from __future__ import annotations

from . import client, guest, sync

# What the setting is called here. Core handed it over from its own configuration when
# this extension first loaded, so an install that was already using VPinPlay finds it
# already set.
ENDPOINT_KEY = "endpoint"
USER_KEY = "user_id"
INITIALS_KEY = "initials"
MACHINE_KEY = "machine_id"
SYNC_ON_EXIT_KEY = "sync_on_exit"

# Where VPinPlay lives unless somebody has said otherwise. The same default core carried,
# so an install that never changed it needs nothing handed over at all.
DEFAULT_ENDPOINT = "https://api.vpinplay.com:8888"


def _truthy(value) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def register(ctx) -> None:
    def rating_for(game):
        """What VPinPlay says about one game, or None.

        Keyed on the catalog id, because that is what VPinPlay knows a table by. A game
        no catalog has matched has nothing to ask about, which is not a failure.
        """
        vps_id = str(game.get("vps_id") or "").strip()
        if not vps_id:
            return None
        endpoint = ctx.config.get(ENDPOINT_KEY, "") or DEFAULT_ENDPOINT
        return client.fetch(endpoint, vps_id)

    ctx.entries.contribute("vpinplay", rating_for)

    def _record_play(game_key: str, elapsed_seconds: float, score_data=None) -> bool:
        """One finished session, where a guest is playing. Answers whether it was taken.

        False when nobody is signed in, which is how core knows to write the session to
        the game's own record instead - a visitor's half hour must not land in the play
        count of a library that is not theirs.
        """
        profile = guest.get_active_profile()
        if profile is None:
            return False
        guest.add_game_runtime(game_key, elapsed_seconds, profile.profile_key)
        if score_data:
            guest.set_game_score(game_key, score_data, profile.profile_key)
        return True

    def _record_start(game_key: str) -> bool:
        """A session beginning, where a guest is playing. Answers whether it was taken."""
        profile = guest.get_active_profile()
        if profile is None:
            return False
        guest.record_game_start(game_key)
        return True

    # What core keeps a method for and no longer knows the answer to. A guest is signed
    # in against VPinPlay's identity - a user id, initials and a machine id - so who is
    # playing is this extension's question even though a theme has always asked core.
    ctx.serves.answer("guest.state", guest.get_alternate_profile_state)
    ctx.serves.answer("guest.activate", guest.activate_alternate_profile)
    ctx.serves.answer("guest.clear", guest.clear_alternate_profile)
    ctx.serves.answer("guest.active", guest.get_active_profile)
    ctx.serves.answer("guest.record_play", _record_play)
    ctx.serves.answer("guest.record_start", _record_start)
    def _who() -> tuple[str, str, str, str]:
        """The four settings a sync needs, as this install has them."""
        return (str(ctx.config.get(ENDPOINT_KEY, "") or DEFAULT_ENDPOINT),
                str(ctx.config.get(USER_KEY, "") or ""),
                str(ctx.config.get(INITIALS_KEY, "") or ""),
                str(ctx.config.get(MACHINE_KEY, "") or ""))

    def _sync_library(timeout_seconds: int = sync.ASKED_TIMEOUT) -> dict | None:
        """Tell VPinPlay what is here and what has been played on it.

        The library arrives through the context. The version of this in core enumerated
        it directly, which is the dependency the architecture notes named: the online
        client reaching down into games.
        """
        endpoint, user_id, initials, machine_id = _who()
        missing = [name for name, value in (("a service address", endpoint),
                                            ("a user id", user_id),
                                            ("initials", initials),
                                            ("a machine id", machine_id)) if not value]
        if missing:
            ctx.logger.info("Not syncing: VPinPlay still needs %s", ", ".join(missing))
            return None

        games, skipped = [], 0
        for game in ctx.games.list_games(q="", limit=0, offset=0)["games"]:
            tables = ctx.games.game_tables(game["id"])["tables"]
            default = next((one for one in tables if one.get("default")),
                           tables[0] if tables else None)
            built = sync.payload_for(game, default)
            if built is None:
                skipped += 1
                continue
            games.append(built)

        payload = sync.envelope(user_id, initials, machine_id, games,
                                ctx.host_version, sync.now())
        where = sync.endpoint_for(endpoint)
        ctx.logger.info("Syncing %s of %s games to %s", len(games),
                        len(games) + skipped, where)
        return {"games_sent": len(games), "games_skipped": skipped,
                **sync.send(where, payload, timeout_seconds)}

    def _sync_on_exit() -> dict | None:
        """What core asks for on the way down, if this install wants it."""
        if not _truthy(ctx.config.get(SYNC_ON_EXIT_KEY, "")):
            return None
        return _sync_library(sync.SHUTDOWN_TIMEOUT)

    ctx.serves.answer("sync.library", _sync_library)
    ctx.serves.answer("sync.on_exit", _sync_on_exit)

    ctx.serves.answer("guest.choose", guest.set_active_profile)
    ctx.serves.answer("guest.check", guest.validate_profile_payload)

    def _record_start(game_key: str) -> bool:
        """A session beginning, where a guest is playing. Answers whether it was taken."""
        profile = guest.get_active_profile()
        if profile is None:
            return False
        guest.record_game_start(game_key)
        return True

    # What core keeps a method for and no longer knows the answer to. A guest is signed
    # in against VPinPlay's identity - a user id, initials and a machine id - so who is
    # playing is this extension's question even though a theme has always asked core.

    ctx.logger.info("Contributing ratings from %s",
                    ctx.config.get(ENDPOINT_KEY, "") or DEFAULT_ENDPOINT)
