import json
import os
from urllib.parse import urlparse, parse_qs

class MetaConfig:

    def __init__(self, configfilepath):
        self.configFilePath = configfilepath
        self.data = {}

        if os.path.exists(configfilepath):
            with open(configfilepath, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = {}

    def writeConfigMeta(self, configdata):
        """
        Build the .info JSON structure
        """

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
            "detectNfozzy": configdata["vpxdata"]["detectNfozzy"],
            "detectFleep": configdata["vpxdata"]["detectFleep"],
            "detectSSF": configdata["vpxdata"]["detectSSF"],
            "detectLUT": configdata["vpxdata"]["detectLut"],
            "detectScorebit": configdata["vpxdata"]["detectScorebit"],
            "detectFastflips": configdata["vpxdata"]["detectFastflips"],
            "detectFlex": configdata["vpxdata"]["detectFlex"]
        }

        user = self.data.get("User", {
            "Rating": 0,
            "Favorite": 0,
            "LastRun": None,
            "StartCount": 0,
            "RunTime": 0,
            "Tags": []
        })

        vpinfe = self.data.get("VPinFE", {
            "deletedNVRamOnClose": False
        })

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

    def getMedia(self, mediaType):
        """Return the Medias entry for a given type, or None."""
        return self.data.get("Medias", {}).get(mediaType)

    def _parse_authors(self, value):
        if not value:
            return []
        return [a.strip() for a in value.split(",") if a.strip()]

        