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
#  GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SickRage.  If not, see <http://www.gnu.org/licenses/>.

__all__ = ['ezrss',
           'tvtorrents',
           'btn',
           'thepiratebay',
           'kat',
           'torrentleech',
           'hdtorrents',
           'torrentday',
           'hdbits',
           'iptorrents',
           'nextgen',
           'speedcd',
           'nyaatorrents',
]

import sickbeard
import generic
from sickbeard import logger
from os import sys


def sortedProviderList():
    initialList = sickbeard.providerList + sickbeard.torrentRssProviderList
    providerDict = dict(zip([x.getID() for x in initialList], initialList))

    newList = []

    # add all modules in the priority list, in order
    for curModule in sickbeard.PROVIDER_ORDER:
        if curModule in providerDict:
            newList.append(providerDict[curModule])

    # add any modules that are missing from that list
    for curModule in providerDict:
        if providerDict[curModule] not in newList:
            newList.append(providerDict[curModule])

    return newList

def makeProviderList():
    return [x.provider for x in [getProviderModule(y) for y in __all__] if x]


def getTorrentRssProviderList(data):
    providerList = filter(lambda x: x, [makeTorrentRssProvider(x) for x in data.split('!!!')])

    seen_values = set()
    providerListDeduped = []
    for d in providerList:
        value = d.name
        if value not in seen_values:
            providerListDeduped.append(d)
            seen_values.add(value)

    return filter(lambda x: x, providerList)


def makeTorrentRssProvider(configString):
    if not configString:
        return None

    cookies = None
    search_mode = 'eponly'
    search_fallback = 0
    backlog_only = 0

    try:
        name, url, cookies, enabled, search_mode, search_fallback, backlog_only = configString.split('|')
    except ValueError:
        try:
            name, url, enabled, search_mode, search_fallback, backlog_only = configString.split('|')
        except ValueError:
            try:
                name, url, enabled = configString.split('|')
            except ValueError:
                logger.log(u"Skipping RSS Torrent provider string: '" + configString + "', incorrect format", logger.ERROR)
                return None

    try:
        torrentRss = sys.modules['sickbeard.providers.rsstorrent']
    except:
        return

    newProvider = torrentRss.TorrentRssProvider(name, url, cookies, search_mode, search_fallback, backlog_only)
    newProvider.enabled = enabled == '1'

    return newProvider


def getProviderModule(name):
    name = name.lower()
    prefix = "sickbeard.providers."
    if name in __all__ and prefix + name in sys.modules:
        return sys.modules[prefix + name]
    else:
        raise Exception("Can't find " + prefix + name + " in " + "Providers")


def getProviderClass(id):
    providerMatch = [x for x in
                     sickbeard.providerList + sickbeard.torrentRssProviderList if
                     x.getID() == id]

    if len(providerMatch) != 1:
        return None
    else:
        return providerMatch[0]
