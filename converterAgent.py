#!/usr/bin/python

# converterAgent V0.7
# - now uses SQLite Database managed in separate script to check for files to convert
# - suffix for final converted file can now be chosen (or turned off) in settings file
# - setting ignorePathsWith now accepts a tuple of strings
# - Fix: Filenames should be correctly escaped now
# - Will now simply overwrite old temp files (which are most likely results of aborted conversions) instead of asking and thus stopping the whole   

import os, sys, sqlite3, shutil, re, subprocess, json, pickle, random, importlib
import traceback
from shlex import quote
from pushover import init, Client

import settings
from CAmetadata import getMetadata
from CAgenerateCommand import generateCommand

# Global Variables
originalMetadata = None
knownFiles		 = {}
doneFiles		 = []

# Initializing Pushover Notifications
init("arukijyuq87ry28t5kw33ja3c53ucp")

# Database Connection
db = sqlite3.connect( settings.libraryName + '.sqlite3' )
cursor = db.cursor()

def notify( message ):
	if settings.doNotify:
		try:
			Client( settings.pushoverUser ).send_message( "<b>" + settings.agentName + "</b>:" + message, html=1 )
		except:
			print("Pushover notification failed.")
	else:
		#print( message )
		pass

def getFileToConvert():
	while True:
		cursor.execute("SELECT Path, Modified, Size FROM files WHERE (Codec='mpeg2video' OR Container='.ts') AND Cut=1 AND Error=0 ORDER BY RANDOM()")
		files = cursor.fetchall()
		file = files[0]
		print ("Found " + str(len(files)) + " to convert." )
		try:
			if any(string in file[0] for string in settings.ignorePathsWith):
				break
			if file[1] == os.path.getmtime(file[0]) and file[2] == os.path.getsize(file[0]):
				return file[0]
		except FileNotFoundError:
			pass

def doConvert( filename ): # CAN PROBABLY BE REMOVED
	global originalMetadata
	print ( "checking " + filename )
	if filename in doneFiles:
		return False
	try:
		thisCodec = knownFiles[filename]['codec']
		thisWidth = knownFiles[filename]['width']
		if thisCodec not in settings.codecsToConvert:
			print ("-> Wrong codec: " + thisCodec + " (Data cached)")
			return False
		if not ( thisWidth >= settings.codecsToConvert[thisCodec][0] and \
				 thisWidth <= settings.codecsToConvert[thisCodec][1] and \
				 thisHeight >= settings.codecsToConvert[thisCodec][0] and \
				 thisHeight <= settings.codecsToConvert[thisCodec][1] ):
			print ("-> Wrong size: " + thisHeight + " x " + thisHeight + " (Data cached)")
			return False
	except KeyError:
		pass
	originalMetadata = getMetadata(filename)
	try:
		codec = originalMetadata["streams"][0]["codec_name"]
	except (KeyError, IndexError):
		codec = "unkown"
	try:
		width  = float(originalMetadata['streams'][0]['width'])
		height = float(originalMetadata['streams'][0]['height'])
	except:
		width  = 0
		height = 0
	if  codec in settings.codecsToConvert and \
		width > settings.codecsToConvert[codec]['width'][0] and \
		width <= settings.codecsToConvert[codec]['width'][1] and \
		height > settings.codecsToConvert[codec]['height'][0] and \
		height <= settings.codecsToConvert[codec]['height'][1]:
			print( "\nConverting " + codec + " file " + filename )
			return True
	knownFiles[filename] = {'size': os.path.getsize(filename), \
							'modified': os.path.getmtime(filename), \
							'codec': codec, \
							'width': width, \
							'height': height }
	print (knownFiles[filename])
	return False
	
		
