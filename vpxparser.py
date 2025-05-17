#!/usr/bin/env python3

import argparse
import olefile
import json
import struct
import hashlib
import os, glob
import re
import csv
import pathlib
import sys

from logger import get_logger, init_logger, update_logger_config

class VPXParser:

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
		'tableDescription': 'tableinfo/tabledescription'
		}

	vpxPathsBinary = {
		'gameData': 'gamestg/gamedata',
		#'gameStgVersion': 'gamestg/version' # this is an int32
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
		'detectFlex': ''
	}

	fieldnames = None

	def __init__(self):
		global logger
		logger = get_logger()

		self.fieldnames = [key for key in self.vpxPaths] + [key for key in self.vpxPathsBinary] + [key for key in self.derivedPaths]
		self.fieldnames.remove("gameData") # we don't want these in CSV
		self.fieldnames.remove("tableRules")
		self.fieldnames.remove("tableDescription")

	def decodeBytesToString(self, fileio):
		str = fileio.read().decode("latin-1")
		return str.replace('\x00', '')

	def decodeBytesToInt(self, fileio):
		pass

	def loadTableValues(self, vpxFileValues, ole):
		for key,value in self.vpxPaths.items():
			if ole.exists(value):
				with ole.openstream(value) as file:
					vpxFileValues[key] = self.decodeBytesToString(file)
			else:
				vpxFileValues[key] = "" # make it empty but there

	def printFileValues(self, vpxFileValues):
		for key,value in vpxFileValues.items():
			if(key != 'gameData' and key != 'tableRules' and key != 'tableDescription' ):
				logger.debug(f"{key}: \"{value}\"")
			else:
				logger.debug(f"{key}: \"{value:.5}....\"")

	def loadVBCode(self, ole, vpxFileValues):
		with ole.openstream(self.vpxPathsBinary['gameData']) as file:
			data = file.read()

		offset = self.find_code_offset_after(data)
		length = int.from_bytes(data[offset:offset + 4], byteorder="little", signed=True) # gets the size of vbscript file
		vbscript = data[offset+4:offset+4+length] # slice out the vbscript
		vbscript = vbscript.decode('utf-8', errors="ignore")
		vbscript = self.ensure_msdos_line_endings(vbscript)
		vpxFileValues['gameData'] = vbscript

	def find_code_offset_after(self, data: bytes, word: bytes = b"CODE") -> int:
		index = data.find(word)
		if index != -1:
			return index + len(word)
		return -1  # Return -1 if the word is not found

	def calcCodeHash(self, vpxFileValues):
		vpxFileValues['codeSha256Hash'] = hashlib.sha256(vpxFileValues['gameData'].encode("utf-8")).hexdigest()
		#logger.debug(f"{vpxFileValues['codeSha256Hash']}, {vpxFileValues['tableName']}")

	def ensure_msdos_line_endings(self, text):
		if "\r\n" in text and "\n" not in text.replace("\r\n", ""):
			return text  # Already in MSDOS format, return as is
		return text.replace("\r\n", "\n").replace("\n", "\r\n")  # Normalize to MSDOS

	def sha256sum(self, filename):
		with open(filename, 'rb', buffering=0) as f:
			return hashlib.file_digest(f, 'sha256').hexdigest()

	def getAllVpxFilesFromDir(self, dir):
		files = []
		for file in glob.glob(dir + '/' + "*.vpx"):
			files.append(file)
		return files

	def extractFile(self, file):
		vpxFileValues = {}
		vpxFileValues['filename'] = os.path.basename(file)
		vpxFileValues['fileHash'] = self.sha256sum(file)
		ole = olefile.OleFileIO(file)
		self.loadTableValues(vpxFileValues, ole)
		self.loadVBCode(ole, vpxFileValues)
		self.calcCodeHash(vpxFileValues)
		self.extractRomName(vpxFileValues)
		self.extractDetectNFozzy(vpxFileValues)
		self.extractDetectFleep(vpxFileValues)
		self.extractDetectSSF(vpxFileValues)
		self.extractDetectLut(vpxFileValues)
		self.extractDetectScorebit(vpxFileValues)
		self.extractDetectFastflips(vpxFileValues)
		self.extractDetectFlex(vpxFileValues)
		ole.close()
		return vpxFileValues

	def extractRomName(self, vpxFileValues):
		m = re.search(r'(?i).*c?gamename\s*=\s*"([^"]+)"', vpxFileValues['gameData'])
		try:
			vpxFileValues['rom'] = m.group(1)
		except AttributeError:
			vpxFileValues['rom'] = ""
			logger.debug("No rom found.")

	def extractDetectNFozzy(self, vpxFileValues):
		if 'Class FlipperPolarity' in vpxFileValues['gameData']:
		#if 'Class CoRTracker' in vpxFileValues['gameData']:
			vpxFileValues['detectNfozzy'] = "true"
			logger.debug("NFozzy detected.")
		else:
			vpxFileValues['detectNfozzy'] = "false"

	def extractDetectFleep(self, vpxFileValues):
		#if 'fleep' in vpxFileValues['gameData'].lower():
		if 'RubberStrongSoundFactor'.lower() in vpxFileValues['gameData'].lower():
			vpxFileValues['detectFleep'] = "true"
			logger.debug("Fleep detected.")
		else:
			vpxFileValues['detectFleep'] = "false"

	def extractDetectSSF(self, vpxFileValues):
		if 'PlaySoundAt'.lower() in vpxFileValues['gameData'].lower():
			vpxFileValues['detectSSF'] = "true"
			logger.debug("SSF detected.")
		else:
			vpxFileValues['detectSSF'] = "false"

	def extractDetectLut(self, vpxFileValues):
		if 'lut'.lower() in vpxFileValues['gameData'].lower():
			vpxFileValues['detectLut'] = "true"
			logger.debug("LUT detected.")
		else:
			vpxFileValues['detectLut'] = "false"

	def extractDetectScorebit(self, vpxFileValues):
		if 'Scorebit'.lower() in vpxFileValues['gameData'].lower():
			vpxFileValues['detectScorebit'] = "true"
			logger.debug("Scorebit detected.")
		else:
			vpxFileValues['detectScorebit'] = "false"

	def extractDetectFastflips(self, vpxFileValues):
		if 'Fastflips'.lower() in vpxFileValues['gameData'].lower():
			vpxFileValues['detectFastflips'] = "true"
			logger.debug("Fastflips detected.")
		else:
			vpxFileValues['detectFastflips'] = "false"

	def extractDetectFlex(self, vpxFileValues):
		if 'FlexDMD'.lower() in vpxFileValues['gameData'].lower():
			vpxFileValues['detectFlex'] = "true"
			logger.debug("Flex DMD detected.")
		else:
			vpxFileValues['detectFlex'] = "false"

	def singleFileExtract(self, vpxFile):
		if not os.path.exists(vpxFile):
			logger.error(f"File not found: {vpxFile}")
			return None
		if not olefile.isOleFile(vpxFile):
			logger.error(f"Not an OLE file: {vpxFile}")
			return None
		vpxFileValues = self.extractFile(vpxFile)
		#self.printFileValues(vpxFileValues)
		return vpxFileValues

	def bulkFileExtract(self, vpxFileDir, writer):
		files = self.getAllVpxFilesFromDir(vpxFileDir)
		logger.debug(f"Total Files: {len(files)}")
		for file in files:
			vpxFileValues = {}
			self.extractFile(file, vpxFileValues)
			self.printFileValues(vpxFileValues)
			if writer is not None:
				self.writeCSV(vpxFileValues, writer)

	def writeCSV(self, vpxFileValues, writer):
		try:
			vpxFileValues.pop('gameData')
			vpxFileValues.pop('tableRules')
			vpxFileValues.pop('tableDescription')
		except ValueError:
			pass
		writer.writerow(vpxFileValues)

	def openCSV(self, csvOutFile):
		csvFile = open(csvOutFile, 'w', newline='')
		writer = csv.DictWriter(csvFile, fieldnames=self.fieldnames)
		writer.writeheader()
		return csvFile, writer

	def createDBFromDir(self):
		csvFile, writer = self.openCSV(csvOutFile)
		self.bulkFileExtract(vpxFileDir, writer)
		csvFile.close()

	def loadCSV(self, csvInFile):
		tables = {}
		with open(csvInFile, 'r') as f:
			dict_reader = csv.DictReader(f)
			tables = list(dict_reader)
		return tables

	def findFileSHAMatch(self, tables, vpxFileValues):
		for table in tables:
			if (vpxFileValues['fileHash'] == table['fileHash']):
				logger.debug("Found match FILE hash match.")
				return table
		return None

	def findCodeSHAMatch(self, tables, vpxFileValues):
		for table in tables:
			if (vpxFileValues['codeSha256Hash'] == table['codeSha256Hash']):
				logger.debug("Found match CODE hash match.")
				return table
		return None

