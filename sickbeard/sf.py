import os, time, datetime
import sickbeard

from sickbeard import helpers
def getTemps():
	
	#SpeedFan rolls the log every day, so we have to look for the log file based on the date
	log_file_date = datetime.date(2011,1,29).today().isoformat().replace('-','')
	log_files = []
	log_file = os.path.join( sickbeard.SPEEDFAN_LOG_LOCATION + "SFLog" + log_file_date + '.csv' )
	try:
		with open(log_file, 'rb') as fh:
			lines = fh.readlines()
			last = lines[-1]
			temp_list = last.strip().split('\t')
			del temp_list[0]
			temps = temp_list
			return temps
	except IOError:
			temps = "Error"
			return temps
