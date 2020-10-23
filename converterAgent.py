#!/usr/bin/python

import os, sys, shutil, re, subprocess, json, pickle, random, importlib
import traceback
from pushover import init, Client

import settings

# Global Variables
originalMetadata = None
knownFiles		 = {}

# Initializing Pushover Notifications
init("arukijyuq87ry28t5kw33ja3c53ucp")

def notify( message ):
	if settings.doNotify:
		Client( settings.pushoverUser ).send_message( "<b>" + settings.agentName + "</b>:" + message, html=1 )
	else:
		#print( message )
		pass

def getMetadata( filename ):
	process = subprocess.Popen( ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",\
									"-show_streams", "-select_streams", "v", filename], stdout=subprocess.PIPE )
	theJson = process.communicate()[0]
	#print (json.loads( theJson ))
	return json.loads( theJson )
	
def doConvert( filename ):
	global originalMetadata
	#print ( "checking " + filename )
	try:
		if knownFiles[filename] == (os.path.getsize(filename), os.path.getmtime(filename)):
			return False
	except KeyError:
		pass
	originalMetadata = getMetadata(filename)
	try:
		codec = originalMetadata["streams"][0]["codec_name"]
	except (KeyError, IndexError):
		codec = "unkown"
	if codec in settings.codecsToConvert:
		print( "\nConverting " + codec + " file " + filename )
		return True
	knownFiles[filename] = (os.path.getsize(filename), os.path.getmtime(filename))
	return False
	
		
def find_file(directory, pattern):
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
		ffmpegCommand = "ffmpeg -hide_banner -loglevel warning -ss " + str(starttime) + " -i '" + videofile + "' -vf thumbnail,scale=" + str(targetWidth) + "x" + str(targetHeight) + " -frames:v 1 '" + os.path.splitext(videofile)[0] + ext + " - " + str(i) + ".png'"
		print (ffmpegCommand)
		os.system( ffmpegCommand )

#try:
counter = 0

try:
	knownFiles = pickle.load(settings.agentName + ".db")
except:
	pass

while True:
	for lib in getSortedLibs(settings.inputDirectories):
		filename = find_file(lib, settings.formatsToConvert )
		if filename:
			break
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
		newFilename = os.path.splitext( tempFile )[0] + " - hevc.mkv"
		ffmpegCommand = 'nice -n10 ffmpeg -hide_banner -loglevel warning -stats -i "' + filename + '" -map 0 ' + deint + '-c:v hevc -c:a copy -c:s copy -crf 23 -preset slow -max_muxing_queue_size 1024 "' + newFilename + '"'
	# HARDWARE ENCODING # ffmpegCommand = 'nice -n10 ffmpeg -i "' + filename + '" -map 0 -vf yadif -vcodec h264_videotoolbox -profile:v high -b:v 1.7M -c:a copy "' + newFilename + '"'
		#print ffmpegCommand
		os.system( ffmpegCommand )
		newMetadata = getMetadata( newFilename )
		newDuration = float(newMetadata['format']['duration'])
		originalDuration = float(originalMetadata['format']['duration'])
		if abs(newDuration - originalDuration) > 1.0:
			notify( '<font color="#ff0000">Duration check failed:</font>\nOriginal=' + originalDuration + ' | New File=' + newDuration + '\n<font color="#ff0000">Stopping.</font>' )
			sys.exit(1)
		counter += 1
		createThumbs(  newFilename, os.path.dirname( filename ), "-after" )
		finalPath = os.path.join( os.path.dirname( filename ), os.path.basename( newFilename ) )
		oldSize = os.path.getsize(filename) / 1048576.0
		newSize = os.path.getsize(newFilename) / 1048576.0
		savings = ( (oldSize - newSize) / oldSize) *100
		if settings.swapOriginals:
			shutil.copyfile( newFilename, finalPath )
			os.remove( newFilename )
			shutil.copyfile( tempFile, settings.doneOriginalsFolder + os.path.basename( tempFile ) )
			os.remove( filename )
			if tempFile != filename:
				os.remove( tempFile )
		knownFiles[ finalPath ] = ( os.path.getsize(finalPath), os.path.getmtime(finalPath) )
		notify( '<font color="#ccaa00">Conversion done:</font> ' + os.path.basename(filename) \
				+ "\n(Duration check passed)" \
				+ "\nold file size " + str(int(oldSize)) + " MiB, new " + str(int(newSize)) + " MiB (saved " + '{:.1f}'.format(savings) + "%)" )
		pickle.dump( knownFiles, open( settings.agentName + ".db", "wb" ) )
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

