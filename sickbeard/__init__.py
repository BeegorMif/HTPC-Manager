# Author: Nic Wolfe <nic@wolfeden.ca>
# URL: http://code.google.com/p/sickbeard/
#
# This file is part of SickRage.
#
# SickRage is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SickRage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import webbrowser
import datetime
import socket
import os
import re

from urllib2 import getproxies
from threading import Lock

# apparently py2exe won't build these unless they're imported somewhere
from sickbeard import config, webserveInit

from sickbeard.config import CheckSection, check_setting_int, check_setting_str, check_setting_float, ConfigMigrator
from sickbeard import versionChecker
from sickbeard import helpers, exceptions, scheduler
from sickbeard import logger
from sickbeard.common import SD, SKIPPED, NAMING_REPEAT

from lib.configobj import ConfigObj
from tornado.ioloop import IOLoop
import xml.etree.ElementTree as ElementTree

PID = None

CFG = None
CONFIG_FILE = None

# This is the version of the config we EXPECT to find
CONFIG_VERSION = 5

# Default encryption version (0 for None)
ENCRYPTION_VERSION = 0

PROG_DIR = '.'
MY_FULLNAME = None
MY_NAME = None
MY_ARGS = []
SYS_ENCODING = ''
DATA_DIR = ''
CREATEPID = False
PIDFILE = ''

DAEMON = None
NO_RESIZE = False

versionCheckScheduler = None

traktCheckerScheduler = None

showList = None
loadingShowList = None

NEWEST_VERSION = None
NEWEST_VERSION_STRING = None
VERSION_NOTIFY = None
AUTO_UPDATE = None
CUR_COMMIT_HASH = None

INIT_LOCK = Lock()
started = False
shutdown = False

ACTUAL_LOG_DIR = None
LOG_DIR = None

SOCKET_TIMEOUT = None

WEB_PORT = None
WEB_LOG = None
WEB_ROOT = None
WEB_USERNAME = None
WEB_PASSWORD = None
WEB_HOST = None
WEB_IPV6 = None

HANDLE_REVERSE_PROXY = None
PROXY_SETTING = None

LOCALHOST_IP = None

CPU_PRESET = None

ANON_REDIRECT = None

USE_API = False
API_KEY = None

LAUNCH_BROWSER = None
ROOT_DIRS = None
DEBUG = False
CLEAR_CACHE = None

USE_LISTVIEW = None

UPDATE_FREQUENCY = None

MIN_UPDATE_FREQUENCY = 1
DEFAULT_UPDATE_FREQUENCY = 1

USE_PLEX = False
PLEX_NOTIFY_ONSNATCH = False
PLEX_NOTIFY_ONDOWNLOAD = False
PLEX_UPDATE_LIBRARY = False
PLEX_SERVER_HOST = None
PLEX_HOST = None
PLEX_USERNAME = None
PLEX_PASSWORD = None

USE_BOXCAR2 = False
BOXCAR2_NOTIFY_ONSNATCH = False
BOXCAR2_NOTIFY_ONDOWNLOAD = False
BOXCAR2_ACCESSTOKEN = None

USE_TRAKT = False
TRAKT_USERNAME = None
TRAKT_PASSWORD = None
TRAKT_API = ''
TRAKT_REMOVE_WATCHLIST = False
TRAKT_USE_WATCHLIST = False
TRAKT_METHOD_ADD = 0
TRAKT_START_PAUSED = False
TRAKT_USE_RECOMMENDED = False
TRAKT_SYNC = False

USE_EVENTGHOST = False
EVENTGHOST_SERVER_HOST = None

USE_DRIVES = None
USE_DRIVEA = None
USE_DRIVEB = None
USE_DRIVEC = None
DRIVEA_NAME = None
DRIVEB_NAME = None
DRIVEC_NAME = None

USE_SICKBEARD = False
SICKBEARD_HOST = None
SICKBEARD_API = None

GUI_NAME = None
FUZZY_DATING = False
TRIM_ZERO = False
DATE_PRESET = None
TIME_PRESET = None
TIME_PRESET_W_SECONDS = None
TIMEZONE_DISPLAY = None

USE_FAILED_DOWNLOADS = False
DELETE_FAILED = False

EXTRA_SCRIPTS = []

