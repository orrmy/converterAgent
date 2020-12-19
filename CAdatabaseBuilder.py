#!/usr/bin/python

import os, sqlite3, json, time

import settings
import CAmetadata

countTotal		= 0
countNew		= 0
countChanged	= 0
countMissing	= 0

filesTableInitSQL = """CREATE TABLE IF NOT EXISTS "files" (
	"ID"		INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
	"Path"		TEXT NOT NULL UNIQUE,
	"Filename"	TEXT,
	"Container"	TEXT,
	"Codec"		TEXT,
	"Width"		INTEGER,
	"Height"	INTEGER,
	"Duration"	INTEGER,
	"Size"		INTEGER,
	"Found"		FLOAT,
	"Modified"	FLOAT,
	"Cut" 		INTEGER,
	"Checked" 	INTEGER,
	"Missing"	INTEGER,
	"Error"		INTEGER
)"""

uncutPaths = ("/mnt/Augurinus/PlexDVRSerien", "/mnt/Grumentum/DVR Filme")

def fileInsert( Path=None, Filename="", Container="", Codec="", Width=0, \
				Height=0, Duration=0, Size=0, Found=0.0, Modified=0.0, Cut=0, \
				Checked=0,  Missing=0, Error=0 ):
	global countNew, countChanged
	cursor.execute( 'SELECT * FROM files WHERE Path=?;', (Path,) )
	result = cursor.fetchall()
	if len(result)==0:
		print("new: " + Path)
		countNew += 1
		cursor.execute("INSERT INTO files (Path, Filename, Container, Codec, \
						Width, Height, Duration, Size, Found, Modified, Cut, \
						Checked, Missing, Error) \
						VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", \
						(Path, Filename, Container, Codec, Width, \
						Height, Duration, Size, Found, Modified, Cut, \
						Checked, Missing, Error) )
	else:
		print("changed: " + Path)
		countChanged += 1
		cursor.execute("UPDATE files SET Codec=?, \
						Width=?, Height=?, Duration=?, Size=?, Modified=? \
						WHERE Path=?", \
						(Codec, Width, Height, Duration, Size, Modified, Path) )
	db.commit()

def safeMetadata( metadata, parameters ):
	try:
		result = metadata[parameters[0]][parameters[1]][parameters[2]]
	except (KeyError, IndexError):
		result = None
	#print(result)
	return result

def fileInDB(path):
	cursor.execute("SELECT Size, Modified FROM files WHERE Path=?", (path,))
	DBFileData = cursor.fetchone()
	if DBFileData == (os.path.getsize(path), os.path.getmtime(path)):
		return True
	return False

def findFiles(directory, pattern):
	global countTotal
	#counter = 0
	#print( "\n" + directory ) #debug
	for root, dirs, files in os.walk(directory):
		for basename in files:
			path = os.path.join(root, basename)
			countTotal += 1
			#print (path)
			if basename.endswith(pattern) \
					and not any(string in path for string in settings.ignorePathsWith) \
					and not fileInDB(path):
				metadata = CAmetadata.getMetadata(path)
				if path.startswith(uncutPaths):
					cut = 0
				else:
					cut = 1
				fileInsert( Path 		= path,\
						Filename 	= os.path.basename( path ), \
						Container	= os.path.splitext( path )[1], \
						Codec 		= safeMetadata(metadata, ("streams", 0, "codec_name") ), \
						Width		= safeMetadata(metadata, ("streams", 0, "width") ), \
						Height		= safeMetadata(metadata, ("streams", 0, "height") ), \
						Duration	= safeMetadata(metadata, ("format", "duration") ), \
						Size		= os.path.getsize(path),\
						Found		= time.time(),\
						Modified	= os.path.getmtime(path),\
						Cut=cut, Checked=0,  Missing=0, Error=0 )

def findVersions( path ):
	searchPattern = os.path.splitext( os.path.basename( path ) )[0]
	versions = list(filter(lambda x: searchPattern in x, os.path.dirname(path)))
	versionCount = len( versions )
	return versionCount

def findMissing():
	global countChanged, countMissing
	cursor.execute("SELECT Path FROM files;")
	allfiles = cursor.fetchall()
	for path in allfiles:
		if not os.path.exists( path[0] ):
			if findVersions( path[0] ) > 0:
				cursor.execute( "DELETE FROM files WHERE Path=?;", (path[0],) )
				countChanged += 1
			else:
				cursor.execute( "UPDATE files SET Missing=1 WHERE Path=?;", (path[0],) )
				countMissing += 1
	db.commit()

db = sqlite3.connect( settings.agentName + '.sqlite3' )
cursor = db.cursor()
cursor.execute( filesTableInitSQL )
db.commit()

for lib in settings.inputDirectories:
	findFiles(lib, settings.formatsToConvert )
	findMissing()

print ( str(countTotal) + " files total, " + str(countNew) + " new, " + str(countChanged) + " changed, " + str(countMissing) + " missing." )

