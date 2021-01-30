#!/usr/bin/python

# converterAgent V0.9
# -
# - show conversion setting in notifcations
# - update database after successful conversion


import os, sys, sqlite3, shutil, re, subprocess, json, pickle, random, configparser
import traceback, logging, time
from shlex import quote
from pushover import init, Client

from CAmetadata import getMetadata
from CAdatabaseBuilder import safeMetadata

# Global Variables
originalMetadata = None

allsettings = configparser.ConfigParser( allow_no_value=True )
allsettings.read("config.ini")
settings = allsettings["GLOBAL SETTINGS"]

conversion = allsettings["DEFAULT"]["conversion"]
uncutPaths = settings['postprocessing paths'].split('\n')

if settings["database type"] == "mysql":
    import mysql.connector

# Initializing Pushover Notifications
init(settings['pushover token'])

# Database Connection
if settings["database type"] == 'mysql':
    try:
        db = mysql.connector.connect( host= settings["database server"], user= settings["database user"], password= settings["database password"], database= settings["database name"] )
        print(db)
    except:
        print("No db connection...")
else:
    db = sqlite3.connect( settings['Library Name'] + '.sqlite3' )
cursor = db.cursor()

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
        print (section)
        if section["type"] == "selection":
            search = " WHERE "
            for key,value in section.items():
                print( key,value )
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
                if key == "convert uncut" and value != 'yes':
                    if search != " WHERE ":
                        search = search + " AND "
                    search = search + " `Cut`=1 "
            if search == " WHERE ":
                continue
            query = "SELECT `Path`, `Codec`, `Container`, `Modified`, `Size` FROM `files` " + search + " AND `Done`='0' AND `Lock`=0 AND `Error`=0 AND `Missing`=0 ORDER BY RAND()"
            print( query )
            cursor.execute( query )
            result = cursor.fetchall()
            if len( result ) != 0:
                for file in result:
                    print (str(file[3]) + " | " + str(os.path.getmtime(localPath( file[0] ))))
                    localFile = localPath( file[0] )
                    if file[3] == int(os.path.getmtime(localFile)) and file[4] == os.path.getsize(localFile):
                        print (localFile)
                        print ("Settings: " + conversion)
                        conversion = section["conversion"]
                        return file[0]
    #print( allsettings[section] )
    #print( result[0] )
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
        return "ffmpeg " + convSettings['ffmpeg input options'] + " -i " \
            + quote(filename) + " " + deint + " -map 0 " + \
            convSettings['ffmpeg output options'] + " " + \
            quote(newFilename)

# def getSortedLibs(unsortedList): #not needed right now, implement again?
#     return sorted(unsortedList, key = lambda e: shutil.disk_usage(e)[2])

def interlaceDetect( filename ):
    duration = float( originalMetadata['format']['duration'] )
    process = subprocess.Popen( ["ffmpeg", "-filter:v", "idet", "-frames:v",\
                                "10000", "-an", "-f", "rawvideo", "-y",\
                                "/dev/null", "-i", filename],\
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE )
    print( process.communicate() )
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
        aspectRatio =     float(originalMetadata['streams'][0]['display_aspect_ratio'].split(':')[0]) / \
                        float(originalMetadata['streams'][0]['display_aspect_ratio'].split(':')[1])
    except KeyError:
        try:
            aspectRatio =     float(originalMetadata['streams'][0]['width']) / \
                            float(originalMetadata['streams'][0]['height'])
        except (KeyError, ZeroDivisionError):
            print( "Thumb creation skippen, aspect ratio couldn't be determined..." )
            return
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
    dbFile = getFileToConvert()

    if not dbFile:
        notify( '<b>karthago:</b> No more files to convert. <font color="#ff0000">Stopping.</font>' )
        sys.exit(0)

    setDataByPath( dbFile, 'Lock', 1 )
    localFile = localPath( dbFile )
    originalMetadata = getMetadata( localFile )

    try:
        if settings["Temp Dir"]:
            shutil.copyfile(localFile, settings["Temp Dir"] + os.path.basename(localFile))
            tempFile = settings["Temp Dir"] + os.path.basename(localFile)
        else:
            tempFile = localFile
            
        createThumbs( tempFile, os.path.dirname( localFile ), "-before" )
            
        if interlaceDetect( tempFile ):
            deint = "yes"
            deintNotification = " (Deinterlacing)"
        else:
            deint = ""
            deintNotification = ""
        
        notify( '<font color="#00ff00">Starting to convert</font> ' + os.path.basename(localFile) + deintNotification + \
                "\nConversion: " + conversion)
        tempNameForConvertedFile = os.path.splitext( tempFile )[0] + " - conv.mkv"
        newPath = os.path.splitext( localFile )[0] + settings["Suffix for new Files"] + ".mkv"

        ffmpegCommand = generateCommand(localFile, deint, tempNameForConvertedFile)
        print( ffmpegCommand )
        os.system( ffmpegCommand )
        
        newMetadata = getMetadata( tempNameForConvertedFile )
        newDuration = float(newMetadata['format']['duration'])
        originalDuration = float(originalMetadata['format']['duration'])
        if abs(newDuration - originalDuration) > 1.0:
            notify( '<font color="#ff0000">Duration check failed:</font>\nOriginal=' + str(originalDuration) + ' | New File=' + str(newDuration) + '\n<font color="#ff0000">Stopping.</font>' )
            sys.exit()

        createThumbs(  tempNameForConvertedFile, os.path.dirname( localFile ), "-after" )
        # finalPath = os.path.join( os.path.dirname( filename ), os.path.basename( newPath ) )
        oldSize = os.path.getsize(localFile) / 1048576.0
        newSize = os.path.getsize(tempNameForConvertedFile) / 1048576.0
        savings = ( (oldSize - newSize) / oldSize) *100
        if settings["Swap Originals"] == "yes":
            shutil.copyfile( tempNameForConvertedFile, newPath )
            os.remove( tempNameForConvertedFile )
            shutil.copyfile( tempFile, settings["Done Originals Dir"] + os.path.basename( tempFile ) )
            if newPath != localFile:
                os.remove( localFile )
                cursor.execute( "DELETE FROM `files` WHERE `Path`=%s;", (dbFile[0],) )
            if tempFile != localFile:
                os.remove( tempFile )
        
        if localFile.startswith(tuple(uncutPaths)):
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
        allsettings.read("config.ini")        # this enables controlling the
        settings = allsettings["GLOBAL SETTINGS"]     # agent simply by changing the settings file.
        counter += 1
        if counter >= int(settings["Max Conversions"]):
            notify( '<font color="#ff0000">Stopping</font> after ' + str(settings.maxConversions) + ' planned conversions.' )
            break
        if settings["Restart"] != "yes":
            break

    except:
        setDataByPath(dbFile, 'Error', 1)
        notify( '<b>karthago:</b> <font color="#ff0000">Unexpected error:</font> ' + str(sys.exc_info()) )
        traceback.print_exception(*exc_info)
        sys.exit(1)