GIT_PATH = None

CALENDAR_UNPROTECTED = False

TMDB_API_KEY = 'edc5f123313769de83a71e157758030b'
TRAKT_API_KEY = 'abd806c54516240c76e4ebc9c5ccf394'

__INITIALIZED__ = False
def initialize(consoleLogging=True):
    with INIT_LOCK:

        global ACTUAL_LOG_DIR, LOG_DIR, WEB_PORT, WEB_LOG, ENCRYPTION_VERSION, WEB_ROOT, WEB_USERNAME, WEB_PASSWORD, WEB_HOST, WEB_IPV6, USE_API, API_KEY, \
            HANDLE_REVERSE_PROXY, \
            USE_XBMC, XBMC_ALWAYS_ON, XBMC_NOTIFY_ONSNATCH, XBMC_NOTIFY_ONDOWNLOAD, XBMC_UPDATE_FULL, XBMC_UPDATE_ONLYFIRST, \
            XBMC_UPDATE_LIBRARY, XBMC_HOST, XBMC_USERNAME, XBMC_PASSWORD, \
            USE_TRAKT, TRAKT_USERNAME, TRAKT_PASSWORD, TRAKT_API, TRAKT_REMOVE_WATCHLIST, TRAKT_USE_WATCHLIST, TRAKT_METHOD_ADD, TRAKT_START_PAUSED, traktCheckerScheduler, TRAKT_USE_RECOMMENDED, TRAKT_SYNC, \
            USE_PLEX, PLEX_NOTIFY_ONSNATCH, PLEX_NOTIFY_ONDOWNLOAD, PLEX_UPDATE_LIBRARY, \
            PLEX_SERVER_HOST, PLEX_HOST, PLEX_USERNAME, PLEX_PASSWORD, SKIP_REMOVED_FILES, \
            USE_DRIVES, USE_DRIVEA, USE_DRIVEB, USE_DRIVEC, DRIVEA_NAME, DRIVEB_NAME, DRIVEC_NAME, \
            __INITIALIZED__, LAUNCH_BROWSER, \
            INDEXER_DEFAULT, INDEXER_TIMEOUT, \
            PROG_DIR, \
            versionCheckScheduler, VERSION_NOTIFY, AUTO_UPDATE, CPU_PRESET, \
            MIN_DAILYSEARCH_FREQUENCY, DEFAULT_UPDATE_FREQUENCY, MIN_UPDATE_FREQUENCY, UPDATE_FREQUENCY, \
            ROOT_DIRS, TIMEZONE_DISPLAY, \
            EXTRA_SCRIPTS, \
            USE_BOXCAR2, BOXCAR2_ACCESSTOKEN, BOXCAR2_NOTIFY_ONDOWNLOAD, BOXCAR2_NOTIFY_ONSNATCH, \
            USE_LISTVIEW, \
            GIT_PATH, MOVE_ASSOCIATED_FILES, CLEAR_CACHE, NFO_RENAME, \
            GUI_NAME, FUZZY_DATING, TRIM_ZERO, DATE_PRESET, TIME_PRESET, TIME_PRESET_W_SECONDS, \
            ANON_REDIRECT, LOCALHOST_IP, TMDB_API_KEY, DEBUG, PROXY_SETTING, \
            DEFAULT_AUTOPOSTPROCESSER_FREQUENCY, MIN_AUTOPOSTPROCESSER_FREQUENCY, \
            USE_SICKBEARD, SICKBEARD_API, SICKBEARD_HOST

        if __INITIALIZED__:
            return False

        CheckSection(CFG, 'General')
        CheckSection(CFG, 'Blackhole')
        CheckSection(CFG, 'XBMC')
        CheckSection(CFG, 'PLEX')
        CheckSection(CFG, 'EVENTGHOST')
        CheckSection(CFG, 'Growl')
        CheckSection(CFG, 'Prowl')
        CheckSection(CFG, 'Twitter')
        CheckSection(CFG, 'Boxcar')
        CheckSection(CFG, 'Boxcar2')
        CheckSection(CFG, 'NMJ')
        CheckSection(CFG, 'NMJv2')
        CheckSection(CFG, 'Synology')
        CheckSection(CFG, 'SynologyNotifier')
        CheckSection(CFG, 'pyTivo')
        CheckSection(CFG, 'NMA')
        CheckSection(CFG, 'Pushalot')
        CheckSection(CFG, 'Pushbullet')

        GUI_NAME = check_setting_str(CFG, 'GUI', 'gui_name', 'slick')

        ACTUAL_LOG_DIR = check_setting_str(CFG, 'General', 'log_dir', 'Logs')
        # put the log dir inside the data dir, unless an absolute path
        LOG_DIR = os.path.normpath(os.path.join(DATA_DIR, ACTUAL_LOG_DIR))

        if not helpers.makeDir(LOG_DIR):
            logger.log(u"!!! No log folder, logging to screen only!", logger.ERROR)

        SOCKET_TIMEOUT = check_setting_int(CFG, 'General', 'socket_timeout', 30)
        socket.setdefaulttimeout(SOCKET_TIMEOUT)

        try:
            WEB_PORT = check_setting_int(CFG, 'General', 'web_port', 8081)
        except:
            WEB_PORT = 8081

        if WEB_PORT < 21 or WEB_PORT > 65535:
            WEB_PORT = 8081

        WEB_HOST = check_setting_str(CFG, 'General', 'web_host', '0.0.0.0')
        WEB_IPV6 = bool(check_setting_int(CFG, 'General', 'web_ipv6', 0))
        WEB_ROOT = check_setting_str(CFG, 'General', 'web_root', '').rstrip("/")
        WEB_LOG = bool(check_setting_int(CFG, 'General', 'web_log', 0))
        ENCRYPTION_VERSION = check_setting_int(CFG, 'General', 'encryption_version', 0)
        WEB_USERNAME = check_setting_str(CFG, 'General', 'web_username', '')
        WEB_PASSWORD = check_setting_str(CFG, 'General', 'web_password', '')
        LAUNCH_BROWSER = bool(check_setting_int(CFG, 'General', 'launch_browser', 1))

        LOCALHOST_IP = check_setting_str(CFG, 'General', 'localhost_ip', '')

        CPU_PRESET = check_setting_str(CFG, 'General', 'cpu_preset', 'NORMAL')

        ANON_REDIRECT = check_setting_str(CFG, 'General', 'anon_redirect', 'http://dereferer.org/?')
        PROXY_SETTING = check_setting_str(CFG, 'General', 'proxy_setting', '')
        # attempt to help prevent users from breaking links by using a bad url 
        if not ANON_REDIRECT.endswith('?'):
            ANON_REDIRECT = ''

        USE_API = bool(check_setting_int(CFG, 'General', 'use_api', 0))
        API_KEY = check_setting_str(CFG, 'General', 'api_key', '')

        DEBUG = bool(check_setting_int(CFG, 'General', 'debug', 0))

        HANDLE_REVERSE_PROXY = bool(check_setting_int(CFG, 'General', 'handle_reverse_proxy', 0))

        ACTUAL_CACHE_DIR = check_setting_str(CFG, 'General', 'cache_dir', 'cache')
        # fix bad configs due to buggy code
        if ACTUAL_CACHE_DIR == 'None':
            ACTUAL_CACHE_DIR = 'cache'

        # unless they specify, put the cache dir inside the data dir
        if not os.path.isabs(ACTUAL_CACHE_DIR):
            CACHE_DIR = os.path.join(DATA_DIR, ACTUAL_CACHE_DIR)
        else:
            CACHE_DIR = ACTUAL_CACHE_DIR

        if not helpers.makeDir(CACHE_DIR):
            logger.log(u"!!! Creating local cache dir failed, using system default", logger.ERROR)
            CACHE_DIR = None

        ROOT_DIRS = check_setting_str(CFG, 'General', 'root_dirs', '')
        if not re.match(r'\d+\|[^|]+(?:\|[^|]+)*', ROOT_DIRS):
            ROOT_DIRS = ''

        proxies = getproxies()
        proxy_url = None
        if 'http' in proxies:
            proxy_url = proxies['http']
        elif 'ftp' in proxies:
            proxy_url = proxies['ftp']

        QUALITY_DEFAULT = check_setting_int(CFG, 'General', 'quality_default', SD)
        STATUS_DEFAULT = check_setting_int(CFG, 'General', 'status_default', SKIPPED)
        VERSION_NOTIFY = check_setting_int(CFG, 'General', 'version_notify', 1)
        AUTO_UPDATE = check_setting_int(CFG, 'General', 'auto_update', 0)
        FLATTEN_FOLDERS_DEFAULT = bool(check_setting_int(CFG, 'General', 'flatten_folders_default', 0))
        INDEXER_DEFAULT = check_setting_int(CFG, 'General', 'indexer_default', 0)
        INDEXER_TIMEOUT = check_setting_int(CFG, 'General', 'indexer_timeout', 10)
        ANIME_DEFAULT = bool(check_setting_int(CFG, 'General', 'anime_default', 0))
        SCENE_DEFAULT = bool(check_setting_int(CFG, 'General', 'scene_default', 0))

        PROVIDER_ORDER = check_setting_str(CFG, 'General', 'provider_order', '').split()

        UPDATE_FREQUENCY = check_setting_int(CFG, 'General', 'update_frequency', DEFAULT_UPDATE_FREQUENCY)
        if UPDATE_FREQUENCY < MIN_UPDATE_FREQUENCY:
            UPDATE_FREQUENCY = MIN_UPDATE_FREQUENCY

        USE_XBMC = bool(check_setting_int(CFG, 'XBMC', 'use_xbmc', 0))
        XBMC_ALWAYS_ON = bool(check_setting_int(CFG, 'XBMC', 'xbmc_always_on', 1))
        XBMC_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'XBMC', 'xbmc_notify_onsnatch', 0))
        XBMC_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'XBMC', 'xbmc_notify_ondownload', 0))
        XBMC_UPDATE_LIBRARY = bool(check_setting_int(CFG, 'XBMC', 'xbmc_update_library', 0))
        XBMC_UPDATE_FULL = bool(check_setting_int(CFG, 'XBMC', 'xbmc_update_full', 0))
        XBMC_UPDATE_ONLYFIRST = bool(check_setting_int(CFG, 'XBMC', 'xbmc_update_onlyfirst', 0))
        XBMC_HOST = check_setting_str(CFG, 'XBMC', 'xbmc_host', '')
        XBMC_USERNAME = check_setting_str(CFG, 'XBMC', 'xbmc_username', '')
        XBMC_PASSWORD = check_setting_str(CFG, 'XBMC', 'xbmc_password', '')

        USE_PLEX = bool(check_setting_int(CFG, 'Plex', 'use_plex', 0))
        PLEX_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Plex', 'plex_notify_onsnatch', 0))
        PLEX_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Plex', 'plex_notify_ondownload', 0))
        PLEX_UPDATE_LIBRARY = bool(check_setting_int(CFG, 'Plex', 'plex_update_library', 0))
        PLEX_SERVER_HOST = check_setting_str(CFG, 'Plex', 'plex_server_host', '')
        PLEX_HOST = check_setting_str(CFG, 'Plex', 'plex_host', '')
        PLEX_USERNAME = check_setting_str(CFG, 'Plex', 'plex_username', '')
        PLEX_PASSWORD = check_setting_str(CFG, 'Plex', 'plex_password', '')

        USE_BOXCAR2 = bool(check_setting_int(CFG, 'Boxcar2', 'use_boxcar2', 0))
        BOXCAR2_NOTIFY_ONSNATCH = bool(check_setting_int(CFG, 'Boxcar2', 'boxcar2_notify_onsnatch', 0))
        BOXCAR2_NOTIFY_ONDOWNLOAD = bool(check_setting_int(CFG, 'Boxcar2', 'boxcar2_notify_ondownload', 0))
        BOXCAR2_ACCESSTOKEN = check_setting_str(CFG, 'Boxcar2', 'boxcar2_accesstoken', '')

        USE_TRAKT = bool(check_setting_int(CFG, 'Trakt', 'use_trakt', 0))
        TRAKT_USERNAME = check_setting_str(CFG, 'Trakt', 'trakt_username', '')
        TRAKT_PASSWORD = check_setting_str(CFG, 'Trakt', 'trakt_password', '')
        TRAKT_API = check_setting_str(CFG, 'Trakt', 'trakt_api', '')
        TRAKT_REMOVE_WATCHLIST = bool(check_setting_int(CFG, 'Trakt', 'trakt_remove_watchlist', 0))
        TRAKT_USE_WATCHLIST = bool(check_setting_int(CFG, 'Trakt', 'trakt_use_watchlist', 0))
        TRAKT_METHOD_ADD = check_setting_str(CFG, 'Trakt', 'trakt_method_add', "0")
        TRAKT_START_PAUSED = bool(check_setting_int(CFG, 'Trakt', 'trakt_start_paused', 0))
        TRAKT_USE_RECOMMENDED = bool(check_setting_int(CFG, 'Trakt', 'trakt_use_recommended', 0))
        TRAKT_SYNC = bool(check_setting_int(CFG, 'Trakt', 'trakt_sync', 0))

        USE_PLEX = bool(check_setting_int(CFG, 'Plex', 'use_plex', 0))
        PLEX_SERVER_HOST = check_setting_str(CFG, 'Plex', 'plex_server_host', '')
        PLEX_HOST = check_setting_str(CFG, 'Plex', 'plex_host', '')

        USE_DRIVES = bool(check_setting_int(CFG, 'Drives', 'use_drives', 0))
        USE_DRIVEA = bool(check_setting_int(CFG, 'Drives', 'use_driveA', 0))
        USE_DRIVEB = bool(check_setting_int(CFG, 'Drives', 'use_driveB', 0))
        USE_DRIVEC = bool(check_setting_int(CFG, 'Drives', 'use_driveC', 0))
        DRIVEA_NAME = check_setting_str(CFG, 'Drives', 'driveA_name', '')
        DRIVEB_NAME = check_setting_str(CFG, 'Drives', 'driveB_name', '')
        DRIVEC_NAME = check_setting_str(CFG, 'Drives', 'driveC_name', '')

        USE_SICKBEARD = bool(check_setting_int(CFG, 'Sickbeard', 'use_sickbeard', 0))
        SICKBEARD_HOST = check_setting_str(CFG, 'Sickbeard', 'sickbeard_host', '')
        SICKBEARD_API = check_setting_str(CFG, 'Sickbeard', 'sickbeard_api', '')

        GIT_PATH = check_setting_str(CFG, 'General', 'git_path', '')

        EXTRA_SCRIPTS = [x.strip() for x in check_setting_str(CFG, 'General', 'extra_scripts', '').split('|') if
                         x.strip()]

        USE_LISTVIEW = bool(check_setting_int(CFG, 'General', 'use_listview', 0))

        FUZZY_DATING = bool(check_setting_int(CFG, 'GUI', 'fuzzy_dating', 0))
        TRIM_ZERO = bool(check_setting_int(CFG, 'GUI', 'trim_zero', 0))
        DATE_PRESET = check_setting_str(CFG, 'GUI', 'date_preset', '%x')
        TIME_PRESET_W_SECONDS = check_setting_str(CFG, 'GUI', 'time_preset', '%I:%M:%S %p')
        TIME_PRESET = TIME_PRESET_W_SECONDS.replace(u":%S", u"")
        TIMEZONE_DISPLAY = check_setting_str(CFG, 'GUI', 'timezone_display', 'network')

        if not os.path.isfile(CONFIG_FILE):
            logger.log(u"Unable to find '" + CONFIG_FILE + "', all settings will be default!", logger.DEBUG)
            save_config()

        # start up all the threads
        logger.sb_log_instance.initLogging(consoleLogging=consoleLogging)

        # migrate the config if it needs it
        migrator = ConfigMigrator(CFG)
        migrator.migrate_config()

        # initialize schedulers
        # updaters
        update_now = datetime.timedelta(minutes=0)
        versionCheckScheduler = scheduler.Scheduler(versionChecker.CheckVersion(),
                                                    cycleTime=datetime.timedelta(hours=UPDATE_FREQUENCY),
                                                    threadName="CHECKVERSION",
                                                    silent=False)

        search_intervals = {'15m': 15, '45m': 45, '90m': 90, '4h': 4*60, 'daily': 24*60}

        __INITIALIZED__ = True
        return True


