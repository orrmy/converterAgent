#!/usr/bin/python

# converterAgent V0.8
# - Settings are now defined in a new way via a configparser .ini file
# - traceback when aborting after errors should work

import os, sys, sqlite3, shutil, re, subprocess, json, pickle, random, configparser, traceback
import traceback
from shlex import quote
from pushover import init, Client

from CAmetadata import getMetadata

# Global Variables
originalMetadata = None
knownFiles		 = {}
doneFiles		 = []

allsettings = configparser.ConfigParser( allow_no_value=True )
allsettings.read("config.ini")
settings = allsettings["GLOBAL SETTINGS"]

conversion = allsettings["DEFAULT"]["conversion"]

# Initializing Pushover Notifications
init("arukijyuq87ry28t5kw33ja3c53ucp")

# Database Connection
db = sqlite3.connect( settings["Library Name"] + '.sqlite3' )
cursor = db.cursor()

def setErrorByPath( path, value ):
    cursor.execute("UPDATE files Set Error=? WHERE Path=?", (value, path))
    db.commit()

def notify( message ):
	if settings["Notifications"] == "yes":
		try:
			Client( settings["pushover User"] ).send_message( "<b>" + settings["Agent Name"] + "</b>:" + message, html=1 )
		except:
			print("Pushover notification failed.")
	else:
		#print( message )
		pass

def getFileToConvert():
	global conversion
	for secName,section in allsettings.items():
		print (section)
		if section["type"] == "selection":
			search = " WHERE "
			for key,value in section.items():
				print( key,value )
				if key == "codecs":
					if search != " WHERE ":
						search = search + " AND "
					search = search + " ( Codec = '" + value.replace("\n", "' OR Codec = '") + "' ) "
				if key == "containers":
					if search != " WHERE ":
						search = search + " AND "
					search = search + " ( Container = '" + value.replace("\n", "' OR Container = '") + "' ) "
				if key == "paths":
					if search != " WHERE ":
						search = search + " AND "
					search = search + " ( Path LIKE '" + value.replace("\n", "%' OR Path  LIKE '") + "%' ) "
				if key == "convert uncut" and value != 'yes':
					if search != " WHERE ":
						search = search + " AND "
					search = search + " Cut=1 "
			if search == " WHERE ":
				continue
			query = "SELECT Path, Codec, Container, Modified, Size FROM files " + search + " AND Error=0 AND Missing=0 ORDER BY RANDOM()"
			print( query )
			cursor.execute( query )
			result = cursor.fetchall()
			if len( result ) != 0:
				for file in result:
					if file[3] == os.path.getmtime(file[0]) and file[4] == os.path.getsize(file[0]):
						print (file[0])
						print ("Settings: " + conversion)
						conversion = section["conversion"]
						return file[0]
	#print( allsettings[section] )
	#print( result[0] )
	sys.exit()
	# while True:
	# 	cursor.execute("SELECT Path, Modified, Size FROM files WHERE (Codec='mpeg2video' OR Container='.ts') AND Cut=1 AND Error=0 ORDER BY RANDOM()")
	# 	files = cursor.fetchall()
	# 	file = files[0]
	# 	print ("Found " + str(len(files)) + " to convert." )
	# 	try:
	# 		# if any(string in file[0] for string in settings.ignorePathsWith):
	# 		# 	break
	# 		if file[1] == os.path.getmtime(file[0]) and file[2] == os.path.getsize(file[0]):
	# 			return file[0]
	# 	except FileNotFoundError:
	# 		pass
	
def generateCommand(filename, deint, newFilename):
	global conversion

	allsettings = configparser.ConfigParser( allow_no_value=True )
	allsettings.read("config.ini")
	convSettings = allsettings[ conversion ]
	if deint != "":
		deint = convSettings["deint Option"]

	return "ffmpeg " + convSettings['ffmpeg input options'] + " -i " \
			+ quote(filename) + " " + deint + " -map 0 " + \
			convSettings['ffmpeg output options'] + " " + \
			quote(newFilename)

def getSortedLibs(unsortedList):
	return sorted(unsortedList, key = lambda e: shutil.disk_usage(e)[2])

def interlaceDetect( filename ):
	duration = float( originalMetadata['format']['duration'] )
	process = subprocess.Popen( ["ffmpeg", "-filter:v", "idet", "-frames:v",\
								"10000", "-an", "-f", "rawvideo", "-y",\
								"/dev/null", "-i", filename],\
								stdout=subprocess.PIPE, stderr=subprocess.PIPE )
	#print( process.communicate() )
	idetSingleResult = process.communicate()[1].splitlines()[-2].split()
	idetMultiResult = process.communicate()[1].splitlines()[-2].split()
	sTFF = int(idetSingleResult[7])
	sBFF = int(idetSingleResult[9])
	sPro = int(idetSingleResult[11])
	sUnd = int(idetSingleResult[13])
	mTFF = int(idetMultiResult[7])
	mBFF = int(idetMultiResult[9])
	mPro = int(idetMultiResult[11])
	mUnd = int(idetMultiResult[13])
	if (sTFF > 500 or sBFF > 500) and (mTFF > 500 or mBFF > 500):
		print ("Interlacing detected, using yadif...")
		return True
	return False

