#! /usr/bin/python3

import os, sys, sqlite3, argparse, configparser

allsettings = configparser.ConfigParser( allow_no_value=True )
allsettings.read("config.ini")
settings = allsettings["GLOBAL SETTINGS"]

def getArguments():
	parser = argparse.ArgumentParser(description="Various helper functions to manage Converter Agent's sqlite database")
	parser.add_argument("instruction", choices=["random", "setcut"])
	parser.add_argument("-k", "--key", type=int, default=0)
	parser.add_argument("-v", "--value", default=None)
	parser.add_argument("-c", "--codec", default="")
	parser.add_argument("--uncut", action="store_true")
	parser.add_argument("-s", action="store_true", help="show result in system file browser")

	args = parser.parse_args()
	return args

def generateSearch():
	if not args.codec == "" or (not args.uncut):
		return ""
	result = "WHERE "
	if args.codec != "":
		result = result + "Codec = '" + args.codec + " "
		if not args.uncut:
			return result
		return result + "AND Cut=0 "
	return result + "Cut=0"

def random():
    dbQuery = "SELECT id, Path FROM files " + generateSearch() + " ORDER BY RANDOM() LIMIT 1;"
    print (dbQuery)
    cursor.execute( dbQuery )
    (key, path) = cursor.fetchone()
    if args.s:
        print ("opening record " + str(key) + " | " + path)
        os.system('nautilus "%s"' % path)
    if not args.s:
        print (str(key))
        print (path)

def setCut(key, value):
    cursor.execute("UPDATE files SET Cut=? WHERE id=?", (value, key))
    cursor.execute("SELECT * FROM files WHERE id=?", (key,))
    print( cursor.fetchall() )
    db.commit()



db = sqlite3.connect( settings['Library Name'] + '.sqlite3' )
cursor = db.cursor()

args = getArguments()

if args.instruction=="random":
    random()
    sys.exit()
if args.instruction=="setcut":
    setCut(args.key, args.value)
    
