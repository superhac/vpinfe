import olefile
import json
import struct
import hashlib
import os, glob
import re
import csv
import pathlib

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
	'fileHash': ''

}

fieldnames = [key for key in vpxPaths] + [key for key in vpxPathsBinary]  + [key for key in derivedPaths]
fieldnames.remove("gameData") # we don't want these in CSV
fieldnames.remove("tableRules")
fieldnames.remove("tableDescription")

def decodeBytesToString(fileio):
	str = fileio.read().decode("latin-1")
	return str.replace('\x00', '')

def decodeBytesToInt(fileio):
	pass

def loadTableValues(vpxFileValues, ole):
	for key,value in vpxPaths.items():
		if ole.exists(value):
			file = ole.openstream(value)
			vpxFileValues[key] = decodeBytesToString(file)
		else:
			 vpxFileValues[key] = "" # make it empty but there

def printFileValues(vpxFileValues):
	for key,value in vpxFileValues.items():
		if(key != 'gameData' and key != 'tableRules' and key != 'tableDescription' ):
			print("{0}: \"{1}\"".format(key, value))
		else:
			 print("{}: \"{:.5}....\"".format(key, value))
	print()

def loadVBCode(ole, vpxFileValues):
	file = ole.openstream(vpxPathsBinary['gameData'])
	data = file.read() 
             	
	offset = find_code_offset_after(data)
	length = int.from_bytes(data[offset:offset + 4], byteorder="little", signed=True) # gets the size of vbscript file
	vbscript = data[offset+4:offset+4+length] # slice out the vbscript
	vbscript = vbscript.decode('utf-8', errors="ignore")
	vbscript = ensure_msdos_line_endings(vbscript)
	vpxFileValues['gameData'] = vbscript

def find_code_offset_after(data: bytes, word: bytes = b"CODE") -> int:
	index = data.find(word)
	if index != -1:
		return index + len(word)
	return -1  # Return -1 if the word is not found

def calcCodeHash(vpxFileValues):
	vpxFileValues['codeSha256Hash'] = hashlib.sha256(vpxFileValues['gameData'].encode("utf-8")).hexdigest()
	#print(vpxFileValues['codeSha256Hash'], vpxFileValues['tableName'])
	
def ensure_msdos_line_endings(text):
	if "\r\n" in text and "\n" not in text.replace("\r\n", ""):
		return text  # Already in MSDOS format, return as is
	return text.replace("\r\n", "\n").replace("\n", "\r\n")  # Normalize to MSDOS
    
def sha256sum(filename):
    with open(filename, 'rb', buffering=0) as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def getAllVpxFilesFromDir(dir):
	files = []
	for file in glob.glob(dir + '/' + "*.vpx"):
		files.append(file)
	return files

def extractFile(file, vpxFileValues):
	vpxFileValues['filename'] = os.path.basename(file)
	vpxFileValues['fileHash'] = sha256sum(file)
	ole = olefile.OleFileIO(file)
	loadTableValues(vpxFileValues, ole)
	loadVBCode(ole, vpxFileValues)
	calcCodeHash(vpxFileValues)
	extractRomName(vpxFileValues)
	ole.close()

def extractRomName(vpxFileValues):
	m = re.search('(?i).*c?gamename\s*=\s*"([^"]+)"', vpxFileValues['gameData'])
	try:
		vpxFileValues['rom'] = m.group(1)
	except AttributeError:
		vpxFileValues['rom'] = ""
		print("No rom")

def singleFileExtract(vpxFile):
	vpxFileValues = {}
	if olefile.isOleFile(vpxFile):
		extractFile(vpxFile, vpxFileValues)
		#printFileValues(vpxFileValues)
	else:
		sys.exit('Not an OLE file')
	return vpxFileValues

def bulkFileExtract(vpxFileDir, writer):
	files = getAllVpxFilesFromDir(vpxFileDir)
	print("Total Files:", len(files))
	for file in files:
		vpxFileValues = {}
		extractFile(file, vpxFileValues)
		printFileValues(vpxFileValues)
		if writer is not None:
			writeCSV(vpxFileValues, writer)

def writeCSV(vpxFileValues, writer):
	try:
		vpxFileValues.pop('gameData')
		vpxFileValues.pop('tableRules')
		vpxFileValues.pop('tableDescription')
	except ValueError:
		pass
	writer.writerow(vpxFileValues)

def openCSV(csvOutFile):
	csvFile = open(csvOutFile, 'w', newline='')
	writer = csv.DictWriter(csvFile, fieldnames=fieldnames)
	writer.writeheader()
	return writer

def createDBFromDir():
	writer = openCSV(csvOutFile)
	bulkFileExtract(vpxFileDir, writer)

def loadCSV(csvInFile):
	tables = {}
	with open(csvInFile, 'r') as f:
		dict_reader = csv.DictReader(f)
		tables = list(dict_reader)
	return tables

def findFileSHAMatch(tables, vpxFileValues):
	for table in tables:
		if (vpxFileValues['fileHash'] == table['fileHash']):
			print("Found match FILE hash match.")
			return table
	return None

def findCodeSHAMatch(tables, vpxFileValues):
        for table in tables:
                if (vpxFileValues['codeSha256Hash'] == table['codeSha256Hash']):
                        print("Found match CODE hash match.")
                        return table
        return None


if __name__ == "__main__":
	vpxFile = '/home/superhac/ROMs/vpinball/Evil Fight (Playmatic 1980).vpx'
	vpxFileDir = '/home/superhac/ROMs/vpinball'
	#vpxFileDir = '/home/superhac/vhash/myshare/'
	csvOutFile = 'vpxTableDB.csv'
	csvInFile = 'vpxTableDB.csv'

	#tables = loadCSV(csvInFile)
	#print("Total Tables in DB: ", len(tables))
	#vpxFileValues = singleFileExtract(vpxFile)
	#table =findFileSHAMatch(tables, vpxFileValues)
	#table =findCodeSHAMatch(tables, vpxFileValues)
	#print(table)



	# Brand new master DB creation
	#createDBFromDir()

	# testing stuff
	#bulkFileExtract(vpxFileDir)
	tableVals = singleFileExtract(vpxFile)
	printFileValues(tableVals)