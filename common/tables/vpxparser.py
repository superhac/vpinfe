#!/usr/bin/env python3
import argparse
import logging
import olefile
import json
import struct
import hashlib
import os
import re
import csv
import pathlib
import sys


logger = logging.getLogger("vpinfe.common.tables.vpxparser")


class VPXParser:
    sys.setrecursionlimit(10000)  # increase recursion limit for large OLE files

    logger = None

    vpxPaths = {
        'table_name': 'tableinfo/tablename',
        'version': 'tableinfo/tableversion',
        'author_name': 'tableinfo/authorname',
        'release_date': 'tableinfo/releasedate',
        'table_blurb': 'tableinfo/tableblurb',
        'table_rules': 'tableinfo/tablerules',
        'save_date': 'tableinfo/tablesavedate',
        'save_rev': 'tableinfo/tablesaverev',
        'manufacturer': 'tableinfo/companyname',
        'year': 'tableinfo/companyyear',
        'type': 'tableinfo/tabletype',
        'table_description': 'tableinfo/tabledescription',
    }

    vpxPathsBinary = {
        'game_data': 'gamestg/gamedata',
        # 'gameStgVersion': 'gamestg/version'
    }

    derivedPaths = {
        'rom': '',
        'filename': '',
        'vbs_hash': '',
        'file_hash': '',
        'detect_fleep': '',
        'detect_nfozzy': '',
        'detect_scorbit': '',
        'detect_ssf': '',
        'detect_fastflips': '',
        'detect_lut': '',
        'detect_flex': '',
        'detect_pinmame': '',
    }

    def __init__(self):
        self.fieldnames = [
            *self.vpxPaths.keys(),
            *self.vpxPathsBinary.keys(),
            *self.derivedPaths.keys()
        ]
        # remove fields not wanted in CSV
        for key in ("game_data", "table_rules", "table_description"):
            if key in self.fieldnames:
                self.fieldnames.remove(key)

    # -------------------------------
    # Helpers
    # -------------------------------
    def decodeBytesToString(self, fileio):
        text = fileio.read().decode("latin-1")
        return text.replace('\x00', '')

    def decodeBytesToInt(self, fileio):
        # not implemented yet
        pass

    def ensure_msdos_line_endings(self, text):
        if "\r\n" in text and "\n" not in text.replace("\r\n", ""):
            return text  # Already correct
        return text.replace("\r\n", "\n").replace("\n", "\r\n")

    def sha256sum(self, filename):
        with open(filename, 'rb', buffering=0) as f:
            return hashlib.file_digest(f, 'sha256').hexdigest()

    def find_code_offset_after(self, data: bytes, word: bytes = b"CODE") -> int:
        index = data.find(word)
        return index + len(word) if index != -1 else -1

    # -------------------------------
    # Loading / extracting
    # -------------------------------
    def loadTableValues(self, vpxFileValues, ole):
        for key, path in self.vpxPaths.items():
            if ole.exists(path):
                with ole.openstream(path) as file:
                    vpxFileValues[key] = self.decodeBytesToString(file)
            else:
                vpxFileValues[key] = ""

    def loadVBCode(self, ole, vpxFileValues):
        with ole.openstream(self.vpxPathsBinary['game_data']) as file:
            data = file.read()

        offset = self.find_code_offset_after(data)
        if offset == -1:
            vpxFileValues['game_data'] = ""
            return

        length = int.from_bytes(data[offset:offset + 4], "little", signed=True)
        vbscript = data[offset + 4:offset + 4 + length].decode("utf-8", errors="ignore")
        vpxFileValues['game_data'] = self.ensure_msdos_line_endings(vbscript)

    def loadSidecarVBCode(self, vpxFile, vpxFileValues):
        vbs_path = pathlib.Path(vpxFile).with_suffix(".vbs")
        if not vbs_path.exists():
            return

        vbscript = vbs_path.read_bytes().decode("utf-8-sig", errors="ignore")
        vpxFileValues['game_data'] = self.ensure_msdos_line_endings(vbscript)

    def calcCodeHash(self, vpxFileValues):
        vpxFileValues['vbs_hash'] = hashlib.sha256(
            vpxFileValues['game_data'].encode("utf-8")
        ).hexdigest()

    def getAllVpxFilesFromDir(self, directory):
        return [str(p) for p in pathlib.Path(directory).glob("*.vpx")]

    def extractFile(self, file):
        vpxFileValues = {
            'filename': os.path.basename(file),
            'file_hash': self.sha256sum(file),
        }

        with olefile.OleFileIO(file) as ole:
            self.loadTableValues(vpxFileValues, ole)
            self.loadVBCode(ole, vpxFileValues)

        self.loadSidecarVBCode(file, vpxFileValues)
        self.calcCodeHash(vpxFileValues)
        self.extractRomName(vpxFileValues)
        self.runDetectors(vpxFileValues)

        return vpxFileValues

    # -------------------------------
    # Printing
    # -------------------------------
    def printFileValues(self, vpxFileValues):
        for key, value in vpxFileValues.items():
            if key in ('game_data', 'table_rules', 'table_description'):
                preview = (value[:50] + "....") if value else ""
                logger.info("%s: \"%s\"", key, preview)
            else:
                logger.info("%s: \"%s\"", key, value)

    # -------------------------------
    # Extraction helpers
    # -------------------------------
    @staticmethod
    def stripVBScriptComments(script):
        lines = []
        for line in script.splitlines():
            code = []
            in_string = False
            i = 0
            while i < len(line):
                char = line[i]
                if char == '"':
                    code.append(char)
                    if in_string and i + 1 < len(line) and line[i + 1] == '"':
                        code.append(line[i + 1])
                        i += 2
                        continue
                    in_string = not in_string
                elif char == "'" and not in_string:
                    break
                else:
                    code.append(char)
                i += 1
            lines.append("".join(code))
        return "\n".join(lines)

    def extractRomName(self, vpxFileValues):
        game_data = self.stripVBScriptComments(vpxFileValues['game_data'])
        m = re.search(r'(?i)c?gamename\s*=\s*"([^"]+)"', game_data)
        m_opt = re.search(r'(?i)c?OptRom\s*=\s*"([^\s]+)"', game_data)

        if m:
            vpxFileValues['rom'] = m.group(1)
        elif m_opt:
            vpxFileValues['rom'] = m_opt.group(1)
        else:
            vpxFileValues['rom'] = ""

    def runDetectors(self, vpxFileValues):
        game_data_lower = vpxFileValues['game_data'].lower()
        detectors = {
            'detect_nfozzy': 'class flipperpolarity',
            'detect_fleep': 'rubberstrongsoundfactor',
            'detect_ssf': 'playsoundat',
            'detect_lut': 'lut',
            'detect_scorbit': 'scorebit',
            'detect_fastflips': 'fastflips',
            'detect_flex': 'flexdmd',
        }
        for key, token in detectors.items():
            vpxFileValues[key] = "true" if token in game_data_lower else "false"

        # Whether the script drives the PinMAME emulator, as opposed to declaring a
        # rom name only as a DOF key. On the comment-stripped script, unlike the
        # detectors above: EM tables commonly carry commented-out VPM code, and a
        # dead LoadVPM must not read as a live dependency.
        stripped_lower = self.stripVBScriptComments(vpxFileValues['game_data']).lower()
        drives_pinmame = ("loadvpm" in stripped_lower
                          or "vpminit" in stripped_lower
                          or re.search(r'createobject\s*\(\s*"vpinmame\.controller"',
                                       stripped_lower) is not None)
        vpxFileValues['detect_pinmame'] = "true" if drives_pinmame else "false"

    # -------------------------------
    # Bulk ops
    # -------------------------------
    def singleFileExtract(self, vpxFile):
        if not os.path.exists(vpxFile):
            logger.warning("File not found: %s", vpxFile)
            return None
        if not olefile.isOleFile(vpxFile):
            logger.warning("Not an OLE file: %s", vpxFile)
            return None
        return self.extractFile(vpxFile)

    def bulkFileExtract(self, vpxFileDir, writer):
        files = self.getAllVpxFilesFromDir(vpxFileDir)
        logger.info("Total Files: %s", len(files))
        for file in files:
            vpxFileValues = self.extractFile(file)
            self.printFileValues(vpxFileValues)
            if writer:
                self.writeCSV(vpxFileValues, writer)

    # -------------------------------
    # CSV / DB ops
    # -------------------------------
    def writeCSV(self, vpxFileValues, writer):
        for key in ("game_data", "table_rules", "table_description"):
            vpxFileValues.pop(key, None)
        writer.writerow(vpxFileValues)

    def openCSV(self, csvOutFile):
        csvFile = open(csvOutFile, 'w', newline='')
        writer = csv.DictWriter(csvFile, fieldnames=self.fieldnames)
        writer.writeheader()
        return csvFile, writer

    def createDBFromDir(self, vpxFileDir, csvOutFile):
        csvFile, writer = self.openCSV(csvOutFile)
        self.bulkFileExtract(vpxFileDir, writer)
        csvFile.close()

    def loadCSV(self, csvInFile):
        with open(csvInFile, 'r', newline='') as f:
            return list(csv.DictReader(f))

    # -------------------------------
    # Matchers
    # -------------------------------
    def findFileSHAMatch(self, tables, vpxFileValues):
        for game in tables:
            if vpxFileValues['file_hash'] == game['file_hash']:
                logger.info("Found FILE hash match.")
                return game
        return None

    def findCodeSHAMatch(self, tables, vpxFileValues):
        for game in tables:
            if vpxFileValues['vbs_hash'] == game['vbs_hash']:
                logger.info("Found CODE hash match.")
                return game
        return None
