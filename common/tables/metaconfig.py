import json
import logging
import os
import uuid
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger("vpinfe.common.tables.metaconfig")

# Schema version for the VPinFE section only - we own those keys outright, so their
# shape can be reasoned about from a version. Other sections stay shape-driven.
#   1  original shape (deletedNVRamOnClose, altlauncher, pluginprofile, alttitle,
#      altvpsid). Implied when no version is recorded.
#   2  adds `id`, the stable local table id (see common/table_identity.py).
CURRENT_VPINFE_SCHEMA = 2
VPINFE_SCHEMA_KEY = "schema"

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
                "Table metadata uses VPinFE schema %s, newer than this build's %s. "
                "Leaving it untouched; unknown settings are preserved.",
                version, CURRENT_VPINFE_SCHEMA,
            )
        return vpinfe

    if version < 2:
        vpinfe.setdefault("id", "")  # declare only; minting is a writer's job

    vpinfe[VPINFE_SCHEMA_KEY] = CURRENT_VPINFE_SCHEMA
    return vpinfe


class InvalidMetaConfigError(ValueError):
    """Raised when a table .info file exists but cannot be read as metadata."""

    def __init__(self, path, reason):
        self.path = path
        self.reason = reason
        super().__init__(f"Invalid table metadata file: {path} ({reason})")


