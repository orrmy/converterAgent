#!/usr/bin/python3
import os

import settings

def generateCommand(filename, deint, newFilename):
	for path in settings.hwaccelPaths:
		if filename.startswith( path ):
			if deint !="":
				deint = " -vf deinterlace_vaapi "
			return 'ffmpeg -hwaccel vaapi -hwaccel_device /dev/dri/renderD128 -hwaccel_output_format vaapi -i "' + filename + '" ' + deint + '-c:v hevc_vaapi -rc_mode 1 -qp 23 -c:a copy -c:s copy "' + newFilename + '"'

	return 	'nice -n10 ffmpeg -hide_banner -loglevel warning -stats -y -i "' + filename + '" -map 0 ' + deint + ' -c:v hevc -c:a copy -c:s copy -crf 23 -preset slow -max_muxing_queue_size 1024 "' + newFilename + '"'

