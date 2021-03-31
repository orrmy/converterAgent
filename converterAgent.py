#!/usr/bin/python

# converterAgent V0.10
#
# - added config option for filename selection with regular expression
# - added config option to get title tag from filename by regex
# - target container can now be specified in options
# - trying to get some more sensible output, logging and error handling


import os, sys, sqlite3, shutil, re, subprocess, json, pickle, random, configparser
import traceback, logging, time
from shlex import quote
from pushover import init, Client

from CAmetadata import getMetadata
from CAdatabaseBuilder import safeMetadata

logger = logging.getLogger('converterAgent')
logger.setLevel(logging.DEBUG)

# Global Variables
originalMetadata = None

allsettings = configparser.ConfigParser( allow_no_value=True )
allsettings.read("config.ini")
settings = allsettings["GLOBAL SETTINGS"]

conversion = allsettings["DEFAULT"]["conversion"]
uncutPaths = settings['postprocessing paths'].split('\n')

# Initializing Logging
fh = logging.FileHandler('ca.log')
fh.setLevel(logging.DEBUG)
eh = logging.FileHandler('error.log')
eh.setLevel(logging.ERROR)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
eh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)
logger.addHandler(eh)

if settings["database type"] == "mysql":
    import mysql.connector

# Initializing Pushover Notifications
init(settings['pushover token'])
logger.debug('Pushover notifications initialized...')

# Database Connection
if settings["database type"] == 'mysql':
    try:
        db = mysql.connector.connect( host= settings["database server"], user= settings["database user"], password= settings["database password"], database= settings["database name"] )
        cursor = db.cursor()
        logger.info('Connected to MySQL server ' + settings["database server"])
    except:
        logger.error("No db connection... quitting")
        sys.exit()
else:
    logger.error("Connections to databases of type " + settings["database type"] + " are not supported. Sorry.")

def localPath( path ):
    if path.startswith( settings['database base path'] ):
        return path.replace( settings['database base Path'], settings['local base path'], 1 )
    else:
        return path
        
def dbPath( path ):
    if path.startswith( settings['local base path'] ):
        return path.replace( settings['local base path'], settings['database base path'], 1 )
    else:
        return path

def setDataByPath( path, key, value ):
    sqlCommand = "UPDATE `files` Set `" + key + "`=%s WHERE `Path`=%s"
    while counter <= 5:
        try:
            cursor.execute( sqlCommand, (value, path))
            break
        except sqlite3.OperationalError:
            notify( 'Database locked. Waiting...' )
            time.sleep(60)
    db.commit()

def writeAllToDB( Path=None, Filename="", Container="", Codec="", Width=0, \
                Height=0, Duration=0, Size=0, Found=0, Modified=0, Cut=0, \
                Checked=0,  Missing=0, Error=0, Lock=0, Done=0):
    cursor.execute( 'SELECT * FROM files WHERE Path=%s;', (Path,) )
    result = cursor.fetchall()
    if len(result)==0:
        cursor.execute("INSERT INTO `files` (`Path`, `Filename`, `Container`, `Codec`, \
                        `Width`, `Height`, `Duration`, `Size`, `Found`, `Modified`, `Cut`, \
                        `Checked`, `Missing`, `Error`, `Lock`, `Done`) \
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)", \
                        (Path, Filename, Container, Codec, Width, \
                        Height, Duration, Size, Found, Modified, Cut, \
                        Checked, Missing, Error, Lock, Done) )
    else:
        cursor.execute("UPDATE `files` SET `Codec`=%s, \
                        `Width`=%s, `Height`=%s, `Duration`=%s, `Size`=%s, `Modified`=%s, `Missing`=0 \
                        WHERE `Path`=%s", \
                        (Codec, Width, Height, Duration, Size, Modified, Path) )
    db.commit()

def notify( message ):
    if settings["Notifications"] == "yes":
        #try:
        Client( settings["pushover user"] ).send_message( "<b>" + settings["Agent Name"] + "</b>:" + message, html=1 )
        #except:
        #    print("Pushover notification failed.")
    else:
        #print( message )
        pass

