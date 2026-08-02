import json
import logging
import os
from urllib.parse import parse_qs, urlparse

from common.games.info_migration import (
    migrate,
    needs_migration,
    write_backup,
    write_json_atomic,
)
from common.games.tables import (
    DETECT_KEYS,
    TABLES_KEY,
    default_table,
    entry_from_parsed,
    recorded_default,
    table_entries,
)
from common.timestamps import utc_now_iso

logger = logging.getLogger("vpinfe.common.games.metaconfig")

# Schema version for the VPinFE section only - we own those keys outright, so their
# shape can be reasoned about from a version. Other sections stay shape-driven.
#   1  original shape (deletedNVRamOnClose, altlauncher, pluginprofile, alttitle,
#      altvpsid). Implied when no version is recorded.
#   2  adds `id`, the stable local game id (see common/games/game_identity.py).
CURRENT_VPINFE_SCHEMA = 2
VPINFE_SCHEMA_KEY = "schema"

# The section we own outright: app configuration and game-level bookkeeping. 2.x wrote
# it as `VPinFE`; the migration renames it, since the sections we own are snake_case -
# which it now has.
VPINFE_SECTION = "vpinfe"

# One entry per file VPinFE placed, keyed by the path it was written to. Supersedes
# Medias, which was keyed by media kind and so held at most one entry per kind - it
# could not say which table's wheel it meant once artwork could belong to a
# specific one, and the same question applies to backglasses, ROMs and colorizations.
ASSETS_KEY = "assets"

_warned_newer_schema = set()


def migrate_vpinfe_section(vpinfe):
    """Bring the VPinFE section up to the current schema, in memory.

    Idempotent; the stamp reaches disk on the next write. A section written by a newer
    build is left as-is rather than downgraded.
    """
    if not isinstance(vpinfe, dict):
        return {VPINFE_SCHEMA_KEY: CURRENT_VPINFE_SCHEMA}

    try:
        version = int(vpinfe.get(VPINFE_SCHEMA_KEY, 1) or 1)
    except (TypeError, ValueError):
        version = 1

    if version > CURRENT_VPINFE_SCHEMA:
        if version not in _warned_newer_schema:
            _warned_newer_schema.add(version)
            logger.warning(
                "Game metadata uses VPinFE schema %s, newer than this build's %s. "
                "Leaving it untouched; unknown settings are preserved.",
                version, CURRENT_VPINFE_SCHEMA,
            )
        return vpinfe

    if version < 2:
        vpinfe.setdefault("id", "")  # declare only; minting is a writer's job

    vpinfe[VPINFE_SCHEMA_KEY] = CURRENT_VPINFE_SCHEMA
    return vpinfe


def _default_table_changed(chosen, previous_files, tables):
    """Whether the game's default table is a different file than it was.

    A manual VPS override is tied to the table it was chosen against, so replacing
    that file drops it. Scoped to the default: ADDING a table is not a reason to
    discard the user's match.
    """
    previous_hash = str(previous_files.get(chosen, {}).get("file_hash", "") or "").strip()
    new_hash = str(tables.get(chosen, {}).get("file_hash", "") or "").strip()
    return bool(previous_hash and new_hash and previous_hash != new_hash)


class InvalidMetaConfigError(ValueError):
    """Raised when a game's .info file exists but cannot be read as metadata."""

    def __init__(self, path, reason):
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid table metadata file: {path} ({reason})")


