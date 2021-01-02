git #! /usr/bin/python

import os, sys, random, argparse
import CAmetadata

from shlex import quote

parser = argparse.ArgumentParser(description="Generate a still image from a video file")
#parser.add_argument("path")
#parser.add_argument("destination")
parser.add_argument("-r", "--random", action="store_true")
parser.add_argument("-t", "--timecode")
parser.add_argument("--overlay_filename", action="store_true")

args = parser.parse_args()

path = sys.stdin.read()
print (path)

metadata = CAmetadata.getMetadata(path)
print (metadata)
destPath = os.path.join( "/mnt/Augurinus/converterAgentTemp/screensaver/", os.path.basename(path) )

duration = float( metadata['format']['duration'] )
try:
	aspectRatio = 	float(metadata['streams'][0]['display_aspect_ratio'].split(':')[0]) / \
					float(metadata['streams'][0]['display_aspect_ratio'].split(':')[1])
except:
	aspectRatio = 1.0
targetHeight = int( metadata['streams'][0]['height'] )
targetWidth  = int( aspectRatio * targetHeight )

if args.random == True:
	starttime = random.uniform( 0.0, duration )
else:
	starttime = (i+1) * ( duration / (settings.numberOfThumbs+1) )
ffmpegCommand = "ffmpeg -hide_banner \
				-loglevel warning -ss \
				" + str(starttime) + " \
				-y -i " + quote(path) \
				+ " -vf thumbnail,scale=" \
				+ str(targetWidth) \
				+ "x" + str(targetHeight) \
				+ ""","drawtext=fontfile=/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc:text=''""" \
				+ os.path.basename(path) + """'': fontcolor=white:bordercolor=black@0.5:borderw=2: x=20: y=20" """ \
				+  " -frames:v 1 " + quote(os.path.splitext(destPath)[0] + " - " + str(int(starttime)) + ".png")
print (ffmpegCommand)
os.system( ffmpegCommand )