if __name__ == "__main__":
	logger = init_logger("VPXParser")

	PARSER_CONFIG = {
		"level": "DEBUG",
		"file": None,
		"console": True,
	}
	update_logger_config(PARSER_CONFIG)

	parservpx = VPXParser()

	parser = argparse.ArgumentParser(description='Parse a VPX file.')
	parser.add_argument('--vpxpath', help='Path to the VPX file', default=None)
	parser.add_argument('--vpxdir', help='Path to the directory with all the tables', default=None)
	args = parser.parse_args()

	if args.vpxpath == None:
		vpxFile = '/home/superhac/ROMs/vpinball/Evil Fight (Playmatic 1980).vpx'
	else:
		vpxFile = args.vpxpath

	if args.vpxdir == None:
		vpxFileDir = '/home/superhac/ROMs/vpinball'
	else:
		vpxFileDir = args.vpxdir

	csvOutFile = 'vpxTableDB.csv'
	csvInFile = 'vpxTableDB.csv'

	#tables = parservpx.loadCSV(csvInFile)
	#logger.debug(f"Total Tables in DB: {len(tables)}")
	#vpxFileValues = parservpx.singleFileExtract(vpxFile)
	#table = parservpx.findFileSHAMatch(tables, vpxFileValues)
	#table = parservpx.findCodeSHAMatch(tables, vpxFileValues)
	#logger.debug(table)

	# Brand new master DB creation
	#parservpx.createDBFromDir()

	# testing stuff
	#parservpx.bulkFileExtract(vpxFileDir)
	tableVals = parservpx.singleFileExtract(vpxFile)
	if tableVals != None:
		parservpx.printFileValues(tableVals)