def getFileToConvert():
    global conversion
    for secName,section in allsettings.items():
        if section["type"] == "selection":
            logger.info('Checking for files in selection ' + secName )
            search = " WHERE "
            for key,value in section.items():
                if key == "codecs":
                    if search != " WHERE ":
                        search = search + " AND "
                    search = search + " ( `Codec` = '" + value.replace("\n", "' OR `Codec` = '") + "' ) "
                if key == "containers":
                    if search != " WHERE ":
                        search = search + " AND "
                    search = search + " ( `Container` = '" + value.replace("\n", "' OR `Container` = '") + "' ) "
                if key == "paths":
                    if search != " WHERE ":
                        search = search + " AND "
                    search = search + " ( `Path` LIKE '" + value.replace("\n", "%' OR `Path`  LIKE '") + "%' ) "
                if key == "filenames":
                    if search != " WHERE ":
                        search = search + " AND "
                    search = search + " ( filename REGEXP '" + value.replace("\n","' OR filename REGEXP '") + "' )"
                if key == "convert uncut" and value != 'yes':
                    if search != " WHERE ":
                        search = search + " AND "
                    search = search + " `Cut`=1 "
            if search == " WHERE ":
                continue
            query = "SELECT `Path`, `Codec`, `Container`, `Modified`, `Size` FROM `files` " + search + " AND `Done`='0' AND `Lock`='0' AND `Error`=0 AND `Missing`=0 ORDER BY filename"
            logger.debug("Database query: " + query )
            cursor.execute( query )
            result = cursor.fetchall()
            logger.info("Found " + str(len(result)) + " items...")
            if len( result ) != 0:
                for file in result:
                    localFile = localPath( file[0] )
                    if file[3] == int(os.path.getmtime(localFile)) and file[4] == os.path.getsize(localFile):
                        conversion = section["conversion"]
                        logger.info("Selected file " + localFile + " with settings " + conversion)
                        return file[0]
    return
    
def generateCommand(filename, deint, newFilename):
    global conversion

    allsettings = configparser.ConfigParser( allow_no_value=True )
    allsettings.read("config.ini")
    convSettings = allsettings[ conversion ]
    if deint != "":
        deint = convSettings["deint Option"]

    if convSettings['engine'] == "Handbrake":
        return "HandBrakeCLI -v --preset-import-gui -Z '" + \
            convSettings['preset'] + "' " + convSettings['options'] + " " \
            + deint + " -i " + quote(filename) + " -o " + \
            quote(newFilename)
    else:
        command = "ffmpeg " + convSettings['ffmpeg input options'] + " -i " \
            + quote(filename) + " " + deint + " -map 0 " + \
            convSettings['ffmpeg output options'] + " "
        try:
            if convSettings['title from filename']:
                metadataTitle = re.search(convSettings['title from filename'], filename).group(1) #TODO We really shouldn't just assume group 1
                if metadataTitle != "":
                    command = command + '-metadata Title="' + metadataTitle + '" '
        except KeyError:
            pass
        command = command + quote(newFilename)
    return command

# def getSortedLibs(unsortedList): #not needed right now, implement again?
#     return sorted(unsortedList, key = lambda e: shutil.disk_usage(e)[2])

def interlaceDetect( filename ):
    logger.info('Checking if file is interlaced')
    duration = float( originalMetadata['format']['duration'] )
    process = subprocess.Popen( ["ffmpeg", "-filter:v", "idet", "-frames:v",\
                                "10000", "-an", "-f", "rawvideo", "-y",\
                                "/dev/null", "-i", filename],\
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE )
    #logger.debug( process.communicate() )
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
        logger.info ("Interlacing detected")
        return True
    logger.info('Looks progressive')
    return False