def createThumbs( videofile, targetDir, ext="" ):
	duration = float( originalMetadata['format']['duration'] )
	try:
		aspectRatio = 	float(originalMetadata['streams'][0]['display_aspect_ratio'].split(':')[0]) / \
						float(originalMetadata['streams'][0]['display_aspect_ratio'].split(':')[1])
	except:
		aspectRatio = 1.0
	targetHeight = int( originalMetadata['streams'][0]['height'] )
	targetWidth  = int( aspectRatio * originalMetadata['streams'][0]['height'] )
	for i in range(0,int(settings["Number of Thumbs"])):
		if settings["Thumb Mode"] == "random":
			starttime = random.uniform( 0.0, duration )
		else:
			starttime = (i+1) * ( duration / (int(settings["Number of Thumbs"])+1) )
		ffmpegCommand = "ffmpeg -hide_banner -loglevel warning -ss " + str(starttime) + " -y -i " + quote(videofile) + " -vf thumbnail,scale=" + str(targetWidth) + "x" + str(targetHeight) + " -frames:v 1 " + quote(os.path.splitext(videofile)[0] + ext + " - " + str(i) + ".png")
		print (ffmpegCommand)
		os.system( ffmpegCommand )

#try:
counter = 0

while True:
	filename = getFileToConvert()
	originalMetadata = getMetadata(filename)

	if not filename:
		notify( '<b>karthago:</b> No more files to convert. <font color="#ff0000">Stopping.</font>' )
		sys.exit(0)

	try:
		if settings["Temp Dir"]:
			shutil.copyfile(filename, settings["Temp Dir"] + os.path.basename(filename))
			tempFile = settings["Temp Dir"] + os.path.basename(filename)
		else:
			tempFile = filename
			
		createThumbs( tempFile, os.path.dirname( filename ), "-before" )
			
		if interlaceDetect( tempFile ):
			deint = "yes"
			deintNotification = " (Deinterlacing)"
		else:
			deint = ""
			deintNotification = ""
		
		notify( '<font color="#00ff00">Starting to convert</font> ' + os.path.basename(filename) + deintNotification )
		tempNameForConvertedFile = os.path.splitext( tempFile )[0] + " - conv.mkv"
		newPath = os.path.splitext( filename )[0] + settings["Suffix for new Files"] + ".mkv"

		ffmpegCommand = generateCommand(filename, deint, tempNameForConvertedFile)
		print( ffmpegCommand )
		os.system( ffmpegCommand )
		newMetadata = getMetadata( tempNameForConvertedFile )
		newDuration = float(newMetadata['format']['duration'])
		originalDuration = float(originalMetadata['format']['duration'])
		if abs(newDuration - originalDuration) > 1.0:
			notify( '<font color="#ff0000">Duration check failed:</font>\nOriginal=' + str(originalDuration) + ' | New File=' + str(newDuration) + '\n<font color="#ff0000">Stopping.</font>' )
			sys.exit(1)

		createThumbs(  tempNameForConvertedFile, os.path.dirname( filename ), "-after" )
		# finalPath = os.path.join( os.path.dirname( filename ), os.path.basename( newPath ) )
		oldSize = os.path.getsize(filename) / 1048576.0
		newSize = os.path.getsize(tempNameForConvertedFile) / 1048576.0
		savings = ( (oldSize - newSize) / oldSize) *100
		if settings["Swap Originals"] == "yes":
			shutil.copyfile( tempNameForConvertedFile, newPath )
			os.remove( tempNameForConvertedFile )
			shutil.copyfile( tempFile, settings["Done Originals Dir"] + os.path.basename( tempFile ) )
			if newPath != filename:
				os.remove( filename )
			if tempFile != filename:
				os.remove( tempFile )
		# TODO: Update Database after converting a file
		# try:
		# 	width  = float(originalMetadata['streams'][0]['width'].split(':')[0])
		# 	height = float(originalMetadata['streams'][0]['height'].split(':')[1])
		# except:
		# 	width  = 0
		# 	height = 0
		# 	knownFiles[ finalPath ] = {	'size': os.path.getsize(finalPath),
		# 								'modified': os.path.getmtime(finalPath),
		# 								'codec': 'hevc',
		# 								'width': width,
		# 								'height': height }
		# doneFiles.append( finalPath )
		notify( '<font color="#ccaa00">Conversion done:</font> ' + os.path.basename(filename) \
				+ "\n(Duration check passed)" \
				+ "\nold file size " + str(int(oldSize)) + " MiB, new " + str(int(newSize)) + " MiB (saved " + '{:.1f}'.format(savings) + "%)" )
		allsettings.read("config.ini")		# this enables controlling the
		settings = allsettings["GLOBAL SETTINGS"] 	# agent simply by changing the settings file.
		counter += 1
		if counter >= int(settings["Max Conversions"]):
			notify( '<font color="#ff0000">Stopping</font> after ' + str(settings.maxConversions) + ' planned conversions.' )
			break
		if settings["Restart"] != "yes":
			break

	except:
		setErrorByPath(filename, 1)
		notify( '<b>karthago:</b> <font color="#ff0000">Unexpected error:</font> ' + str(sys.exc_info()) )
		traceback.print_exception(*exc_info)
		sys.exit(1)

