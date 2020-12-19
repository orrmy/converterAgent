#! /usr/bin/python

import subprocess,json
from shlex import quote

def getMetadata( filename ):
	print (filename)
	process = subprocess.Popen( ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format",\
								"-show_streams", "-select_streams", "v", filename], stdout=subprocess.PIPE )
	theJson = process.communicate()[0]
	print (json.loads( theJson ))
	return json.loads( theJson )
