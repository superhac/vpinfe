import json
import os
from urllib.parse import urlparse, parse_qs

class MetaConfig:
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
            with open(configfilepath, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {}
        self._normalize_detection_flags()

    def writeConfigMeta(self, configdata):
        """
        Build the .info JSON structure
        """
        existing_vpxfile = self.data.get("VPXFile", {})
        if not isinstance(existing_vpxfile, dict):
            existing_vpxfile = {}
        existing_filehash = str(existing_vpxfile.get("filehash", "") or "").strip()
        new_filehash = str(configdata.get("vpxdata", {}).get("fileHash", "") or "").strip()

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
            "Description": self.strip_all_newlines(
                configdata.get("vpxdata", {}).get("tableBlurb", "")
            )
        }

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
            "detectflex": configdata["vpxdata"]["detectflex"]
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
        vpinfe.setdefault("deletedNVRamOnClose", False)
        vpinfe.setdefault("altlauncher", "")
        vpinfe.setdefault("alttitle", "")
        if existing_filehash and new_filehash and existing_filehash != new_filehash:
            vpinfe["altvpsid"] = ""
        else:
            vpinfe.setdefault("altvpsid", "")

        medias = self.data.get("Medias", {})

        self.data = {
            "Info": info,
            "User": user,
            "VPXFile": vpxfile,
            "VPinFE": vpinfe,
            "Medias": medias
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

        
