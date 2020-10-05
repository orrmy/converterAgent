agentName = "cartenna"

formatsToConvert 	= (".ts", ".mp4", ".m4v", "mkv")
codecsToConvert		= ("mpeg2video")

ignorePathsWith = "/.grab/" # this should be extended to support a list of paths

inputDirectories	= 	( 	"/home/bjoern/Videos/converterAgent/interlaced/", \
							"/home/bjoern/Videos/converterAgent/progressive/", \
							"/run/user/1000/gvfs/smb-share:server=karthago.local,share=plex%20serien%20elvas/",\
							"/run/user/1000/gvfs/smb-share:server=karthago.local,share=plex%20dvr%20serien/", \
							"/run/user/1000/gvfs/smb-share:server=karthago.local,share=plex%20serien/",\
							"/run/user/1000/gvfs/smb-share:server=karthago.local,share=plex%20movies%20elvas/")
tempDirectory		= "/home/bjoern/Videos/converterAgent/temp/"

swapOriginals		= True
doneOriginalsFolder	= "/home/bjoern/Videos/converterAgent/originals/"
convertedFilesFolder	= "/home/bjoern/Videos/converterAgent/converted/"

writeLockFiles		= True

thumbmode			= "normal"
numberOfThumbs		= 5

doRestart = True

doNotify = 		True
pushoverUser= 	"uiaakautaeqy831yxf7ztq6ngjhnqr"

maxConversions = 1000