class MetaConfig:
    PINBALL_PRIMER_PREFIX = "https://pinballprimer.github.io/"

    def __init__(self, configfilepath):
        self.configFilePath = configfilepath
        self.data = {}
        # The file as it was found, held only until a write backs it up.
        self._pre_migration = ""

        if os.path.exists(configfilepath):
            try:
                if os.path.getsize(configfilepath) == 0:
                    raise InvalidMetaConfigError(configfilepath, "file is empty")
                with open(configfilepath, encoding="utf-8") as f:
                    original = f.read()
                self.data = json.loads(original)
            except json.JSONDecodeError as exc:
                reason = f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
                raise InvalidMetaConfigError(configfilepath, reason) from exc
            if needs_migration(self.data):
                self._pre_migration = original
                self.data = migrate(self.data)
                logger.info("Migrated %s to schema %s in memory", configfilepath,
                            CURRENT_VPINFE_SCHEMA)
        else:
            self.data = {}
        self._normalize_detection_flags()
        self._migrate_vpinfe()

    @property
    def pending_migration(self) -> bool:
        """Whether this file converted on read and has not been written back yet.

        The lazy path means "has the library converted" has no answer without asking every
        file. This is how the caller asks one.
        """
        return bool(self._pre_migration)

    def writeConfigMeta(self, configdata):
        """
        Build the .info JSON structure
        """
        pinball_primer_tutorial = self._find_pinball_primer_tutorial(
            configdata.get("vpsdata", {})
        )

        # Info is wholly what VPS knows about the machine. Rom and Authors used to be
        # copied in from the parsed .vpx and were per-table values all along - they
        # live on their own tables entry now.
        info = {
            "IPDBId": parse_qs(urlparse(configdata.get("vpsdata", {}).get("ipdbUrl", "")).query).get("id", [""])[0],
            "Title": configdata.get("vpsdata", {}).get("name", ""),
            "Manufacturer": configdata.get("vpsdata", {}).get("manufacturer", ""),
            "Year": configdata.get("vpsdata", {}).get("year", ""),
            "Type": configdata.get("vpsdata", {}).get("type", ""),
            "Themes": configdata.get("vpsdata", {}).get("theme", []),
            "VPSId": configdata.get("vpsdata", {}).get("id", ""),
        }
        if pinball_primer_tutorial:
            info["PinballPrimerTut"] = pinball_primer_tutorial

        user = self.data.get("User", {
            "Rating": 0,
            "Favorite": 0,
            "LastRun": None,
            "StartCount": 0,
            "RunTime": 0,
            "Tags": [],
        })
        if not isinstance(user, dict):
            user = {}
        user.setdefault("Rating", 0)
        user.setdefault("Favorite", 0)
        user.setdefault("LastRun", None)
        user.setdefault("StartCount", 0)
        user.setdefault("RunTime", 0)
        user.setdefault("Tags", [])

        vpinfe = self.data.get(VPINFE_SECTION, {})
        if not isinstance(vpinfe, dict):
            vpinfe = {}
        vpinfe = migrate_vpinfe_section(vpinfe)
        vpinfe.setdefault("delete_nvram_on_close", False)
        vpinfe.setdefault("alt_launcher", "")
        vpinfe.setdefault("plugin_profile", "")
        vpinfe.setdefault("alt_title", "")
        # Configuration, not a play record - see game_metadata.game_frontend_dof_event.
        vpinfe.setdefault("frontend_dof_event", "")
        # Outside the filehash check below on purpose: the id must survive the table
        # changing, which is exactly when alt_vpsid is cleared.
        if not str(vpinfe.get("id", "") or "").strip():
            # Imported here because game_identity reaches back through game_metadata
            # to this module. One minting rule, one place, no cycle.
            from common.games.game_identity import new_id

            vpinfe["id"] = new_id()

        assets = self.data.get(ASSETS_KEY, {})
        previous_files = table_entries(self.data)
        tables = self._build_tables(configdata)

        # Which table a single-table consumer gets - today's themes all assume one game
        # means one table. Resolved fresh here and deliberately NOT written back:
        # seeding it on every rebuild would turn an arbitrary first pick into a
        # permanent one with nothing to change it. The key is written only when
        # somebody chooses (and by the migration, which seeds it from VPXFile.filename
        # so existing games keep selecting exactly what they select today).
        chosen = default_table(tables, "", recorded_default(vpinfe))

        if _default_table_changed(chosen, previous_files, tables):
            vpinfe["alt_vpsid"] = ""
        else:
            vpinfe.setdefault("alt_vpsid", "")

        # Preserve any top-level sections we don't manage (e.g. metadata written by
        # other tools sharing the .info file) instead of dropping them on rebuild.
        # VPXFile and Medias are listed because they are ours and superseded - without
        # them here the old sections would survive as "unmanaged" and be written back
        # forever.
        preserved = {
            k: v
            for k, v in self.data.items()
            if k not in ("Info", "User", "VPXFile", VPINFE_SECTION, "Medias",
                         TABLES_KEY, ASSETS_KEY)
        }

        self.data = {
            "Info": info,
            "User": user,
            VPINFE_SECTION: vpinfe,
            TABLES_KEY: tables,
            ASSETS_KEY: assets,
            **preserved
        }

        self.writeConfig()

    def _build_tables(self, configdata):
        """One entry per parsed table, keyed by filename.

        Callers pass `gamefiles` as {filename: parsed}. `vpxdata` alone is still
        accepted for the single-table case, which is most of the library.

        Anything already recorded against a filename and not covered by the parse -
        the user's `hidden`, a `patch_applied` flag, later play stats and match
        records - survives untouched. Parsed fields are refreshed, so a stale value
        can never outlive what the .vpx actually says.
        """
        parsed_files = configdata.get("gamefiles")
        if not isinstance(parsed_files, dict) or not parsed_files:
            single = configdata.get("vpxdata") or {}
            name = str(single.get("filename", "") or "").strip()
            parsed_files = {name: single} if name else {}

        existing = table_entries(self.data)
        built = {}
        for filename, parsed in parsed_files.items():
            entry = entry_from_parsed(parsed)
            prior = existing.get(filename)
            if isinstance(prior, dict):
                # Refresh what the parse covers; leave everything else alone. Doing it
                # the other way - naming the keys worth keeping - means every field we
                # add later has to be remembered here, and forgetting one silently
                # deletes it on the next rebuild. Play stats and match records are
                # coming; neither should depend on somebody updating a list.
                entry = {**prior, **entry}
            built[filename] = entry
        return built

    def writeConfig(self):
        self._normalize_detection_flags()
        os.makedirs(os.path.dirname(self.configFilePath), exist_ok=True)
        if self._pre_migration:
            # Before the first write of the new shape, and only then: one restore point
            # per schema bump, not one per rebuild. A failure here stops the write - the
            # backup exists for the person who needs to go back, so proceeding without
            # one would take away the only thing that makes this reversible.
            saved = write_backup(self.configFilePath, self._pre_migration)
            self._pre_migration = ""
            logger.info("Kept the pre-migration metadata at %s", saved)
        write_json_atomic(self.configFilePath, self.data)

    def getConfig(self):
        return self.data

    def strip_all_newlines(self, text):
        return text.replace("\r\n", "").replace("\n", "")

    def gameFileSettings(self):
        """Per-table entries, keyed by filename. A folder can hold several tables
        of one game - desktop, VR, a patched variant - and they are peers."""
        return table_entries(self.data)

    def setTableHidden(self, filename, hidden):
        """Hide a table from the frontend, or unhide it.

        Hiding never deletes. A patch base has to stay on disk - the patched table
        cannot be rebuilt without it - it just should not be offered as something to
        play. The same applies to a variant someone may want back later.
        """
        settings = self.data.setdefault(TABLES_KEY, {})
        entry = settings.setdefault(filename, {})
        if hidden:
            entry["hidden"] = True
        else:
            entry.pop("hidden", None)
            # An entry that only ever carried `hidden` came from a table we never
            # parsed; drop it rather than leave an empty record behind.
            if not entry:
                settings.pop(filename, None)
        self.writeConfig()

    def gameFileValue(self, filename, key, default=""):
        """One key off a specific table's entry."""
        value = table_entries(self.data).get(filename, {})
        return value.get(key, default) if isinstance(value, dict) else default

    def setTableValue(self, filename, key, value):
        """Record something we did to a table, against that table."""
        entry = self.data.setdefault(TABLES_KEY, {}).setdefault(filename, {})
        entry[key] = value
        self.writeConfig()

    def refresh_table(self, filename, parsed):
        """Refresh what one table says about itself. Everything else on the entry -
        hidden, where it came from, later play stats - survives, as it does on a full
        rebuild.
        """
        entry = self.data.setdefault(TABLES_KEY, {}).setdefault(filename, {})
        entry.update(entry_from_parsed(parsed))
        self.writeConfig()

    def replace_table(self, removed, filename, parsed):
        """One table replaced another on disk: describe the new one, forget the old.

        A gone table's entry is not kept - its history answers nothing once the file is
        gone. If the default is what changed, the manual VPS override goes with it, the
        same rule a rebuild applies.
        """
        entries = table_entries(self.data)
        # Deep enough to survive the update below: a shallow copy shares the entry dicts,
        # so the "before" would change with the "after" and never look different.
        previous = {name: dict(entry) for name, entry in entries.items()
                    if isinstance(entry, dict)}

        dropped = bool(removed and removed != filename and entries.pop(removed, None))
        if parsed:
            # A failed parse leaves the entry unparsed rather than filled with empties.
            entries.setdefault(filename, {}).update(entry_from_parsed(parsed))
        elif not dropped:
            return      # nothing to say; do not add an empty section to the .info

        self.data[TABLES_KEY] = entries
        vpinfe = self.data.get(VPINFE_SECTION)
        if isinstance(vpinfe, dict):
            chosen = default_table(entries, "", recorded_default(vpinfe))
            if _default_table_changed(chosen, previous, entries):
                vpinfe["alt_vpsid"] = ""
        self.writeConfig()

    def record_patch_source(self, filename, base_file, base_hash, patch_format):
        """Record a table we made ourselves: the base it came from, and the patch that
        made it. An ordinary .vpx has no source, which is the normal case.

        The base is hashed because a .dif applies to one exact file, and the delta's
        format is recorded rather than the code that applied it.
        """
        entry = self.data.setdefault(TABLES_KEY, {}).setdefault(filename, {})
        entry["source"] = {
            "base": {"file": base_file, "hash": base_hash},
            "patch": {"format": patch_format, "applied": utc_now_iso()},
        }
        self.writeConfig()

    def add_asset(self, path, host, md5=""):
        """Record a file we placed, against the path we wrote it to.

        Origin only. What kind of media it is and which table it belongs to are read
        off the filename by resolve_media_files on every run, so a stored copy could
        only ever agree with it or be wrong - and resolution wins either way.
        """
        source = {"host": host}
        if md5:
            source["hash"] = md5
        self.data.setdefault(ASSETS_KEY, {})[self._asset_key(path)] = {"source": source}
        self.writeConfig()

    def _asset_key(self, path):
        """A path relative to the game folder, with forward slashes.

        The .info travels with its folder, so an absolute path stops meaning anything
        the moment the library moves. Separators are normalized because a key written
        on Windows has to match one read on Linux.
        """
        try:
            relative = os.path.relpath(str(path), os.path.dirname(self.configFilePath))
        except ValueError:
            # Different drive on Windows; there is nothing to record but the name.
            relative = os.path.basename(str(path))
        return relative.replace(os.sep, "/")

    def _find_pinball_primer_tutorial(self, vpsdata):
        if not isinstance(vpsdata, dict):
            return ""

        for tutorial in vpsdata.get("tutorialFiles", []):
            if not isinstance(tutorial, dict):
                continue

            direct_url = tutorial.get("url")
            if isinstance(direct_url, str) and direct_url.startswith(self.PINBALL_PRIMER_PREFIX):
                return direct_url

            for entry in tutorial.get("urls", []):
                if not isinstance(entry, dict):
                    continue
                nested_url = entry.get("url")
                if isinstance(nested_url, str) and nested_url.startswith(self.PINBALL_PRIMER_PREFIX):
                    return nested_url

        return ""

    def _migrate_vpinfe(self):
        """Apply the VPinFE section schema migration to the loaded data, in memory."""
        if not isinstance(self.data, dict):
            return
        vpinfe = self.data.get(VPINFE_SECTION)
        if isinstance(vpinfe, dict):
            self.data[VPINFE_SECTION] = migrate_vpinfe_section(vpinfe)

    def _to_bool(self, val):
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() in ("true", "1", "yes", "on")
        return val == 1

    def _normalize_detection_flags(self):
        """Detect flags as real booleans, on every table entry.

        The parser has handed back strings at times, and a JSON "false" is truthy to
        anything that reads it without care.
        """
        for entry in table_entries(self.data).values():
            if not isinstance(entry, dict):
                continue
            for key in DETECT_KEYS:
                if key in entry:
                    entry[key] = self._to_bool(entry[key])