def createThumbs( videofile, metadata, targetDir, ext="" ):
    logger.info('Creating ' + settings["Number of Thumbs"] + ' still images' + '(Mode: ' + settings["Thumb Mode"]+ ')')
    duration = float( metadata['format']['duration'] )
    try:
        aspectRatio =     float(metadata['streams'][0]['display_aspect_ratio'].split(':')[0]) / \
                        float(metadata['streams'][0]['display_aspect_ratio'].split(':')[1])
    except KeyError:
        try:
            aspectRatio =     float(metadata['streams'][0]['width']) / \
                            float(metadata['streams'][0]['height'])
        except (KeyError, ZeroDivisionError):
            logger.warning( "Thumb creation skipped, aspect ratio couldn't be determined..." )
            return
    logger.debug('Aspect ratio determined as '+ str(aspectRatio))
    targetHeight = int( metadata['streams'][0]['height'] )
    targetWidth  = int( aspectRatio * metadata['streams'][0]['height'] )
    for i in range(0,int(settings["Number of Thumbs"])):
        if settings["Thumb Mode"] == "random":
            starttime = random.uniform( 0.0, duration )
        else:
            starttime = (i+1) * ( duration / (int(settings["Number of Thumbs"])+1) )
        ffmpegCommand = "ffmpeg -hide_banner -loglevel warning -ss " + str(starttime) + " -y -i " + quote(videofile) + " -vf thumbnail,scale=" + str(targetWidth) + "x" + str(targetHeight) + " -frames:v 1 " + quote(os.path.splitext(videofile)[0] + ext + " - " + str(i) + ".png")
        logger.debug(ffmpegCommand)
        os.system( ffmpegCommand )

#try:
counter = 0
error = 0

