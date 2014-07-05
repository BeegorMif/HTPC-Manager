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

import os.path
import datetime
import re
import urlparse
import sickbeard

from sickbeard import encodingKludge as ek
from sickbeard import logger
from sickbeard import helpers

def change_LOG_DIR(log_dir, web_log):
    log_dir_changed = False
    abs_log_dir = os.path.normpath(os.path.join(sickbeard.DATA_DIR, log_dir))
    web_log_value = checkbox_to_value(web_log)

    if os.path.normpath(sickbeard.LOG_DIR) != abs_log_dir:
        if helpers.makeDir(abs_log_dir):
            sickbeard.ACTUAL_LOG_DIR = os.path.normpath(log_dir)
            sickbeard.LOG_DIR = abs_log_dir

            logger.sb_log_instance.initLogging()
            logger.log(u"Initialized new log file in " + sickbeard.LOG_DIR)
            log_dir_changed = True

        else:
            return False

    if sickbeard.WEB_LOG != web_log_value or log_dir_changed == True:
        sickbeard.WEB_LOG = web_log_value

    return True


def change_UPDATE_FREQUENCY(freq):
    sickbeard.UPDATE_FREQUENCY = to_int(freq, default=sickbeard.DEFAULT_UPDATE_FREQUENCY)

    if sickbeard.UPDATE_FREQUENCY < sickbeard.MIN_UPDATE_FREQUENCY:
        sickbeard.UPDATE_FREQUENCY = sickbeard.MIN_UPDATE_FREQUENCY

    sickbeard.versionCheckScheduler.cycleTime = datetime.timedelta(hours=sickbeard.UPDATE_FREQUENCY)

def change_VERSION_NOTIFY(version_notify):
    oldSetting = sickbeard.VERSION_NOTIFY

    sickbeard.VERSION_NOTIFY = version_notify

    if not version_notify:
        sickbeard.NEWEST_VERSION_STRING = None

    if oldSetting == False and version_notify == True:
        sickbeard.versionCheckScheduler.action.run()  # @UndefinedVariable


def CheckSection(CFG, sec):
    """ Check if INI section exists, if not create it """
    try:
        CFG[sec]
        return True
    except:
        CFG[sec] = {}
        return False


def checkbox_to_value(option, value_on=1, value_off=0):
    """
    Turns checkbox option 'on' or 'true' to value_on (1)
    any other value returns value_off (0)
    """
    if option == 'on' or option == 'true':
        return value_on

    return value_off


def clean_host(host, default_port=None):
    """
    Returns host or host:port or empty string from a given url or host
    If no port is found and default_port is given use host:default_port
    """

    host = host.strip()

    if host:

        match_host_port = re.search(r'(?:http.*://)?(?P<host>[^:/]+).?(?P<port>[0-9]*).*', host)

        cleaned_host = match_host_port.group('host')
        cleaned_port = match_host_port.group('port')

        if cleaned_host:

            if cleaned_port:
                host = cleaned_host + ':' + cleaned_port

            elif default_port:
                host = cleaned_host + ':' + str(default_port)

            else:
                host = cleaned_host

        else:
            host = ''

    return host


def clean_hosts(hosts, default_port=None):
    cleaned_hosts = []

    for cur_host in [x.strip() for x in hosts.split(",")]:
        if cur_host:
            cleaned_host = clean_host(cur_host, default_port)
            if cleaned_host:
                cleaned_hosts.append(cleaned_host)

    if cleaned_hosts:
        cleaned_hosts = ",".join(cleaned_hosts)

    else:
        cleaned_hosts = ''

    return cleaned_hosts


def clean_url(url):
    """
    Returns an cleaned url starting with a scheme and folder with trailing /
    or an empty string
    """

    if url and url.strip():

        url = url.strip()

        if '://' not in url:
            url = '//' + url

        scheme, netloc, path, query, fragment = urlparse.urlsplit(url, 'http')

        if not path.endswith('/'):
            basename, ext = ek.ek(os.path.splitext, ek.ek(os.path.basename, path))  # @UnusedVariable
            if not ext:
                path = path + '/'

        cleaned_url = urlparse.urlunsplit((scheme, netloc, path, query, fragment))

    else:
        cleaned_url = ''

    return cleaned_url


def to_int(val, default=0):
    """ Return int value of val or default on error """

    try:
        val = int(val)
    except:
        val = default

    return val