class MetaConfig:
    PINBALL_PRIMER_PREFIX = "https://pinballprimer.github.io/"
    DETECT_KEY_MAP = {
        "detectNfozzy": "detectnfozzy",
        "detectFleep": "detectfleep",
        "detectSSF": "detectssf",
        "detectLUT": "detectlut",
        "detectScorebit": "detectscorebit",
        "detectFastflips": "detectfastflips",
        "detectFlex": "detectflex",
    }

    def __init__(self, configfilepath):
        self.configFilePath = configfilepath
        self.data = {}

        if os.path.exists(configfilepath):
            try:
                if os.path.getsize(configfilepath) == 0:
                    raise InvalidMetaConfigError(configfilepath, "file is empty")
                with open(configfilepath, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except json.JSONDecodeError as exc:
                reason = f"invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}"
                raise InvalidMetaConfigError(configfilepath, reason) from exc
        else:
            self.data = {}
        self._normalize_detection_flags()
        self._migrate_vpinfe()

    def writeConfigMeta(self, configdata):
        """
        Build the .info JSON structure
        """
        existing_vpxfile = self.data.get("VPXFile", {})
        if not isinstance(existing_vpxfile, dict):
            existing_vpxfile = {}
        existing_filehash = str(existing_vpxfile.get("filehash", "") or "").strip()
        new_filehash = str(configdata.get("vpxdata", {}).get("fileHash", "") or "").strip()
        pinball_primer_tutorial = self._find_pinball_primer_tutorial(
            configdata.get("vpsdata", {})
        )

        info = {
            "IPDBId": parse_qs(urlparse(configdata.get("vpsdata", {}).get("ipdbUrl", "")).query).get("id", [""])[0],
            "Title": configdata.get("vpsdata", {}).get("name", ""),
            "Manufacturer": configdata.get("vpsdata", {}).get("manufacturer", ""),
            "Year": configdata.get("vpsdata", {}).get("year", ""),
            "Type": configdata.get("vpsdata", {}).get("type", ""),
            "Themes": configdata.get("vpsdata", {}).get("theme", []),
            "VPSId": configdata.get("vpsdata", {}).get("id", ""),
            "Authors": self._parse_authors(
                configdata.get("vpxdata", {}).get("authorName", "")
            ),
            "Rom": configdata.get("vpxdata", {}).get("rom", ""),
        }
        if pinball_primer_tutorial:
            info["PinballPrimerTut"] = pinball_primer_tutorial

        vpxfile = {
            "filename": configdata["vpxdata"]["filename"],
            "filehash": configdata["vpxdata"]["fileHash"],
            "version": configdata["vpxdata"]["tableVersion"],
            "releaseDate": configdata["vpxdata"]["releaseDate"],
            "saveDate": configdata["vpxdata"]["tableSaveDate"],
            "saveRev": configdata["vpxdata"]["tableSaveRev"],
            "manufacturer": configdata["vpxdata"]["companyName"],
            "year": configdata["vpxdata"]["companyYear"],
            "type": configdata["vpxdata"]["tableType"],
            "vbsHash": configdata["vpxdata"]["codeSha256Hash"],
            "rom": configdata["vpxdata"]["rom"],
            "detectnfozzy": configdata["vpxdata"]["detectnfozzy"],
            "detectfleep": configdata["vpxdata"]["detectfleep"],
            "detectssf": configdata["vpxdata"]["detectssf"],
            "detectlut": configdata["vpxdata"]["detectlut"],
            "detectscorebit": configdata["vpxdata"]["detectscorebit"],
            "detectfastflips": configdata["vpxdata"]["detectfastflips"],
            "detectflex": configdata["vpxdata"]["detectflex"],
            "detectpinmame": configdata["vpxdata"].get("detectpinmame", "")
        }

        user = self.data.get("User", {
            "Rating": 0,
            "Favorite": 0,
            "LastRun": None,
            "StartCount": 0,
            "RunTime": 0,
            "Tags": [],
            "FrontendDOFEvent": ""
        })
        if not isinstance(user, dict):
            user = {}
        user.setdefault("Rating", 0)
        user.setdefault("Favorite", 0)
        user.setdefault("LastRun", None)
        user.setdefault("StartCount", 0)
        user.setdefault("RunTime", 0)
        user.setdefault("Tags", [])
        user.setdefault("FrontendDOFEvent", "")

        vpinfe = self.data.get("VPinFE", {})
        if not isinstance(vpinfe, dict):
            vpinfe = {}
        vpinfe = migrate_vpinfe_section(vpinfe)
        vpinfe.setdefault("deletedNVRamOnClose", False)
        vpinfe.setdefault("altlauncher", "")
        vpinfe.setdefault("pluginprofile", "")
        vpinfe.setdefault("alttitle", "")
        # Outside the filehash check below on purpose: the id must survive the table
        # file changing, which is exactly when altvpsid is cleared.
        if not str(vpinfe.get("id", "") or "").strip():
            vpinfe["id"] = uuid.uuid4().hex
        if existing_filehash and new_filehash and existing_filehash != new_filehash:
            vpinfe["altvpsid"] = ""
        else:
            vpinfe.setdefault("altvpsid", "")

        medias = self.data.get("Medias", {})
        game_files = self.data.get("GameFiles", {})

        # Preserve any top-level sections we don't manage (e.g. metadata written by
        # other tools sharing the .info file) instead of dropping them on rebuild.
        preserved = {
            k: v
            for k, v in self.data.items()
            if k not in ("Info", "User", "VPXFile", "VPinFE", "Medias", "GameFiles")
        }

        self.data = {
            "Info": info,
            "User": user,
            "VPXFile": vpxfile,
            "VPinFE": vpinfe,
            "Medias": medias,
            "GameFiles": game_files,
            **preserved
        }

        self.writeConfig()

    def writeConfig(self):
        self._normalize_detection_flags()
        os.makedirs(os.path.dirname(self.configFilePath), exist_ok=True)
        with open(self.configFilePath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=4)

    def getConfig(self):
        return self.data

    def strip_all_newlines(self, text):
        return text.replace("\r\n", "").replace("\n", "")

    def gameFileSettings(self):
        """Per-game-file settings, keyed by filename. A folder can hold several builds
        of one table - desktop, VR, a patched variant - and they are peers."""
        settings = self.data.get("GameFiles")
        return settings if isinstance(settings, dict) else {}

    def setGameFileHidden(self, filename, hidden):
        """Hide a game file from the frontend, or unhide it.

        Hiding never deletes. A patch base has to stay on disk - the patched table
        cannot be rebuilt without it - it just should not be offered as something to
        play. The same applies to a variant someone may want back later.
        """
        settings = self.data.setdefault("GameFiles", {})
        entry = settings.setdefault(filename, {})
        if hidden:
            entry["hidden"] = True
        else:
            entry.pop("hidden", None)
            if not entry:
                settings.pop(filename, None)
        self.writeConfig()

    def addMedia(self, mediaType, source, path, md5hash):
        """Record a downloaded media entry in the Medias section."""
        self.data.setdefault("Medias", {})[mediaType] = {
            "Source": source,
             "Path": os.path.basename(path),
            "MD5Hash": md5hash
        }
        self.writeConfig()

    def removeMedia(self, mediaType):
        """Remove a media entry from the Medias section."""
        medias = self.data.get("Medias", {})
        if not isinstance(medias, dict):
            return False
        if mediaType not in medias:
            return False
        medias.pop(mediaType, None)
        self.writeConfig()
        return True

    def getMedia(self, mediaType):
        """Return the Medias entry for a given type, or None."""
        return self.data.get("Medias", {}).get(mediaType)

    def _parse_authors(self, value):
        if not value:
            return []
        return [a.strip() for a in value.split(",") if a.strip()]

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
        vpinfe = self.data.get("VPinFE")
        if isinstance(vpinfe, dict):
            self.data["VPinFE"] = migrate_vpinfe_section(vpinfe)

    def _to_bool(self, val):
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.strip().lower() in ("true", "1", "yes", "on")
        return val == 1

    def _normalize_detection_flags(self):
        if not isinstance(self.data, dict):
            return
        vpx = self.data.get("VPXFile")
        if not isinstance(vpx, dict):
            return

        for mixed_key, lower_key in self.DETECT_KEY_MAP.items():
            if lower_key in vpx:
                raw_val = vpx.get(lower_key)
            else:
                raw_val = vpx.get(mixed_key, False)
            vpx[lower_key] = self._to_bool(raw_val)
            vpx.pop(mixed_key, None)

        
