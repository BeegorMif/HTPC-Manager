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

import sickbeard

import plex
import boxcar2
import trakt

from sickbeard.common import *

# home theater / nas
plex_notifier = plex.PLEXNotifier()
# devices
boxcar2_notifier = boxcar2.Boxcar2Notifier()
# social
trakt_notifier = trakt.TraktNotifier()

notifiers = [
    plex_notifier,
    boxcar2_notifier,
    trakt_notifier,
]