while True:
    dbFile = getFileToConvert()

    if not dbFile:
        logger.warning('No more files to convert. Stopping')
        notify( '<b>karthago:</b> No more files to convert. <font color="#ff0000">Stopping.</font>' )
        sys.exit(0)

    setDataByPath( dbFile, 'Lock', 1 );										logger.debug('File locked in DB')
    localFile = localPath( dbFile );										logger.debug('DB path ' + dbFile + ' --> locally at ' + localFile)
    originalMetadata = getMetadata( localFile );							logger.info('Gathering metadata')

    oldSize = os.path.getsize(localFile) / 1048576.0
    try:
        if settings["Temp Dir"] != "":
            logger.info('Copying to temp directory (' + str(oldSize) + ' Mib)')
            shutil.copyfile(localFile, settings["Temp Dir"] + os.path.basename(localFile))
            tempFile = settings["Temp Dir"] + os.path.basename(localFile)
        else:
            tempFile = localFile
            
        createThumbs( tempFile, originalMetadata, os.path.dirname( localFile ), "-before" )
            
        if interlaceDetect( tempFile ):
            deint = "yes"
            deintNotification = " (Deinterlacing)"
        else:
            deint = ""
            deintNotification = ""
        
        notify( '<font color="#00ff00">Starting to convert</font> ' + os.path.basename(localFile) + deintNotification + \
                "\nConversion: " + conversion)
        tempNameForConvertedFile = os.path.splitext( tempFile )[0] + " - conv" + allsettings[conversion]["container"]
        newPath = os.path.splitext( localFile )[0] + settings["Suffix for new Files"] + allsettings[conversion]["container"]

        ffmpegCommand = generateCommand(localFile, deint, tempNameForConvertedFile)
        logger.debug( 'Conversion Command: ' + ffmpegCommand )
        os.system( ffmpegCommand )
        
        logger.info('Conversion done. Running checks...')

        newMetadata = getMetadata( tempNameForConvertedFile )
        newDuration = float(newMetadata['format']['duration'])
        originalDuration = float(originalMetadata['format']['duration'])
        if abs(newDuration - originalDuration) > 1.0:
            notify( '<font color="#ff0000">Duration check failed:</font>\nOriginal=' + str(originalDuration) + ' | New File=' + str(newDuration) + '\n<font color="#ff0000">Stopping.</font>' )
            logger.error('Duration check failed. Original=' + str(originalDuration) + ' | New File=' + str(newDuration) + '. File will not be replaced.')
            raise Exception('Duration check failed')
        else:
            logger.info('Duration... OK')

        createThumbs(  tempNameForConvertedFile, newMetadata, os.path.dirname( localFile ), "-after" )
        # finalPath = os.path.join( os.path.dirname( filename ), os.path.basename( newPath )
        newSize = os.path.getsize(tempNameForConvertedFile) / 1048576.0
        savings = ( (oldSize - newSize) / oldSize) *100
        oldBitrate = int( (oldSize / originalDuration) / 1000 )
        newBitrate = int( (newSize / newDuration) / 1000 )
        logger.info('Saved ' + str(oldSize-newSize) + 'MiB / ' + '{:.1f}'.format(savings) + '% (Bitrate ' + str(oldBitrate) + ' kbps --> ' + str(newBitrate) + ' kbps)')
        if settings["Swap Originals"] == "yes":
            logger.info('Copying new file to original path...')
            shutil.copyfile( tempNameForConvertedFile, newPath )
            logger.info('Removing temporary target file...')
            os.remove( tempNameForConvertedFile )
            logger.info('Backing up original to ' + settings["Done Originals Dir"])
            shutil.copyfile( tempFile, settings["Done Originals Dir"] + os.path.basename( tempFile ) )
            if newPath != localFile:
                logger.info('Removing original file and its DB entry...')
                os.remove( localFile )
                cursor.execute( "DELETE FROM `files` WHERE `Path`=%s;", (dbFile[0],) )
            if tempFile != localFile:
                logger.info('Removing temporary source file...')
                os.remove( tempFile )
        
        logger.info('Updating DB...')
        if localFile.startswith(tuple(uncutPaths)): #TODO This erases a possibly differing entrance in the DB!
            cut = 0
        else:
            cut = 1

        writeAllToDB( Path      = dbPath( newPath ),\
                    Filename    = os.path.basename( newPath ), \
                    Container   = os.path.splitext( newPath )[1], \
                    Codec       = safeMetadata(newMetadata, ("streams", 0, "codec_name") ), \
                    Width       = safeMetadata(newMetadata, ("streams", 0, "width") ), \
                    Height      = safeMetadata(newMetadata, ("streams", 0, "height") ), \
                    Duration    = safeMetadata(newMetadata, ("format", "duration") ), \
                    Size        = os.path.getsize(newPath),\
                    Found       = int(time.time()),\
                    Modified    = int(os.path.getmtime(newPath)),\
                    Cut=cut, Checked=0,  Missing=0, Error=0, Lock=0, Done=conversion )


        setDataByPath( dbFile, 'Lock', 0 )
        setDataByPath( dbFile, 'Done', conversion )

        notify( '<font color="#ccaa00">Conversion done:</font> ' + os.path.basename(dbFile) \
                + "\n(Duration check passed)" \
                + "\nold file size " + str(int(oldSize)) + " MiB, new " + str(int(newSize)) + " MiB (saved " + '{:.1f}'.format(savings) + "%)" )
        logger.debug('Reloading settings...')
        allsettings.read("config.ini")        # this enables controlling the
        settings = allsettings["GLOBAL SETTINGS"]     # agent simply by changing the settings file.
        counter += 1
        if counter >= int(settings["Max Conversions"]):
            logger.info('Stopping after ' + settings['max conversions'] + ' planned conversions.' )
            notify( '<font color="#ff0000">Stopping</font> after ' + settings['max conversions'] + ' planned conversions.' )
            break
        if settings["Restart"] != "yes":
            logger.info( str(counter) + ' conversion(s) done (max ' + settings['max conversions'] + ')') #FIXME Stops because of no restart!
            error = 0
            break

    except:
        setDataByPath(dbFile, 'Error', 1)
        notify( '<b>karthago:</b> <font color="#ff0000">Unexpected error:</font> ' + str(sys.exc_info()) )
        error += 1
        if error >= 5:
            logger.error( dbFile + ' (' + str(sys.exc_info() + ')' ))
            sys.exit()
        logger.error( dbFile + ' (' + str(sys.exc_info() + ')' ))

