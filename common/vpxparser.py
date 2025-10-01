#!/usr/bin/env python3
import argparse
import olefile
import json
import struct
import hashlib
import os
import re
import csv
import pathlib
import sys


class VPXParser:
    sys.setrecursionlimit(10000)  # increase recursion limit for large OLE files

    logger = None

    vpxPaths = {
        'tableName': 'tableinfo/tablename',
        'tableVersion': 'tableinfo/tableversion',
        'authorName': 'tableinfo/authorname',
        'releaseDate': 'tableinfo/releasedate',
        'tableBlurb': 'tableinfo/tableblurb',
        'tableRules': 'tableinfo/tablerules',
        'tableSaveDate': 'tableinfo/tablesavedate',
        'tableSaveRev': 'tableinfo/tablesaverev',
        'companyName': 'tableinfo/companyname',
        'companyYear': 'tableinfo/companyyear',
        'tableType': 'tableinfo/tabletype',
        'tableDescription': 'tableinfo/tabledescription',
    }

    vpxPathsBinary = {
        'gameData': 'gamestg/gamedata',
        # 'gameStgVersion': 'gamestg/version'
    }

    derivedPaths = {
        'rom': '',
        'filename': '',
        'codeSha256Hash': '',
        'fileHash': '',
        'detectFleep': '',
        'detectNfozzy': '',
        'detectScorebit': '',
        'detectSSF': '',
        'detectFastflips': '',
        'detectLut': '',
        'detectFlex': '',
    }

    def __init__(self):
        self.fieldnames = [
            *self.vpxPaths.keys(),
            *self.vpxPathsBinary.keys(),
            *self.derivedPaths.keys()
        ]
        # remove fields not wanted in CSV
        for key in ("gameData", "tableRules", "tableDescription"):
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
        with ole.openstream(self.vpxPathsBinary['gameData']) as file:
            data = file.read()

        offset = self.find_code_offset_after(data)
        if offset == -1:
            vpxFileValues['gameData'] = ""
            return

        length = int.from_bytes(data[offset:offset + 4], "little", signed=True)
        vbscript = data[offset + 4:offset + 4 + length].decode("utf-8", errors="ignore")
        vpxFileValues['gameData'] = self.ensure_msdos_line_endings(vbscript)

    def calcCodeHash(self, vpxFileValues):
        vpxFileValues['codeSha256Hash'] = hashlib.sha256(
            vpxFileValues['gameData'].encode("utf-8")
        ).hexdigest()

    def getAllVpxFilesFromDir(self, directory):
        return [str(p) for p in pathlib.Path(directory).glob("*.vpx")]

    def extractFile(self, file):
        vpxFileValues = {
            'filename': os.path.basename(file),
            'fileHash': self.sha256sum(file),
        }

        with olefile.OleFileIO(file) as ole:
            self.loadTableValues(vpxFileValues, ole)
            self.loadVBCode(ole, vpxFileValues)

        self.calcCodeHash(vpxFileValues)
        self.extractRomName(vpxFileValues)
        self.runDetectors(vpxFileValues)

        return vpxFileValues

    # -------------------------------
    # Printing
    # -------------------------------
    def printFileValues(self, vpxFileValues):
        for key, value in vpxFileValues.items():
            if key in ('gameData', 'tableRules', 'tableDescription'):
                preview = (value[:50] + "....") if value else ""
                print(f"{key}: \"{preview}\"")
            else:
                print(f"{key}: \"{value}\"")

    # -------------------------------
    # Extraction helpers
    # -------------------------------
    def extractRomName(self, vpxFileValues):
        game_data = vpxFileValues['gameData']
        m = re.search(r'(?i)c?gamename\s*=\s*"([^"]+)"', game_data)
        m_opt = re.search(r'(?i)c?OptRom\s*=\s*"([^\s]+)"', game_data)

        if m:
            vpxFileValues['rom'] = m.group(1)
        elif m_opt:
            vpxFileValues['rom'] = m_opt.group(1)
        else:
            vpxFileValues['rom'] = ""

    def runDetectors(self, vpxFileValues):
        game_data_lower = vpxFileValues['gameData'].lower()
        detectors = {
            'detectNfozzy': 'class flipperpolarity',
            'detectFleep': 'rubberstrongsoundfactor',
            'detectSSF': 'playsoundat',
            'detectLut': 'lut',
            'detectScorebit': 'scorebit',
            'detectFastflips': 'fastflips',
            'detectFlex': 'flexdmd',
        }
        for key, token in detectors.items():
            vpxFileValues[key] = "true" if token in game_data_lower else "false"

    # -------------------------------
    # Bulk ops
    # -------------------------------
    def singleFileExtract(self, vpxFile):
        if not os.path.exists(vpxFile):
            print(f"File not found: {vpxFile}")
            return None
        if not olefile.isOleFile(vpxFile):
            print(f"Not an OLE file: {vpxFile}")
            return None
        return self.extractFile(vpxFile)

    def bulkFileExtract(self, vpxFileDir, writer):
        files = self.getAllVpxFilesFromDir(vpxFileDir)
        print(f"Total Files: {len(files)}")
        for file in files:
            vpxFileValues = self.extractFile(file)
            self.printFileValues(vpxFileValues)
            if writer:
                self.writeCSV(vpxFileValues, writer)

    # -------------------------------
    # CSV / DB ops
    # -------------------------------
    def writeCSV(self, vpxFileValues, writer):
        for key in ("gameData", "tableRules", "tableDescription"):
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
        for table in tables:
            if vpxFileValues['fileHash'] == table['fileHash']:
                print("Found FILE hash match.")
                return table
        return None

    def findCodeSHAMatch(self, tables, vpxFileValues):
        for table in tables:
            if vpxFileValues['codeSha256Hash'] == table['codeSha256Hash']:
                print("Found CODE hash match.")
                return table
        return None