def start():
    global __INITIALIZED__, versionCheckScheduler, started

    with INIT_LOCK:

        if __INITIALIZED__:

            # start the version checker
            versionCheckScheduler.thread.start()

            started = True


def halt():
    global __INITIALIZED__, versionCheckScheduler, started

    with INIT_LOCK:

        if __INITIALIZED__:

            logger.log(u"Aborting all threads")

            # abort all the threads

            versionCheckScheduler.abort = True
            logger.log(u"Waiting for the VERSIONCHECKER thread to exit")
            try:
                versionCheckScheduler.thread.join(10)
            except:
                pass

            __INITIALIZED__ = False


def remove_pid_file(PIDFILE):
    try:
        if os.path.exists(PIDFILE):
            os.remove(PIDFILE)

    except (IOError, OSError):
        return False

    return True


def sig_handler(signum=None, frame=None):
    global shutdown

    if type(signum) != type(None):
        logger.log(u"Signal %i caught, saving and exiting..." % int(signum))
        shutdown = True
        IOLoop.current().stop()

def saveAll():
    # save config
    logger.log(u"Saving config file to disk")
    save_config()

def saveAndShutdown(restart=False):
    global shutdown

    if not restart:
        shutdown = True

    # stop tornado web server
    webserveInit.server.stop()

    # stop all tasks
    halt()

    # save all shows to db
    saveAll()

    #stop tornado io loop
    IOLoop.current().stop()