def find_file(directory, pattern): # CAN PROBABLY BE REMOVED
	counter = 0
	print( "\n" + directory ) #debug
	for root, dirs, files in os.walk(directory):
		for basename in files:
			filename = os.path.join(root, basename)
			if basename.endswith(pattern) and (settings.ignorePathsWith not in filename):
				filename = os.path.join(root, basename)
				searchPattern = os.path.splitext( basename )[0]
				versions = list(filter(lambda x: searchPattern in x, os.listdir(root)))
				counter += 1
				sys.stdout.write( "\rchecked " + str(counter) + " files...")
				sys.stdout.flush()
				if not len(versions) > 1:
					if doConvert( filename ):
						return filename
	return None

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
	for i in range(0,settings.numberOfThumbs):
		if settings.thumbmode == "random":
			starttime = random.uniform( 0.0, duration )
		else:
			starttime = (i+1) * ( duration / (settings.numberOfThumbs+1) ) 
		ffmpegCommand = "ffmpeg -hide_banner -loglevel warning -ss " + str(starttime) + " -y -i " + quote(videofile) + " -vf thumbnail,scale=" + str(targetWidth) + "x" + str(targetHeight) + " -frames:v 1 " + quote(os.path.splitext(videofile)[0] + ext + " - " + str(i) + ".png")
		print (ffmpegCommand)
		os.system( ffmpegCommand )

#try:
counter = 0

try:
	knownFiles = pickle.load(settings.agentName + ".db")
except:
	pass
	
try:
	doneFiles = pickle.load(settings.agentName + "-done.db")
except:
	pass

while True:
	filename = getFileToConvert()
	originalMetadata = getMetadata(filename)

	if not filename:
		notify( '<b>karthago:</b> No more files to convert. <font color="#ff0000">Stopping.</font>' )
		sys.exit(0)

	try:
		if settings.tempDirectory:
			shutil.copyfile(filename, settings.tempDirectory + os.path.basename(filename))
			tempFile = settings.tempDirectory + os.path.basename(filename)
		else:
			tempFile = filename
			
		createThumbs( tempFile, os.path.dirname( filename ), "-before" )
			
		if interlaceDetect( tempFile ):
			deint = "-vf yadif "
			deintNotification = " (Deinterlacing)"
		else:
			deint = ""
			deintNotification = ""
	#except:
	#	notify( 'Copying of file ' + os.path.basename(filename) + ' failed. <font color="#ff0000">Stopping.</font>' )
		
		notify( '<font color="#00ff00">Starting to convert</font> ' + os.path.basename(filename) + deintNotification )
		tempNameForConvertedFile = os.path.splitext( tempFile )[0] + " - conv.mkv"
		newPath = os.path.splitext( filename )[0] + settings.newFileSuffix + ".mkv"

		ffmpegCommand = generateCommand(filename, deint, tempNameForConvertedFile)
		print( ffmpegCommand )
		os.system( ffmpegCommand )
		newMetadata = getMetadata( tempNameForConvertedFile )
		newDuration = float(newMetadata['format']['duration'])
		originalDuration = float(originalMetadata['format']['duration'])
		if abs(newDuration - originalDuration) > 1.0:
			notify( '<font color="#ff0000">Duration check failed:</font>\nOriginal=' + str(originalDuration) + ' | New File=' + str(newDuration) + '\n<font color="#ff0000">Stopping.</font>' )
			sys.exit(1)
		counter += 1
		createThumbs(  tempNameForConvertedFile, os.path.dirname( filename ), "-after" )
		# finalPath = os.path.join( os.path.dirname( filename ), os.path.basename( newPath ) )
		oldSize = os.path.getsize(filename) / 1048576.0
		newSize = os.path.getsize(tempNameForConvertedFile) / 1048576.0
		savings = ( (oldSize - newSize) / oldSize) *100
		if settings.swapOriginals:
			shutil.copyfile( tempNameForConvertedFile, newPath )
			os.remove( tempNameForConvertedFile )
			shutil.copyfile( tempFile, settings.doneOriginalsFolder + os.path.basename( tempFile ) )
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
		pickle.dump( knownFiles, open( settings.agentName + ".db", "wb" ) )
		pickle.dump( doneFiles, open( settings.agentName + "-done.db", "wb" ) )
		importlib.reload( settings ) # this enables controlling the agent simply by changing the settings file. 
		if counter >= settings.maxConversions:
			settings.doRestart = False
			notify( '<font color="#ff0000">Stopping</font> after ' + str(settings.maxConversions) + ' planned conversions.' )
		if settings.doRestart == False:
			break

	except:
		notify( '<b>karthago:</b> <font color="#ff0000">Unexpected error:</font> ' + str(sys.exc_info()) )
		traceback.print_exception(*exc_info)
		sys.exit(1)