################################################################################
# Check_setting_int                                                            #
################################################################################
def minimax(val, default, low, high):
    """ Return value forced within range """

    val = to_int(val, default=default)

    if val < low:
        return low
    if val > high:
        return high

    return val


################################################################################
# Check_setting_int                                                            #
################################################################################
def check_setting_int(config, cfg_name, item_name, def_val):
    try:
        my_val = int(config[cfg_name][item_name])
    except:
        my_val = def_val
        try:
            config[cfg_name][item_name] = my_val
        except:
            config[cfg_name] = {}
            config[cfg_name][item_name] = my_val
    logger.log(item_name + " -> " + str(my_val), logger.DEBUG)
    return my_val


################################################################################
# Check_setting_float                                                          #
################################################################################
def check_setting_float(config, cfg_name, item_name, def_val):
    try:
        my_val = float(config[cfg_name][item_name])
    except:
        my_val = def_val
        try:
            config[cfg_name][item_name] = my_val
        except:
            config[cfg_name] = {}
            config[cfg_name][item_name] = my_val

    logger.log(item_name + " -> " + str(my_val), logger.DEBUG)
    return my_val


################################################################################
# Check_setting_str                                                            #
################################################################################
def check_setting_str(config, cfg_name, item_name, def_val, log=True):
    # For passwords you must include the word `password` in the item_name and add `helpers.encrypt(ITEM_NAME, ENCRYPTION_VERSION)` in save_config()
    if bool(item_name.find('password') + 1):
        log = False
        encryption_version = sickbeard.ENCRYPTION_VERSION
    else:
        encryption_version = 0

    try:
        my_val = helpers.decrypt(config[cfg_name][item_name], encryption_version)
    except:
        my_val = def_val
        try:
            config[cfg_name][item_name] = helpers.encrypt(my_val, encryption_version)
        except:
            config[cfg_name] = {}
            config[cfg_name][item_name] = helpers.encrypt(my_val, encryption_version)

    if log:
        logger.log(item_name + " -> " + str(my_val), logger.DEBUG)
    else:
        logger.log(item_name + " -> ******", logger.DEBUG)

    return my_val

class ConfigMigrator():
    def __init__(self, config_obj):
        """
        Initializes a config migrator that can take the config from the version indicated in the config
        file up to the version required by SB
        """

        self.config_obj = config_obj

        # check the version of the config
        self.config_version = check_setting_int(config_obj, 'General', 'config_version', sickbeard.CONFIG_VERSION)
        self.expected_config_version = sickbeard.CONFIG_VERSION
        self.migration_names = {1: 'Custom naming',
                                2: 'Sync backup number with version number',
        }

    def migrate_config(self):
        """
        Calls each successive migration until the config is the same version as SB expects
        """

        if self.config_version > self.expected_config_version:
            logger.log_error_and_exit(u"Your config version (" + str(
                self.config_version) + ") has been incremented past what this version of SickRage supports (" + str(
                self.expected_config_version) + ").\n" + \
                                      "If you have used other forks or a newer version of SickRage, your config file may be unusable due to their modifications.")

        sickbeard.CONFIG_VERSION = self.config_version

        while self.config_version < self.expected_config_version:
            next_version = self.config_version + 1

            if next_version in self.migration_names:
                migration_name = ': ' + self.migration_names[next_version]
            else:
                migration_name = ''

            logger.log(u"Backing up config before upgrade")
            if not helpers.backupVersionedFile(sickbeard.CONFIG_FILE, self.config_version):
                logger.log_error_and_exit(u"Config backup failed, abort upgrading config")
            else:
                logger.log(u"Proceeding with upgrade")

            # do the                                                                                                migration, expect a method named _migrate_v<num>
            logger.log(u"Migrating config up to version " + str(next_version) + migration_name)
            getattr(self, '_migrate_v' + str(next_version))()
            self.config_version = next_version

            # save new config after migration
            sickbeard.CONFIG_VERSION = self.config_version
            logger.log(u"Saving config file to disk")
            sickbeard.save_config()

    # Migration v1: Custom naming
    def _migrate_v1(self):
        """
        Reads in the old naming settings from your config and generates a new config template from them.
        """
        return
    # Migration v2: Dummy migration to sync backup number with config version number
    def _migrate_v2(self):
        return