def invoke_command(to_call, *args, **kwargs):

    def delegate():
        to_call(*args, **kwargs)

    logger.log(u"Placed invoked command: " + repr(delegate) + " for " + repr(to_call) + " with " + repr(
        args) + " and " + repr(kwargs), logger.DEBUG)

    IOLoop.current().add_callback(delegate)

def invoke_restart(soft=True):
    invoke_command(restart, soft=soft)


def invoke_shutdown():
    global shutdown
    shutdown = True
    invoke_command(IOLoop.current().stop)

def restart(soft=True):
    if soft:
        halt()
        saveAll()
        logger.log(u"Re-initializing all data")
        initialize()
    else:
        IOLoop.current().stop()


def save_config():
    new_config = ConfigObj()
    new_config.filename = CONFIG_FILE

    # For passwords you must include the word `password` in the item_name and add `helpers.encrypt(ITEM_NAME, ENCRYPTION_VERSION)` in save_config()
    new_config['General'] = {}
    new_config['General']['config_version'] = CONFIG_VERSION
    new_config['General']['encryption_version'] = int(ENCRYPTION_VERSION)
    new_config['General']['log_dir'] = ACTUAL_LOG_DIR if ACTUAL_LOG_DIR else 'Logs'
    new_config['General']['socket_timeout'] = SOCKET_TIMEOUT
    new_config['General']['web_port'] = WEB_PORT
    new_config['General']['web_host'] = WEB_HOST
    new_config['General']['web_ipv6'] = int(WEB_IPV6)
    new_config['General']['web_log'] = int(WEB_LOG)
    new_config['General']['web_root'] = WEB_ROOT
    new_config['General']['web_username'] = WEB_USERNAME
    new_config['General']['web_password'] = helpers.encrypt(WEB_PASSWORD, ENCRYPTION_VERSION)
    new_config['General']['localhost_ip'] = LOCALHOST_IP
    new_config['General']['cpu_preset'] = CPU_PRESET
    new_config['General']['anon_redirect'] = ANON_REDIRECT
    new_config['General']['use_api'] = int(USE_API)
    new_config['General']['api_key'] = API_KEY
    new_config['General']['debug'] = int(DEBUG)
    new_config['General']['handle_reverse_proxy'] = int(HANDLE_REVERSE_PROXY)
    new_config['General']['update_frequency'] = int(UPDATE_FREQUENCY)
    new_config['General']['version_notify'] = int(VERSION_NOTIFY)
    new_config['General']['auto_update'] = int(AUTO_UPDATE)
    new_config['General']['launch_browser'] = int(LAUNCH_BROWSER)
    new_config['General']['proxy_setting'] = PROXY_SETTING

    new_config['General']['use_listview'] = int(USE_LISTVIEW)

    new_config['General']['extra_scripts'] = '|'.join(EXTRA_SCRIPTS)
    new_config['General']['git_path'] = GIT_PATH

    new_config['Plex'] = {}
    new_config['Plex']['use_plex'] = int(USE_PLEX)
    new_config['Plex']['plex_notify_onsnatch'] = int(PLEX_NOTIFY_ONSNATCH)
    new_config['Plex']['plex_notify_ondownload'] = int(PLEX_NOTIFY_ONDOWNLOAD)
    new_config['Plex']['plex_update_library'] = int(PLEX_UPDATE_LIBRARY)
    new_config['Plex']['plex_server_host'] = PLEX_SERVER_HOST
    new_config['Plex']['plex_host'] = PLEX_HOST
    new_config['Plex']['plex_username'] = PLEX_USERNAME
    new_config['Plex']['plex_password'] = helpers.encrypt(PLEX_PASSWORD, ENCRYPTION_VERSION)

    new_config['Boxcar2'] = {}
    new_config['Boxcar2']['use_boxcar2'] = int(USE_BOXCAR2)
    new_config['Boxcar2']['boxcar2_notify_onsnatch'] = int(BOXCAR2_NOTIFY_ONSNATCH)
    new_config['Boxcar2']['boxcar2_notify_ondownload'] = int(BOXCAR2_NOTIFY_ONDOWNLOAD)
    new_config['Boxcar2']['boxcar2_accesstoken'] = BOXCAR2_ACCESSTOKEN

    new_config['Trakt'] = {}
    new_config['Trakt']['use_trakt'] = int(USE_TRAKT)
    new_config['Trakt']['trakt_username'] = TRAKT_USERNAME
    new_config['Trakt']['trakt_password'] = helpers.encrypt(TRAKT_PASSWORD, ENCRYPTION_VERSION)
    new_config['Trakt']['trakt_api'] = TRAKT_API
    new_config['Trakt']['trakt_remove_watchlist'] = int(TRAKT_REMOVE_WATCHLIST)
    new_config['Trakt']['trakt_use_watchlist'] = int(TRAKT_USE_WATCHLIST)
    new_config['Trakt']['trakt_method_add'] = TRAKT_METHOD_ADD
    new_config['Trakt']['trakt_start_paused'] = int(TRAKT_START_PAUSED)
    new_config['Trakt']['trakt_use_recommended'] = int(TRAKT_USE_RECOMMENDED)
    new_config['Trakt']['trakt_sync'] = int(TRAKT_SYNC)

    new_config['GUI'] = {}
    new_config['GUI']['gui_name'] = GUI_NAME
    new_config['GUI']['fuzzy_dating'] = int(FUZZY_DATING)
    new_config['GUI']['trim_zero'] = int(TRIM_ZERO)
    new_config['GUI']['date_preset'] = DATE_PRESET
    new_config['GUI']['time_preset'] = TIME_PRESET_W_SECONDS
    new_config['GUI']['timezone_display'] = TIMEZONE_DISPLAY

    new_config['EventGhost'] = {}
    new_config['EventGhost']['eventghost_plex'] = int(USE_PLEX)
    new_config['EventGhost']['eventghost_server_host'] = PLEX_SERVER_HOST
    new_config['EventGhost']['eventghost_host'] = PLEX_HOST

    new_config['Drives'] = {}
    new_config['Drives']['use_drives'] = int(USE_DRIVES)
    new_config['Drives']['use_drivea'] = int(USE_DRIVEA)
    new_config['Drives']['use_driveb'] = int(USE_DRIVEB)
    new_config['Drives']['use_drivec'] = int(USE_DRIVEC)
    new_config['Drives']['driveA_name'] = DRIVEA_NAME
    new_config['Drives']['driveB_name'] = DRIVEB_NAME
    new_config['Drives']['driveC_name'] = DRIVEC_NAME

    new_config['Sickbeard'] = {}
    new_config['Sickbeard']['use_sickbeard'] = int(USE_SICKBEARD)
    new_config['Sickbeard']['sickbeard_host'] = SICKBEARD_HOST
    new_config['Sickbeard']['sickbeard_api'] = SICKBEARD_API

    new_config.write()


def launchBrowser(startPort=None):
    if not startPort:
        startPort = WEB_PORT
    browserURL = 'http://localhost:%d%s' % (startPort, WEB_ROOT)
    try:
        webbrowser.open(browserURL, 2, 1)
    except:
        try:
            webbrowser.open(browserURL, 1, 1)
        except:
            logger.log(u"Unable to launch a browser", logger.ERROR)
