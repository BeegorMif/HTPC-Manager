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
import base64
import inspect
import traceback
import urlparse

import os.path

import time
import urllib
import re
import threading
import datetime
import random
import sys

import sickbeard

from sickbeard import config
from sickbeard import ui
from sickbeard import logger, helpers, exceptions, classes
from sickbeard import encodingKludge as ek
from sickbeard.sf import getTemps
from sickbeard.space import getSpace
from sickbeard.space import divWidth
from sickbeard.common import Overview, cpu_presets
from sickbeard.exceptions import ex

from browser import WebFileBrowser

from lib.dateutil import tz

from trakt import TraktCall

try:
    import json
except ImportError:
    from lib import simplejson as json

try:
    import xml.etree.cElementTree as etree
except ImportError:
    import xml.etree.ElementTree as etree

from Cheetah.Template import Template
from tornado.web import RequestHandler, HTTPError


def authenticated(handler_class):
    def wrap_execute(handler_execute):
        def basicauth(handler, transforms, *args, **kwargs):
            def _request_basic_auth(handler):
                handler.set_status(401)
                handler.set_header('WWW-Authenticate', 'Basic realm="SickRage"')
                handler._transforms = []
                handler.finish()
                return False

            try:
                if not (sickbeard.WEB_USERNAME and sickbeard.WEB_PASSWORD):
                    return True
                elif handler.request.uri.startswith('/calendar') or (
                            handler.request.uri.startswith('/api') and '/api/builder' not in handler.request.uri):
                    return True

                auth_hdr = handler.request.headers.get('Authorization')

                if auth_hdr == None:
                    return _request_basic_auth(handler)
                if not auth_hdr.startswith('Basic '):
                    return _request_basic_auth(handler)

                auth_decoded = base64.decodestring(auth_hdr[6:])
                username, password = auth_decoded.split(':', 2)

                if username != sickbeard.WEB_USERNAME or password != sickbeard.WEB_PASSWORD:
                    return _request_basic_auth(handler)
            except Exception, e:
                return _request_basic_auth(handler)
            return True

        def _execute(self, transforms, *args, **kwargs):
            if not basicauth(self, transforms, *args, **kwargs):
                return False
            return handler_execute(self, transforms, *args, **kwargs)

        return _execute

    handler_class._execute = wrap_execute(handler_class._execute)
    return handler_class


class HTTPRedirect(Exception):
    """Exception raised when the request should be redirected."""

    def __init__(self, url, permanent=False, status=None):
        self.url = urlparse.urljoin(sickbeard.WEB_ROOT, url)
        self.permanent = permanent
        self.status = status
        Exception.__init__(self, self.url, self.permanent, self.status)

    def __call__(self):
        """Use this exception as a request.handler (raise self)."""
        raise self


def redirect(url, permanent=False, status=None):
    raise HTTPRedirect(url, permanent, status)


@authenticated
class MainHandler(RequestHandler):
    def http_error_401_handler(self):
        """ Custom handler for 401 error """
        return r'''<!DOCTYPE html>
    <html>
        <head>
            <title>%s</title>
        </head>
        <body>
            <br/>
            <font color="#0000FF">Error %s: You need to provide a valid username and password.</font>
        </body>
    </html>
    ''' % ('Access denied', 401)

    def write_error(self, status_code, **kwargs):
        if status_code == 401:
            self.finish(self.http_error_401_handler())
        elif status_code == 404:
            self.redirect('/home/')
        else:
            logger.log(traceback.format_exc(), logger.DEBUG)
            super(MainHandler, self).write_error(status_code, **kwargs)

    def _dispatch(self):

        path = self.request.uri.replace(sickbeard.WEB_ROOT, '').split('?')[0]

        method = path.strip('/').split('/')[-1]

        if method == 'robots.txt':
            method = 'robots_txt'

        if path.startswith('/api') and method != 'builder':
            apikey = path.strip('/').split('/')[-1]
            method = path.strip('/').split('/')[0]
            self.request.arguments.update({'apikey': [apikey]})

        def pred(c):
            return inspect.isclass(c) and c.__module__ == pred.__module__

        try:
            klass = [cls[1] for cls in
                     inspect.getmembers(sys.modules[__name__], pred) + [(self.__class__.__name__, self.__class__)] if
                     cls[0].lower() == method.lower() or method in cls[1].__dict__.keys()][0](self.application,
                                                                                              self.request)
        except:
            klass = None

        if klass and not method.startswith('_'):
            # Sanitize argument lists:
            args = self.request.arguments
            for arg, value in args.items():
                if len(value) == 1:
                    args[arg] = value[0]

            # Regular method handler for classes
            func = getattr(klass, method, None)

            # Special index method handler for classes and subclasses:
            if path.startswith('/api') or path.endswith('/'):
                if func and getattr(func, 'index', None):
                    func = getattr(func(self.application, self.request), 'index', None)
                elif not func:
                    func = getattr(klass, 'index', None)

            if func:
                return func(**args)

        raise HTTPError(404)

    def get(self, *args, **kwargs):
        try:
            self.finish(self._dispatch())
        except HTTPRedirect, inst:
            self.redirect(inst.url, inst.permanent, inst.status)

    def post(self, *args, **kwargs):
        try:
            self.finish(self._dispatch())
        except HTTPRedirect, inst:
            self.redirect(inst.url, inst.permanent, inst.status)

    def robots_txt(self, *args, **kwargs):
        """ Keep web crawlers out """
        self.set_header('Content-Type', 'text/plain')
        return "User-agent: *\nDisallow: /"

    def showPoster(self, show=None, which=None):
        # Redirect initial poster/banner thumb to default images
        if which[0:6] == 'poster':
            default_image_name = 'poster.png'
        else:
            default_image_name = 'banner.png'

        default_image_path = ek.ek(os.path.join, sickbeard.PROG_DIR, 'gui', 'slick', 'images', default_image_name)
        if show and sickbeard.helpers.findCertainShow(sickbeard.showList, int(show)):
            cache_obj = image_cache.ImageCache()

            image_file_name = None
            if which == 'poster':
                image_file_name = cache_obj.poster_path(show)
            if which == 'poster_thumb':
                image_file_name = cache_obj.poster_thumb_path(show)
            if which == 'banner':
                image_file_name = cache_obj.banner_path(show)
            if which == 'banner_thumb':
                image_file_name = cache_obj.banner_thumb_path(show)

            if ek.ek(os.path.isfile, image_file_name):
                with file(image_file_name, 'rb') as img:
                    return img.read()

        with file(default_image_path, 'rb') as img:
            return img.read()

    def _genericMessage(self, subject, message):
        t = PageTemplate(headers=self.request.headers, file="genericMessage.tmpl")
        t.submenu = HomeMenu()
        t.subject = subject
        t.message = message
        return _munge(t)

    browser = WebFileBrowser


class PageTemplate(Template):
    def __init__(self, headers, *args, **KWs):
        KWs['file'] = os.path.join(sickbeard.PROG_DIR, "gui/" + sickbeard.GUI_NAME + "/interfaces/default/",
                                   KWs['file'])
        super(PageTemplate, self).__init__(*args, **KWs)

        self.sbRoot = sickbeard.WEB_ROOT
        self.sbHttpPort = sickbeard.WEB_PORT
        self.sbHandleReverseProxy = sickbeard.HANDLE_REVERSE_PROXY

        if headers['Host'][0] == '[':
            self.sbHost = re.match("^\[.*\]", headers['Host'], re.X | re.M | re.S).group(0)
        else:
            self.sbHost = re.match("^[^:]+", headers['Host'], re.X | re.M | re.S).group(0)

        if "X-Forwarded-Host" in headers:
            self.sbHost = headers['X-Forwarded-Host']
        if "X-Forwarded-Port" in headers:
            sbHttpPort = headers['X-Forwarded-Port']
            self.sbHttpsPort = sbHttpPort
        if "X-Forwarded-Proto" in headers:
            self.sbHttpsEnabled = True if headers['X-Forwarded-Proto'] == 'https' else False

        logPageTitle = 'Logs &amp; Errors'
        if len(classes.ErrorViewer.errors):
            logPageTitle += ' (' + str(len(classes.ErrorViewer.errors)) + ')'
        self.logPageTitle = logPageTitle
        self.sbPID = str(sickbeard.PID)
        self.menu = [
            {'title': 'Home', 'key': 'home'},
            {'title': 'Coming Episodes', 'key': 'comingEpisodes'},
            {'title': 'History', 'key': 'history'},
            {'title': 'Manage', 'key': 'manage'},
            {'title': 'Config', 'key': 'config'},
            {'title': logPageTitle, 'key': 'errorlogs'},
        ]


class IndexerWebUI(MainHandler):
    def __init__(self, config, log=None):
        self.config = config
        self.log = log

def _munge(string):
    return unicode(string).encode('utf-8', 'xmlcharrefreplace')

def ManageMenu():
    manageMenu = [
        {'title': 'Backlog Overview', 'path': 'manage/backlogOverview/'},
        {'title': 'Manage Searches', 'path': 'manage/manageSearches/'},
        {'title': 'Episode Status Management', 'path': 'manage/episodeStatuses/'}, ]

    return manageMenu


class ManageSearches(MainHandler):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file="manage_manageSearches.tmpl")
        # t.backlogPI = sickbeard.backlogSearchScheduler.action.getProgressIndicator()
        t.backlogPaused = sickbeard.searchQueueScheduler.action.is_backlog_paused()  # @UndefinedVariable
        t.backlogRunning = sickbeard.searchQueueScheduler.action.is_backlog_in_progress()  # @UndefinedVariable
        t.dailySearchStatus = sickbeard.dailySearchScheduler.action.amActive  # @UndefinedVariable
        t.findPropersStatus = sickbeard.properFinderScheduler.action.amActive  # @UndefinedVariable

        t.submenu = ManageMenu()

        return _munge(t)


class Manage(MainHandler):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file="manage.tmpl")
        t.submenu = ManageMenu()
        return _munge(t)


    def showEpisodeStatuses(self, indexer_id, whichStatus):
        status_list = [int(whichStatus)]
        if status_list[0] == SNATCHED:
            status_list = Quality.SNATCHED + Quality.SNATCHED_PROPER

        myDB = db.DBConnection()
        cur_show_results = myDB.select(
            "SELECT season, episode, name FROM tv_episodes WHERE showid = ? AND season != 0 AND status IN (" + ','.join(
                ['?'] * len(status_list)) + ")", [int(indexer_id)] + status_list)

        result = {}
        for cur_result in cur_show_results:
            cur_season = int(cur_result["season"])
            cur_episode = int(cur_result["episode"])

            if cur_season not in result:
                result[cur_season] = {}

            result[cur_season][cur_episode] = cur_result["name"]

        return json.dumps(result)


    def episodeStatuses(self, whichStatus=None):

        if whichStatus:
            whichStatus = int(whichStatus)
            status_list = [whichStatus]
            if status_list[0] == SNATCHED:
                status_list = Quality.SNATCHED + Quality.SNATCHED_PROPER
        else:
            status_list = []

        t = PageTemplate(headers=self.request.headers, file="manage_episodeStatuses.tmpl")
        t.submenu = ManageMenu()
        t.whichStatus = whichStatus

        # if we have no status then this is as far as we need to go
        if not status_list:
            return _munge(t)

        myDB = db.DBConnection()
        status_results = myDB.select(
            "SELECT show_name, tv_shows.indexer_id as indexer_id FROM tv_episodes, tv_shows WHERE tv_episodes.status IN (" + ','.join(
                ['?'] * len(
                    status_list)) + ") AND season != 0 AND tv_episodes.showid = tv_shows.indexer_id ORDER BY show_name",
            status_list)

        ep_counts = {}
        show_names = {}
        sorted_show_ids = []
        for cur_status_result in status_results:
            cur_indexer_id = int(cur_status_result["indexer_id"])
            if cur_indexer_id not in ep_counts:
                ep_counts[cur_indexer_id] = 1
            else:
                ep_counts[cur_indexer_id] += 1

            show_names[cur_indexer_id] = cur_status_result["show_name"]
            if cur_indexer_id not in sorted_show_ids:
                sorted_show_ids.append(cur_indexer_id)

        t.show_names = show_names
        t.ep_counts = ep_counts
        t.sorted_show_ids = sorted_show_ids
        return _munge(t)


    def changeEpisodeStatuses(self, oldStatus, newStatus, *args, **kwargs):

        status_list = [int(oldStatus)]
        if status_list[0] == SNATCHED:
            status_list = Quality.SNATCHED + Quality.SNATCHED_PROPER

        to_change = {}

        # make a list of all shows and their associated args
        for arg in kwargs:
            indexer_id, what = arg.split('-')

            # we don't care about unchecked checkboxes
            if kwargs[arg] != 'on':
                continue

            if indexer_id not in to_change:
                to_change[indexer_id] = []

            to_change[indexer_id].append(what)

        myDB = db.DBConnection()
        for cur_indexer_id in to_change:

            # get a list of all the eps we want to change if they just said "all"
            if 'all' in to_change[cur_indexer_id]:
                all_eps_results = myDB.select(
                    "SELECT season, episode FROM tv_episodes WHERE status IN (" + ','.join(
                        ['?'] * len(status_list)) + ") AND season != 0 AND showid = ?",
                    status_list + [cur_indexer_id])
                all_eps = [str(x["season"]) + 'x' + str(x["episode"]) for x in all_eps_results]
                to_change[cur_indexer_id] = all_eps

            Home(self.application, self.request).setStatus(cur_indexer_id, '|'.join(to_change[cur_indexer_id]),
                                                           newStatus, direct=True)

        redirect('/manage/episodeStatuses/')


    def showSubtitleMissed(self, indexer_id, whichSubs):
        myDB = db.DBConnection()
        cur_show_results = myDB.select(
            "SELECT season, episode, name, subtitles FROM tv_episodes WHERE showid = ? AND season != 0 AND status LIKE '%4'",
            [int(indexer_id)])

        result = {}
        for cur_result in cur_show_results:
            if whichSubs == 'all':
                if len(set(cur_result["subtitles"].split(',')).intersection(set(subtitles.wantedLanguages()))) >= len(
                        subtitles.wantedLanguages()):
                    continue
            elif whichSubs in cur_result["subtitles"].split(','):
                continue

            cur_season = int(cur_result["season"])
            cur_episode = int(cur_result["episode"])

            if cur_season not in result:
                result[cur_season] = {}

            if cur_episode not in result[cur_season]:
                result[cur_season][cur_episode] = {}

            result[cur_season][cur_episode]["name"] = cur_result["name"]

            result[cur_season][cur_episode]["subtitles"] = ",".join(
                subliminal.language.Language(subtitle).alpha2 for subtitle in cur_result["subtitles"].split(',')) if not \
                cur_result["subtitles"] == '' else ''

        return json.dumps(result)


    def subtitleMissed(self, whichSubs=None):

        t = PageTemplate(headers=self.request.headers, file="manage_subtitleMissed.tmpl")
        t.submenu = ManageMenu()
        t.whichSubs = whichSubs

        if not whichSubs:
            return _munge(t)

        myDB = db.DBConnection()
        status_results = myDB.select(
            "SELECT show_name, tv_shows.indexer_id as indexer_id, tv_episodes.subtitles subtitles FROM tv_episodes, tv_shows WHERE tv_shows.subtitles = 1 AND tv_episodes.status LIKE '%4' AND tv_episodes.season != 0 AND tv_episodes.showid = tv_shows.indexer_id ORDER BY show_name")

        ep_counts = {}
        show_names = {}
        sorted_show_ids = []
        for cur_status_result in status_results:
            if whichSubs == 'all':
                if len(set(cur_status_result["subtitles"].split(',')).intersection(
                        set(subtitles.wantedLanguages()))) >= len(subtitles.wantedLanguages()):
                    continue
            elif whichSubs in cur_status_result["subtitles"].split(','):
                continue

            cur_indexer_id = int(cur_status_result["indexer_id"])
            if cur_indexer_id not in ep_counts:
                ep_counts[cur_indexer_id] = 1
            else:
                ep_counts[cur_indexer_id] += 1

            show_names[cur_indexer_id] = cur_status_result["show_name"]
            if cur_indexer_id not in sorted_show_ids:
                sorted_show_ids.append(cur_indexer_id)

        t.show_names = show_names
        t.ep_counts = ep_counts
        t.sorted_show_ids = sorted_show_ids
        return _munge(t)


    def downloadSubtitleMissed(self, *args, **kwargs):

        to_download = {}

        # make a list of all shows and their associated args
        for arg in kwargs:
            indexer_id, what = arg.split('-')

            # we don't care about unchecked checkboxes
            if kwargs[arg] != 'on':
                continue

            if indexer_id not in to_download:
                to_download[indexer_id] = []

            to_download[indexer_id].append(what)

        for cur_indexer_id in to_download:
            # get a list of all the eps we want to download subtitles if they just said "all"
            if 'all' in to_download[cur_indexer_id]:
                myDB = db.DBConnection()
                all_eps_results = myDB.select(
                    "SELECT season, episode FROM tv_episodes WHERE status LIKE '%4' AND season != 0 AND showid = ?",
                    [cur_indexer_id])
                to_download[cur_indexer_id] = [str(x["season"]) + 'x' + str(x["episode"]) for x in all_eps_results]

            for epResult in to_download[cur_indexer_id]:
                season, episode = epResult.split('x')

                show = sickbeard.helpers.findCertainShow(sickbeard.showList, int(cur_indexer_id))
                subtitles = show.getEpisode(int(season), int(episode)).downloadSubtitles()

        redirect('/manage/subtitleMissed/')


    def backlogShow(self, indexer_id):

        show_obj = helpers.findCertainShow(sickbeard.showList, int(indexer_id))

        if show_obj:
            sickbeard.backlogSearchScheduler.action.searchBacklog([show_obj])  # @UndefinedVariable

        redirect("/manage/backlogOverview/")


    def backlogOverview(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="manage_backlogOverview.tmpl")
        t.submenu = ManageMenu()

        showCounts = {}
        showCats = {}
        showSQLResults = {}

        myDB = db.DBConnection()
        for curShow in sickbeard.showList:

            epCounts = {}
            epCats = {}
            epCounts[Overview.SKIPPED] = 0
            epCounts[Overview.WANTED] = 0
            epCounts[Overview.QUAL] = 0
            epCounts[Overview.GOOD] = 0
            epCounts[Overview.UNAIRED] = 0
            epCounts[Overview.SNATCHED] = 0

            sqlResults = myDB.select(
                "SELECT * FROM tv_episodes WHERE showid = ? ORDER BY season DESC, episode DESC",
                [curShow.indexerid])

            for curResult in sqlResults:
                curEpCat = curShow.getOverview(int(curResult["status"]))
                if curEpCat:
                    epCats[str(curResult["season"]) + "x" + str(curResult["episode"])] = curEpCat
                    epCounts[curEpCat] += 1

            showCounts[curShow.indexerid] = epCounts
            showCats[curShow.indexerid] = epCats
            showSQLResults[curShow.indexerid] = sqlResults

        t.showCounts = showCounts
        t.showCats = showCats
        t.showSQLResults = showSQLResults

        return _munge(t)


    def massEdit(self, toEdit=None):

        t = PageTemplate(headers=self.request.headers, file="manage_massEdit.tmpl")
        t.submenu = ManageMenu()

        if not toEdit:
            redirect("/manage/")

        showIDs = toEdit.split("|")
        showList = []
        for curID in showIDs:
            curID = int(curID)
            showObj = helpers.findCertainShow(sickbeard.showList, curID)
            if showObj:
                showList.append(showObj)

        flatten_folders_all_same = True
        last_flatten_folders = None

        paused_all_same = True
        last_paused = None

        anime_all_same = True
        last_anime = None

        quality_all_same = True
        last_quality = None

        subtitles_all_same = True
        last_subtitles = None

        scene_all_same = True
        last_scene = None

        root_dir_list = []

        for curShow in showList:

            cur_root_dir = ek.ek(os.path.dirname, curShow._location)
            if cur_root_dir not in root_dir_list:
                root_dir_list.append(cur_root_dir)

            # if we know they're not all the same then no point even bothering
            if paused_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_paused not in (curShow.paused, None):
                    paused_all_same = False
                else:
                    last_paused = curShow.paused

            if anime_all_same:
                # if we had a value already and this value is different then they're not all the same
                if last_anime not in (curShow.is_anime, None):
                    anime_all_same = False
                else:
                    last_anime = curShow.is_anime

            if flatten_folders_all_same:
                if last_flatten_folders not in (None, curShow.flatten_folders):
                    flatten_folders_all_same = False
                else:
                    last_flatten_folders = curShow.flatten_folders

            if quality_all_same:
                if last_quality not in (None, curShow.quality):
                    quality_all_same = False
                else:
                    last_quality = curShow.quality

            if subtitles_all_same:
                if last_subtitles not in (None, curShow.subtitles):
                    subtitles_all_same = False
                else:
                    last_subtitles = curShow.subtitles

            if scene_all_same:
                if last_scene not in (None, curShow.scene):
                    scene_all_same = False
                else:
                    last_scene = curShow.scene

        t.showList = toEdit
        t.paused_value = last_paused if paused_all_same else None
        t.anime_value = last_anime if anime_all_same else None
        t.flatten_folders_value = last_flatten_folders if flatten_folders_all_same else None
        t.quality_value = last_quality if quality_all_same else None
        t.subtitles_value = last_subtitles if subtitles_all_same else None
        t.scene_value = last_scene if scene_all_same else None
        t.root_dir_list = root_dir_list

        return _munge(t)


    def massEditSubmit(self, paused=None, anime=None, scene=None, flatten_folders=None, quality_preset=False,
                       subtitles=None,
                       anyQualities=[], bestQualities=[], toEdit=None, *args, **kwargs):

        dir_map = {}
        for cur_arg in kwargs:
            if not cur_arg.startswith('orig_root_dir_'):
                continue
            which_index = cur_arg.replace('orig_root_dir_', '')
            end_dir = kwargs['new_root_dir_' + which_index]
            dir_map[kwargs[cur_arg]] = end_dir

        showIDs = toEdit.split("|")
        errors = []
        for curShow in showIDs:
            curErrors = []
            showObj = helpers.findCertainShow(sickbeard.showList, int(curShow))
            if not showObj:
                continue

            cur_root_dir = ek.ek(os.path.dirname, showObj._location)
            cur_show_dir = ek.ek(os.path.basename, showObj._location)
            if cur_root_dir in dir_map and cur_root_dir != dir_map[cur_root_dir]:
                new_show_dir = ek.ek(os.path.join, dir_map[cur_root_dir], cur_show_dir)
                logger.log(
                    u"For show " + showObj.name + " changing dir from " + showObj._location + " to " + new_show_dir)
            else:
                new_show_dir = showObj._location

            if paused == 'keep':
                new_paused = showObj.paused
            else:
                new_paused = True if paused == 'enable' else False
            new_paused = 'on' if new_paused else 'off'

            if anime == 'keep':
                new_anime = showObj.is_anime
            else:
                new_anime = True if anime == 'enable' else False
            new_anime = 'on' if new_anime else 'off'

            if scene == 'keep':
                new_scene = showObj.is_scene
            else:
                new_scene = True if scene == 'enable' else False
            new_scene = 'on' if new_scene else 'off'

            if flatten_folders == 'keep':
                new_flatten_folders = showObj.flatten_folders
            else:
                new_flatten_folders = True if flatten_folders == 'enable' else False
            new_flatten_folders = 'on' if new_flatten_folders else 'off'

            if subtitles == 'keep':
                new_subtitles = showObj.subtitles
            else:
                new_subtitles = True if subtitles == 'enable' else False

            new_subtitles = 'on' if new_subtitles else 'off'

            if quality_preset == 'keep':
                anyQualities, bestQualities = Quality.splitQuality(showObj.quality)

            exceptions_list = []

            curErrors += Home(self.application, self.request).editShow(curShow, new_show_dir, anyQualities,
                                                                       bestQualities, exceptions_list,
                                                                       new_flatten_folders, new_paused,
                                                                       subtitles=new_subtitles, anime=new_anime,
                                                                       scene=new_scene, directCall=True)

            if curErrors:
                logger.log(u"Errors: " + str(curErrors), logger.ERROR)
                errors.append('<b>%s:</b>\n<ul>' % showObj.name + ' '.join(
                    ['<li>%s</li>' % error for error in curErrors]) + "</ul>")

        if len(errors) > 0:
            ui.notifications.error('%d error%s while saving changes:' % (len(errors), "" if len(errors) == 1 else "s"),
                                   " ".join(errors))

        redirect("/manage/")


    def manageTorrents(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="manage_torrents.tmpl")
        t.info_download_station = ''
        t.submenu = ManageMenu()

        if re.search('localhost', sickbeard.TORRENT_HOST):

            if sickbeard.LOCALHOST_IP == '':
                t.webui_url = re.sub('localhost', helpers.get_lan_ip(), sickbeard.TORRENT_HOST)
            else:
                t.webui_url = re.sub('localhost', sickbeard.LOCALHOST_IP, sickbeard.TORRENT_HOST)
        else:
            t.webui_url = sickbeard.TORRENT_HOST

        if sickbeard.TORRENT_METHOD == 'utorrent':
            t.webui_url = '/'.join(s.strip('/') for s in (t.webui_url, 'gui/'))
        if sickbeard.TORRENT_METHOD == 'download_station':
            if helpers.check_url(t.webui_url + 'download/'):
                t.webui_url = t.webui_url + 'download/'
            else:
                t.info_download_station = '<p>To have a better experience please set the Download Station alias as <code>download</code>, you can check this setting in the Synology DSM <b>Control Panel</b> > <b>Application Portal</b>. Make sure you allow DSM to be embedded with iFrames too in <b>Control Panel</b> > <b>DSM Settings</b> > <b>Security</b>.</p><br/><p>There is more information about this available <a href="https://github.com/midgetspy/Sick-Beard/pull/338">here</a>.</p><br/>'

        return _munge(t)


    def failedDownloads(self, limit=100, toRemove=None):

        myDB = db.DBConnection('failed.db')

        if limit == "0":
            sqlResults = myDB.select("SELECT * FROM failed")
        else:
            sqlResults = myDB.select("SELECT * FROM failed LIMIT ?", [limit])

        toRemove = toRemove.split("|") if toRemove is not None else []

        for release in toRemove:
            myDB.action('DELETE FROM failed WHERE release = ?', [release])

        if toRemove:
            redirect('/manage/failedDownloads/')

        t = PageTemplate(headers=self.request.headers, file="manage_failedDownloads.tmpl")
        t.failedResults = sqlResults
        t.limit = limit
        t.submenu = ManageMenu()

        return _munge(t)


class History(MainHandler):
    def index(self, limit=100):

        # sqlResults = myDB.select("SELECT h.*, show_name, name FROM history h, tv_shows s, tv_episodes e WHERE h.showid=s.indexer_id AND h.showid=e.showid AND h.season=e.season AND h.episode=e.episode ORDER BY date DESC LIMIT "+str(numPerPage*(p-1))+", "+str(numPerPage))
        myDB = db.DBConnection()
        if limit == "0":
            sqlResults = myDB.select(
                "SELECT h.*, show_name FROM history h, tv_shows s WHERE h.showid=s.indexer_id ORDER BY date DESC")
        else:
            sqlResults = myDB.select(
                "SELECT h.*, show_name FROM history h, tv_shows s WHERE h.showid=s.indexer_id ORDER BY date DESC LIMIT ?",
                [limit])

        history = {'show_id': 0, 'season': 0, 'episode': 0, 'quality': 0,
                   'actions': [{'time': '', 'action': '', 'provider': ''}]}
        compact = []

        for sql_result in sqlResults:

            if not any((history['show_id'] == sql_result['showid']
                        and history['season'] == sql_result['season']
                        and history['episode'] == sql_result['episode']
                        and history['quality'] == sql_result['quality'])
                       for history in compact):

                history = {}
                history['show_id'] = sql_result['showid']
                history['season'] = sql_result['season']
                history['episode'] = sql_result['episode']
                history['quality'] = sql_result['quality']
                history['show_name'] = sql_result['show_name']
                history['resource'] = sql_result['resource']

                action = {}
                history['actions'] = []

                action['time'] = sql_result['date']
                action['action'] = sql_result['action']
                action['provider'] = sql_result['provider']
                action['resource'] = sql_result['resource']
                history['actions'].append(action)
                history['actions'].sort(key=lambda x: x['time'])
                compact.append(history)
            else:
                index = [i for i, dict in enumerate(compact) \
                         if dict['show_id'] == sql_result['showid'] \
                         and dict['season'] == sql_result['season'] \
                         and dict['episode'] == sql_result['episode']
                         and dict['quality'] == sql_result['quality']][0]

                action = {}
                history = compact[index]

                action['time'] = sql_result['date']
                action['action'] = sql_result['action']
                action['provider'] = sql_result['provider']
                action['resource'] = sql_result['resource']
                history['actions'].append(action)
                history['actions'].sort(key=lambda x: x['time'], reverse=True)

        t = PageTemplate(headers=self.request.headers, file="history.tmpl")
        t.historyResults = sqlResults
        t.compactResults = compact
        t.limit = limit
        t.submenu = [
            {'title': 'Clear History', 'path': 'history/clearHistory'},
            {'title': 'Trim History', 'path': 'history/trimHistory'},
        ]

        return _munge(t)


    def clearHistory(self, *args, **kwargs):

        myDB = db.DBConnection()
        myDB.action("DELETE FROM history WHERE 1=1")

        ui.notifications.message('History cleared')
        redirect("/history/")


    def trimHistory(self, *args, **kwargs):

        myDB = db.DBConnection()
        myDB.action("DELETE FROM history WHERE date < " + str(
            (datetime.datetime.today() - datetime.timedelta(days=30)).strftime(history.dateFormat)))

        ui.notifications.message('Removed history entries greater than 30 days old')
        redirect("/history/")


ConfigMenu = [
    {'title': 'General', 'path': 'config/general/'},
    {'title': 'Backup/Restore', 'path': 'config/backuprestore/'},
    {'title': 'Search Settings', 'path': 'config/search/'},
    {'title': 'Search Providers', 'path': 'config/providers/'},
    {'title': 'Subtitles Settings', 'path': 'config/subtitles/'},
    {'title': 'EventGhost', 'path': 'config/eventghost/'},
    {'title': 'Notifications', 'path': 'config/notifications/'},
    {'title': 'Anime', 'path': 'config/anime/'},
    {'title': 'Drives', 'path': 'config/drives/'},
]


class ConfigGeneral(MainHandler):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="config_general.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)


    def saveRootDirs(self, rootDirString=None):
        sickbeard.ROOT_DIRS = rootDirString


    def saveAddShowDefaults(self, defaultStatus, anyQualities, bestQualities, defaultFlattenFolders, subtitles=False,
                            anime=False, scene=False):

        if anyQualities:
            anyQualities = anyQualities.split(',')
        else:
            anyQualities = []

        if bestQualities:
            bestQualities = bestQualities.split(',')
        else:
            bestQualities = []

        newQuality = Quality.combineQualities(map(int, anyQualities), map(int, bestQualities))

        sickbeard.STATUS_DEFAULT = int(defaultStatus)
        sickbeard.QUALITY_DEFAULT = int(newQuality)

        sickbeard.FLATTEN_FOLDERS_DEFAULT = config.checkbox_to_value(defaultFlattenFolders)
        sickbeard.SUBTITLES_DEFAULT = config.checkbox_to_value(subtitles)

        sickbeard.ANIME_DEFAULT = config.checkbox_to_value(anime)
        sickbeard.SCENE_DEFAULT = config.checkbox_to_value(scene)

        sickbeard.save_config()


    def generateKey(self, *args, **kwargs):
        """ Return a new randomized API_KEY
        """

        try:
            from hashlib import md5
        except ImportError:
            from md5 import md5

        # Create some values to seed md5
        t = str(time.time())
        r = str(random.random())

        # Create the md5 instance and give it the current time
        m = md5(t)

        # Update the md5 instance with the random variable
        m.update(r)

        # Return a hex digest of the md5, eg 49f68a5c8493ec2c0bf489821c21fc3b
        logger.log(u"New API generated")
        return m.hexdigest()


    def saveGeneral(self, log_dir=None, web_port=None, web_log=None, encryption_version=None, web_ipv6=None,
                    update_shows_on_start=None, update_frequency=None, launch_browser=None, web_username=None,
                    use_api=None, api_key=None, indexer_default=None, timezone_display=None, cpu_preset=None,
                    web_password=None, version_notify=None, enable_https=None, https_cert=None, https_key=None,
                    handle_reverse_proxy=None, sort_article=None, auto_update=None, proxy_setting=None,
                    anon_redirect=None, git_path=None, calendar_unprotected=None,
                    fuzzy_dating=None, trim_zero=None, date_preset=None, date_preset_na=None, time_preset=None,
                    indexer_timeout=None):

        results = []

        # Misc
        sickbeard.LAUNCH_BROWSER = config.checkbox_to_value(launch_browser)
        config.change_VERSION_NOTIFY(config.checkbox_to_value(version_notify))
        sickbeard.AUTO_UPDATE = config.checkbox_to_value(auto_update)
        # sickbeard.LOG_DIR is set in config.change_LOG_DIR()

        sickbeard.UPDATE_SHOWS_ON_START = config.checkbox_to_value(update_shows_on_start)
        config.change_UPDATE_FREQUENCY(update_frequency)
        sickbeard.LAUNCH_BROWSER = config.checkbox_to_value(launch_browser)
        sickbeard.SORT_ARTICLE = config.checkbox_to_value(sort_article)
        sickbeard.CPU_PRESET = cpu_preset
        sickbeard.ANON_REDIRECT = anon_redirect
        sickbeard.PROXY_SETTING = proxy_setting
        sickbeard.GIT_PATH = git_path
        sickbeard.CALENDAR_UNPROTECTED = config.checkbox_to_value(calendar_unprotected)
        # sickbeard.LOG_DIR is set in config.change_LOG_DIR()

        sickbeard.WEB_PORT = config.to_int(web_port)
        sickbeard.WEB_IPV6 = config.checkbox_to_value(web_ipv6)
        # sickbeard.WEB_LOG is set in config.change_LOG_DIR()
        sickbeard.ENCRYPTION_VERSION = config.checkbox_to_value(encryption_version)
        sickbeard.WEB_USERNAME = web_username
        sickbeard.WEB_PASSWORD = web_password

        sickbeard.FUZZY_DATING = config.checkbox_to_value(fuzzy_dating)
        sickbeard.TRIM_ZERO = config.checkbox_to_value(trim_zero)

        if date_preset:
            sickbeard.DATE_PRESET = date_preset
            discarded_na_data = date_preset_na

        if indexer_default:
            sickbeard.INDEXER_DEFAULT = config.to_int(indexer_default)

        if indexer_timeout:
            sickbeard.INDEXER_TIMEOUT = config.to_int(indexer_timeout)

        if time_preset:
            sickbeard.TIME_PRESET_W_SECONDS = time_preset
            sickbeard.TIME_PRESET = sickbeard.TIME_PRESET_W_SECONDS.replace(u":%S", u"")

        sickbeard.TIMEZONE_DISPLAY = timezone_display

        if not config.change_LOG_DIR(log_dir, web_log):
            results += ["Unable to create directory " + os.path.normpath(log_dir) + ", log directory not changed."]

        sickbeard.USE_API = config.checkbox_to_value(use_api)
        sickbeard.API_KEY = api_key

        sickbeard.ENABLE_HTTPS = config.checkbox_to_value(enable_https)

        if not config.change_HTTPS_CERT(https_cert):
            results += [
                "Unable to create directory " + os.path.normpath(https_cert) + ", https cert directory not changed."]

        if not config.change_HTTPS_KEY(https_key):
            results += [
                "Unable to create directory " + os.path.normpath(https_key) + ", https key directory not changed."]

        sickbeard.HANDLE_REVERSE_PROXY = config.checkbox_to_value(handle_reverse_proxy)

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


class ConfigBackupRestore(MainHandler):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file="config_backuprestore.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)

    def backup(self, backupDir=None):

        finalResult = ''

        if backupDir:
            source = [os.path.join(sickbeard.DATA_DIR, 'sickbeard.db'), sickbeard.CONFIG_FILE]
            target = os.path.join(backupDir, 'sickrage-' + time.strftime('%Y%m%d%H%M%S') + '.zip')

            if helpers.makeZip(source, target):
                finalResult += "Successful backup to " + target
            else:
                finalResult += "Backup FAILED"
        else:
            finalResult += "You need to choose a folder to save your backup to!"

        finalResult += "<br />\n"

        return finalResult


    def restore(self, backupFile=None):


        finalResult = ''

        if backupFile:
            source = backupFile
            target_dir = os.path.join(sickbeard.DATA_DIR, 'restore')

            if helpers.extractZip(source, target_dir):
                finalResult += "Successfully extracted restore files to " + target_dir
                finalResult += "<br>Restart sickrage to complete the restore."
            else:
                finalResult += "Restore FAILED"
        else:
            finalResult += "You need to select a backup file to restore!"

        finalResult += "<br />\n"

        return finalResult


class ConfigSearch(MainHandler):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="config_search.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)


    def saveSearch(self, use_torrents=None,
                   dailysearch_frequency=None,
                   torrent_method=None, backlog_frequency=None,
                   download_propers=None, check_propers_interval=None, allow_high_priority=None,
                   backlog_startup=None, dailysearch_startup=None,
                   torrent_dir=None, torrent_username=None, torrent_password=None, torrent_host=None,
                   torrent_label=None, torrent_path=None, torrent_verify_cert=None,
                   torrent_seed_time=None, torrent_paused=None, torrent_high_bandwidth=None, ignore_words=None):

        results = []

        if not config.change_TORRENT_DIR(torrent_dir):
            results += ["Unable to create directory " + os.path.normpath(torrent_dir) + ", dir not changed."]

        config.change_DAILYSEARCH_FREQUENCY(dailysearch_frequency)
        config.change_BACKLOG_FREQUENCY(backlog_frequency)

        sickbeard.USE_TORRENTS = config.checkbox_to_value(use_torrents)

        sickbeard.TORRENT_METHOD = torrent_method

        sickbeard.IGNORE_WORDS = ignore_words if ignore_words else ""

        sickbeard.DOWNLOAD_PROPERS = config.checkbox_to_value(download_propers)
        sickbeard.CHECK_PROPERS_INTERVAL = check_propers_interval

        sickbeard.ALLOW_HIGH_PRIORITY = config.checkbox_to_value(allow_high_priority)

        sickbeard.DAILYSEARCH_STARTUP = config.checkbox_to_value(dailysearch_startup)
        sickbeard.BACKLOG_STARTUP = config.checkbox_to_value(backlog_startup)

        sickbeard.TORRENT_USERNAME = torrent_username
        sickbeard.TORRENT_PASSWORD = torrent_password
        sickbeard.TORRENT_LABEL = torrent_label
        sickbeard.TORRENT_VERIFY_CERT = config.checkbox_to_value(torrent_verify_cert)
        sickbeard.TORRENT_PATH = torrent_path
        sickbeard.TORRENT_SEED_TIME = torrent_seed_time
        sickbeard.TORRENT_PAUSED = config.checkbox_to_value(torrent_paused)
        sickbeard.TORRENT_HIGH_BANDWIDTH = config.checkbox_to_value(torrent_high_bandwidth)
        sickbeard.TORRENT_HOST = config.clean_url(torrent_host)

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


class ConfigPostProcessing(MainHandler):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="config_postProcessing.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)


    def savePostProcessing(self):

        results = []

        sickbeard.PROCESS_AUTOMATICALLY = config.checkbox_to_value(process_automatically)
        config.change_AUTOPOSTPROCESSER_FREQUENCY(autopostprocesser_frequency)

        if sickbeard.PROCESS_AUTOMATICALLY:
            sickbeard.autoPostProcesserScheduler.silent = False
        else:
            sickbeard.autoPostProcesserScheduler.silent = True

        if unpack:
            if self.isRarSupported() != 'not supported':
                sickbeard.UNPACK = config.checkbox_to_value(unpack)
            else:
                sickbeard.UNPACK = 0
                results.append("Unpacking Not Supported, disabling unpack setting")
        else:
            sickbeard.UNPACK = config.checkbox_to_value(unpack)

        sickbeard.KEEP_PROCESSED_DIR = config.checkbox_to_value(keep_processed_dir)
        sickbeard.PROCESS_METHOD = process_method
        sickbeard.EXTRA_SCRIPTS = [x.strip() for x in extra_scripts.split('|') if x.strip()]
        sickbeard.RENAME_EPISODES = config.checkbox_to_value(rename_episodes)
        sickbeard.AIRDATE_EPISODES = config.checkbox_to_value(airdate_episodes)
        sickbeard.MOVE_ASSOCIATED_FILES = config.checkbox_to_value(move_associated_files)
        sickbeard.NAMING_CUSTOM_ABD = config.checkbox_to_value(naming_custom_abd)
        sickbeard.NAMING_CUSTOM_SPORTS = config.checkbox_to_value(naming_custom_sports)
        sickbeard.NAMING_STRIP_YEAR = config.checkbox_to_value(naming_strip_year)
        sickbeard.USE_FAILED_DOWNLOADS = config.checkbox_to_value(use_failed_downloads)
        sickbeard.DELETE_FAILED = config.checkbox_to_value(delete_failed)
        sickbeard.SKIP_REMOVED_FILES = config.checkbox_to_value(skip_removed_files)
        sickbeard.NFO_RENAME = config.checkbox_to_value(nfo_rename)

        if self.isNamingValid(naming_pattern, naming_multi_ep, anime_type=naming_anime) != "invalid":
            sickbeard.NAMING_PATTERN = naming_pattern
            sickbeard.NAMING_MULTI_EP = int(naming_multi_ep)
            sickbeard.NAMING_ANIME = int(naming_anime)
            sickbeard.NAMING_FORCE_FOLDERS = naming.check_force_season_folders()
        else:
            if int(naming_anime) in [1, 2]:
                results.append("You tried saving an invalid anime naming config, not saving your naming settings")
            else:
                results.append("You tried saving an invalid naming config, not saving your naming settings")

        if self.isNamingValid(naming_abd_pattern, None, abd=True) != "invalid":
            sickbeard.NAMING_ABD_PATTERN = naming_abd_pattern
        else:
            results.append(
                "You tried saving an invalid air-by-date naming config, not saving your air-by-date settings")

        if self.isNamingValid(naming_sports_pattern, None, sports=True) != "invalid":
            sickbeard.NAMING_SPORTS_PATTERN = naming_sports_pattern
        else:
            results.append(
                "You tried saving an invalid sports naming config, not saving your sports settings")

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


    def testNaming(self, pattern=None, multi=None, abd=False, sports=False, anime_type=None):

        if multi is not None:
            multi = int(multi)

        if anime_type is not None:
            anime_type = int(anime_type)

        result = naming.test_name(pattern, multi, abd, sports, anime_type)

        result = ek.ek(os.path.join, result['dir'], result['name'])

        return result


    def isNamingValid(self, pattern=None, multi=None, abd=False, sports=False, anime_type=None):
        if pattern is None:
            return "invalid"

        if multi is not None:
            multi = int(multi)

        if anime_type is not None:
            anime_type = int(anime_type)

        # air by date shows just need one check, we don't need to worry about season folders
        if abd:
            is_valid = naming.check_valid_abd_naming(pattern)
            require_season_folders = False

        # sport shows just need one check, we don't need to worry about season folders
        elif sports:
            is_valid = naming.check_valid_sports_naming(pattern)
            require_season_folders = False

        else:
            # check validity of single and multi ep cases for the whole path
            is_valid = naming.check_valid_naming(pattern, multi, anime_type)

            # check validity of single and multi ep cases for only the file name
            require_season_folders = naming.check_force_season_folders(pattern, multi, anime_type)

        if is_valid and not require_season_folders:
            return "valid"
        elif is_valid and require_season_folders:
            return "seasonfolders"
        else:
            return "invalid"


    def isRarSupported(self, *args, **kwargs):
        """
        Test Packing Support:
            - Simulating in memory rar extraction on test.rar file
        """

        try:
            rar_path = os.path.join(sickbeard.PROG_DIR, 'lib', 'unrar2', 'test.rar')
            testing = RarFile(rar_path).read_files('*test.txt')
            if testing[0][1] == 'This is only a test.':
                return 'supported'
            logger.log(u'Rar Not Supported: Can not read the content of test file', logger.ERROR)
            return 'not supported'
        except Exception, e:
            logger.log(u'Rar Not Supported: ' + ex(e), logger.ERROR)
            return 'not supported'


class ConfigProviders(MainHandler):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file="config_providers.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)

    def canAddTorrentRssProvider(self, name, url, cookies):

        if not name:
            return json.dumps({'error': 'Invalid name specified'})

        providerDict = dict(
            zip([x.getID() for x in sickbeard.torrentRssProviderList], sickbeard.torrentRssProviderList))

        tempProvider = rsstorrent.TorrentRssProvider(name, url, cookies)

        if tempProvider.getID() in providerDict:
            return json.dumps({'error': 'Exists as ' + providerDict[tempProvider.getID()].name})
        else:
            (succ, errMsg) = tempProvider.validateRSS()
            if succ:
                return json.dumps({'success': tempProvider.getID()})
            else:
                return json.dumps({'error': errMsg})


    def saveTorrentRssProvider(self, name, url, cookies):

        if not name or not url:
            return '0'

        providerDict = dict(zip([x.name for x in sickbeard.torrentRssProviderList], sickbeard.torrentRssProviderList))

        if name in providerDict:
            providerDict[name].name = name
            providerDict[name].url = config.clean_url(url)
            providerDict[name].cookies = cookies

            return providerDict[name].getID() + '|' + providerDict[name].configStr()

        else:
            newProvider = rsstorrent.TorrentRssProvider(name, url, cookies)
            sickbeard.torrentRssProviderList.append(newProvider)
            return newProvider.getID() + '|' + newProvider.configStr()


    def deleteTorrentRssProvider(self, id):

        providerDict = dict(
            zip([x.getID() for x in sickbeard.torrentRssProviderList], sickbeard.torrentRssProviderList))

        if id not in providerDict:
            return '0'

        # delete it from the list
        sickbeard.torrentRssProviderList.remove(providerDict[id])

        if id in sickbeard.PROVIDER_ORDER:
            sickbeard.PROVIDER_ORDER.remove(id)

        return '1'


    def saveProviders(self, torrentrss_string='', provider_order=None, **kwargs):

        results = []

        provider_str_list = provider_order.split()
        provider_list = []

        finishedNames = []

        torrentRssProviderDict = dict(
            zip([x.getID() for x in sickbeard.torrentRssProviderList], sickbeard.torrentRssProviderList))
        finishedNames = []

        if torrentrss_string:
            for curTorrentRssProviderStr in torrentrss_string.split('!!!'):

                if not curTorrentRssProviderStr:
                    continue

                curName, curURL, curCookies = curTorrentRssProviderStr.split('|')
                curURL = config.clean_url(curURL)

                newProvider = rsstorrent.TorrentRssProvider(curName, curURL, curCookies)

                curID = newProvider.getID()

                # if it already exists then update it
                if curID in torrentRssProviderDict:
                    torrentRssProviderDict[curID].name = curName
                    torrentRssProviderDict[curID].url = curURL
                    torrentRssProviderDict[curID].cookies = curCookies
                else:
                    sickbeard.torrentRssProviderList.append(newProvider)

                finishedNames.append(curID)

        # delete anything that is missing
        for curProvider in sickbeard.torrentRssProviderList:
            if curProvider.getID() not in finishedNames:
                sickbeard.torrentRssProviderList.remove(curProvider)

        # do the enable/disable
        for curProviderStr in provider_str_list:
            curProvider, curEnabled = curProviderStr.split(':')
            curEnabled = config.to_int(curEnabled)

            curProvObj = [x for x in sickbeard.providers.sortedProviderList() if
                          x.getID() == curProvider and hasattr(x, 'enabled')]
            if curProvObj:
                curProvObj[0].enabled = bool(curEnabled)

            provider_list.append(curProvider)
            if curProvider in torrentRssProviderDict:
                torrentRssProviderDict[curProvider].enabled = bool(curEnabled)

        # dynamically load provider settings
        for curTorrentProvider in [curProvider for curProvider in sickbeard.providers.sortedProviderList() if
                                   curProvider.providerType == sickbeard.GenericProvider.TORRENT]:

            if hasattr(curTorrentProvider, 'minseed'):
                try:
                    curTorrentProvider.minseed = int(str(kwargs[curTorrentProvider.getID() + '_minseed']).strip())
                except:
                    curTorrentProvider.minseed = 0

            if hasattr(curTorrentProvider, 'minleech'):
                try:
                    curTorrentProvider.minleech = int(str(kwargs[curTorrentProvider.getID() + '_minleech']).strip())
                except:
                    curTorrentProvider.minleech = 0

            if hasattr(curTorrentProvider, 'ratio'):
                try:
                    curTorrentProvider.ratio = str(kwargs[curTorrentProvider.getID() + '_ratio']).strip()
                except:
                    curTorrentProvider.ratio = None

            if hasattr(curTorrentProvider, 'digest'):
                try:
                    curTorrentProvider.digest = str(kwargs[curTorrentProvider.getID() + '_digest']).strip()
                except:
                    curTorrentProvider.digest = None

            if hasattr(curTorrentProvider, 'hash'):
                try:
                    curTorrentProvider.hash = str(kwargs[curTorrentProvider.getID() + '_hash']).strip()
                except:
                    curTorrentProvider.hash = None

            if hasattr(curTorrentProvider, 'api_key'):
                try:
                    curTorrentProvider.api_key = str(kwargs[curTorrentProvider.getID() + '_api_key']).strip()
                except:
                    curTorrentProvider.api_key = None

            if hasattr(curTorrentProvider, 'username'):
                try:
                    curTorrentProvider.username = str(kwargs[curTorrentProvider.getID() + '_username']).strip()
                except:
                    curTorrentProvider.username = None

            if hasattr(curTorrentProvider, 'password'):
                try:
                    curTorrentProvider.password = str(kwargs[curTorrentProvider.getID() + '_password']).strip()
                except:
                    curTorrentProvider.password = None

            if hasattr(curTorrentProvider, 'passkey'):
                try:
                    curTorrentProvider.passkey = str(kwargs[curTorrentProvider.getID() + '_passkey']).strip()
                except:
                    curTorrentProvider.passkey = None

            if hasattr(curTorrentProvider, 'confirmed'):
                try:
                    curTorrentProvider.confirmed = config.checkbox_to_value(
                        kwargs[curTorrentProvider.getID() + '_confirmed'])
                except:
                    curTorrentProvider.confirmed = 0

            if hasattr(curTorrentProvider, 'proxy'):
                try:
                    curTorrentProvider.proxy.enabled = config.checkbox_to_value(
                        kwargs[curTorrentProvider.getID() + '_proxy'])
                except:
                    curTorrentProvider.proxy.enabled = 0

                if hasattr(curTorrentProvider.proxy, 'url'):
                    try:
                        curTorrentProvider.proxy.url = str(kwargs[curTorrentProvider.getID() + '_proxy_url']).strip()
                    except:
                        curTorrentProvider.proxy.url = None

            if hasattr(curTorrentProvider, 'freeleech'):
                try:
                    curTorrentProvider.freeleech = config.checkbox_to_value(
                        kwargs[curTorrentProvider.getID() + '_freeleech'])
                except:
                    curTorrentProvider.freeleech = 0

            if hasattr(curTorrentProvider, 'search_mode'):
                try:
                    curTorrentProvider.search_mode = str(kwargs[curTorrentProvider.getID() + '_search_mode']).strip()
                except:
                    curTorrentProvider.search_mode = 'eponly'

            if hasattr(curTorrentProvider, 'search_fallback'):
                try:
                    curTorrentProvider.search_fallback = config.checkbox_to_value(
                        kwargs[curTorrentProvider.getID() + '_search_fallback'])
                except:
                    curTorrentProvider.search_fallback = 0

            if hasattr(curTorrentProvider, 'backlog_only'):
                try:
                    curTorrentProvider.backlog_only = config.checkbox_to_value(
                        kwargs[curTorrentProvider.getID() + '_backlog_only'])
                except:
                    curTorrentProvider.backlog_only = 0

        sickbeard.PROVIDER_ORDER = provider_list

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


class ConfigNotifications(MainHandler):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file="config_notifications.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)


    def saveNotifications(self, use_xbmc=None, xbmc_always_on=None, xbmc_notify_onsnatch=None,
                          xbmc_notify_ondownload=None,
                          xbmc_notify_onsubtitledownload=None, xbmc_update_onlyfirst=None,
                          xbmc_update_library=None, xbmc_update_full=None, xbmc_host=None, xbmc_username=None,
                          xbmc_password=None,
                          use_plex=None, plex_notify_onsnatch=None, plex_notify_ondownload=None,
                          plex_notify_onsubtitledownload=None, plex_update_library=None,
                          plex_server_host=None, plex_host=None, plex_username=None, plex_password=None,
                          use_growl=None, growl_notify_onsnatch=None, growl_notify_ondownload=None,
                          growl_notify_onsubtitledownload=None, growl_host=None, growl_password=None,
                          use_prowl=None, prowl_notify_onsnatch=None, prowl_notify_ondownload=None,
                          prowl_notify_onsubtitledownload=None, prowl_api=None, prowl_priority=0,
                          use_twitter=None, twitter_notify_onsnatch=None, twitter_notify_ondownload=None,
                          twitter_notify_onsubtitledownload=None,
                          use_boxcar=None, boxcar_notify_onsnatch=None, boxcar_notify_ondownload=None,
                          boxcar_notify_onsubtitledownload=None, boxcar_username=None,
                          use_boxcar2=None, boxcar2_notify_onsnatch=None, boxcar2_notify_ondownload=None,
                          boxcar2_notify_onsubtitledownload=None, boxcar2_accesstoken=None,
                          use_pushover=None, pushover_notify_onsnatch=None, pushover_notify_ondownload=None,
                          pushover_notify_onsubtitledownload=None, pushover_userkey=None, pushover_apikey=None,
                          use_libnotify=None, libnotify_notify_onsnatch=None, libnotify_notify_ondownload=None,
                          libnotify_notify_onsubtitledownload=None,
                          use_nmj=None, nmj_host=None, nmj_database=None, nmj_mount=None, use_synoindex=None,
                          use_nmjv2=None, nmjv2_host=None, nmjv2_dbloc=None, nmjv2_database=None,
                          use_trakt=None, trakt_username=None, trakt_password=None, trakt_api=None,
                          trakt_remove_watchlist=None, trakt_use_watchlist=None, trakt_method_add=None,
                          trakt_start_paused=None, trakt_use_recommended=None, trakt_sync=None,
                          use_synologynotifier=None, synologynotifier_notify_onsnatch=None,
                          synologynotifier_notify_ondownload=None, synologynotifier_notify_onsubtitledownload=None,
                          use_pytivo=None, pytivo_notify_onsnatch=None, pytivo_notify_ondownload=None,
                          pytivo_notify_onsubtitledownload=None, pytivo_update_library=None,
                          pytivo_host=None, pytivo_share_name=None, pytivo_tivo_name=None,
                          use_nma=None, nma_notify_onsnatch=None, nma_notify_ondownload=None,
                          nma_notify_onsubtitledownload=None, nma_api=None, nma_priority=0,
                          use_pushalot=None, pushalot_notify_onsnatch=None, pushalot_notify_ondownload=None,
                          pushalot_notify_onsubtitledownload=None, pushalot_authorizationtoken=None,
                          use_pushbullet=None, pushbullet_notify_onsnatch=None, pushbullet_notify_ondownload=None,
                          pushbullet_notify_onsubtitledownload=None, pushbullet_api=None, pushbullet_device=None,
                          pushbullet_device_list=None,
                          use_email=None, email_notify_onsnatch=None, email_notify_ondownload=None,
                          email_notify_onsubtitledownload=None, email_host=None, email_port=25, email_from=None,
                          email_tls=None, email_user=None, email_password=None, email_list=None, email_show_list=None,
                          email_show=None):

        results = []

        sickbeard.USE_PLEX = config.checkbox_to_value(use_plex)
        sickbeard.PLEX_NOTIFY_ONSNATCH = config.checkbox_to_value(plex_notify_onsnatch)
        sickbeard.PLEX_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(plex_notify_ondownload)
        sickbeard.PLEX_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(plex_notify_onsubtitledownload)
        sickbeard.PLEX_UPDATE_LIBRARY = config.checkbox_to_value(plex_update_library)
        sickbeard.PLEX_HOST = config.clean_hosts(plex_host)
        sickbeard.PLEX_SERVER_HOST = config.clean_host(plex_server_host)
        sickbeard.PLEX_USERNAME = plex_username
        sickbeard.PLEX_PASSWORD = plex_password

        sickbeard.USE_BOXCAR2 = config.checkbox_to_value(use_boxcar2)
        sickbeard.BOXCAR2_NOTIFY_ONSNATCH = config.checkbox_to_value(boxcar2_notify_onsnatch)
        sickbeard.BOXCAR2_NOTIFY_ONDOWNLOAD = config.checkbox_to_value(boxcar2_notify_ondownload)
        sickbeard.BOXCAR2_NOTIFY_ONSUBTITLEDOWNLOAD = config.checkbox_to_value(boxcar2_notify_onsubtitledownload)
        sickbeard.BOXCAR2_ACCESSTOKEN = boxcar2_accesstoken

        sickbeard.USE_TRAKT = config.checkbox_to_value(use_trakt)
        sickbeard.TRAKT_USERNAME = trakt_username
        sickbeard.TRAKT_PASSWORD = trakt_password
        sickbeard.TRAKT_API = trakt_api
        sickbeard.TRAKT_REMOVE_WATCHLIST = config.checkbox_to_value(trakt_remove_watchlist)
        sickbeard.TRAKT_USE_WATCHLIST = config.checkbox_to_value(trakt_use_watchlist)
        sickbeard.TRAKT_METHOD_ADD = trakt_method_add
        sickbeard.TRAKT_START_PAUSED = config.checkbox_to_value(trakt_start_paused)
        sickbeard.TRAKT_USE_RECOMMENDED = config.checkbox_to_value(trakt_use_recommended)
        sickbeard.TRAKT_SYNC = config.checkbox_to_value(trakt_sync)

#        if sickbeard.USE_TRAKT:
#            sickbeard.traktCheckerScheduler.silent = False
#        else:
#            sickbeard.traktCheckerScheduler.silent = True

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


class ConfigEventghost(MainHandler):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file="config_eventghost.tmpl")
        return _munge(t)


    def saveEventghost(self, use_eventghost=None, eventghost_server_host=None):

        results = []

        sickbeard.USE_EVENTGHOST = config.checkbox_to_value(use_eventghost)
        sickbeard.EVENTGHOST_SERVER_HOST = config.clean_host(eventghost_server_host)

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


class ConfigSubtitles(MainHandler):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file="config_subtitles.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)


    def saveSubtitles(self, use_subtitles=None, subtitles_plugins=None, subtitles_languages=None, subtitles_dir=None,
                      service_order=None, subtitles_history=None, subtitles_finder_frequency=None):
        results = []

        if subtitles_finder_frequency == '' or subtitles_finder_frequency is None:
            subtitles_finder_frequency = 1

        if use_subtitles == "on":
            if sickbeard.subtitlesFinderScheduler.thread is None or not sickbeard.subtitlesFinderScheduler.thread.isAlive():
                sickbeard.subtitlesFinderScheduler.silent = False
                sickbeard.subtitlesFinderScheduler.initThread()
        else:
            sickbeard.subtitlesFinderScheduler.abort = True
            sickbeard.subtitlesFinderScheduler.silent = True
            logger.log(u"Waiting for the SUBTITLESFINDER thread to exit")
            try:
                sickbeard.subtitlesFinderScheduler.thread.join(5)
            except:
                pass

        sickbeard.USE_SUBTITLES = config.checkbox_to_value(use_subtitles)
        sickbeard.SUBTITLES_LANGUAGES = [lang.alpha2 for lang in subtitles.isValidLanguage(
            subtitles_languages.replace(' ', '').split(','))] if subtitles_languages != ''  else ''
        sickbeard.SUBTITLES_DIR = subtitles_dir
        sickbeard.SUBTITLES_HISTORY = config.checkbox_to_value(subtitles_history)
        sickbeard.SUBTITLES_FINDER_FREQUENCY = config.to_int(subtitles_finder_frequency, default=1)

        # Subtitles services
        services_str_list = service_order.split()
        subtitles_services_list = []
        subtitles_services_enabled = []
        for curServiceStr in services_str_list:
            curService, curEnabled = curServiceStr.split(':')
            subtitles_services_list.append(curService)
            subtitles_services_enabled.append(int(curEnabled))

        sickbeard.SUBTITLES_SERVICES_LIST = subtitles_services_list
        sickbeard.SUBTITLES_SERVICES_ENABLED = subtitles_services_enabled

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


class ConfigAnime(MainHandler):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="config_anime.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)


    def saveAnime(self, use_anidb=None, anidb_username=None, anidb_password=None, anidb_use_mylist=None,
                  split_home=None):

        results = []

        if use_anidb == "on":
            use_anidb = 1
        else:
            use_anidb = 0

        if anidb_use_mylist == "on":
            anidb_use_mylist = 1
        else:
            anidb_use_mylist = 0

        if split_home == "on":
            split_home = 1
        else:
            split_home = 0

        sickbeard.USE_ANIDB = use_anidb
        sickbeard.ANIDB_USERNAME = anidb_username
        sickbeard.ANIDB_PASSWORD = anidb_password
        sickbeard.ANIDB_USE_MYLIST = anidb_use_mylist
        sickbeard.ANIME_SPLIT_HOME = split_home

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


class ConfigDrives(MainHandler):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="config_drives.tmpl")
        t.submenu = ConfigMenu
        return _munge(t)


    def saveDrives(self, use_drives=None, use_driveA=None, use_driveB=None, use_driveC=None, \
                  driveA_name=None, driveB_name=None, driveC_name=None,
                  split_home=None):

        results = []

        if use_drives == "on":
            use_drives = 1
        else:
            use_drives = 0
			
        if use_driveA == "on":
            use_driveA = 1
        else:
            use_driveA = 0
			
        if use_driveB == "on":
            use_driveB = 1
        else:
            use_driveB = 0
			
        if use_driveC == "on":
            use_driveC = 1
        else:
            use_driveC = 0


        sickbeard.USE_DRIVES = use_drives
        sickbeard.USE_DRIVEA = use_driveA
        sickbeard.USE_DRIVEB = use_driveB
        sickbeard.USE_DRIVEC = use_driveC
        sickbeard.DRIVEA_NAME = driveA_name
        sickbeard.DRIVEB_NAME = driveB_name
        sickbeard.DRIVEC_NAME = driveC_name

        sickbeard.save_config()

        if len(results) > 0:
            for x in results:
                logger.log(x, logger.ERROR)
            ui.notifications.error('Error(s) Saving Configuration',
                                   '<br />\n'.join(results))
        else:
            ui.notifications.message('Configuration Saved', ek.ek(os.path.join, sickbeard.CONFIG_FILE))


class Config(MainHandler):
    def index(self, *args, **kwargs):
        t = PageTemplate(headers=self.request.headers, file="config.tmpl")
        t.submenu = ConfigMenu

        return _munge(t)

    # map class names to urls
    general = ConfigGeneral
    backuprestore = ConfigBackupRestore
    search = ConfigSearch
    providers = ConfigProviders
    subtitles = ConfigSubtitles
    postProcessing = ConfigPostProcessing
    notifications = ConfigNotifications
    anime = ConfigAnime
    eventghost = ConfigEventghost
    drives = ConfigDrives


def haveXBMC():
    return sickbeard.USE_XBMC and sickbeard.XBMC_UPDATE_LIBRARY


def havePLEX():
    return sickbeard.USE_PLEX and sickbeard.PLEX_UPDATE_LIBRARY


def haveTORRENT():
    if sickbeard.USE_TORRENTS and sickbeard.TORRENT_METHOD != 'blackhole' \
            and (sickbeard.ENABLE_HTTPS and sickbeard.TORRENT_HOST[:5] == 'https'
                 or not sickbeard.ENABLE_HTTPS and sickbeard.TORRENT_HOST[:5] == 'http:'):
        return True
    else:
        return False


def HomeMenu():
    return [
        {'title': 'Add Shows', 'path': 'home/addShows/', },
        {'title': 'Manual Post-Processing', 'path': 'home/postprocess/'},
        {'title': 'Update XBMC', 'path': 'home/updateXBMC/', 'requires': haveXBMC},
        {'title': 'Update Plex', 'path': 'home/updatePLEX/', 'requires': havePLEX},
        {'title': 'Manage Torrents', 'path': 'manage/manageTorrents', 'requires': haveTORRENT},
        {'title': 'Restart', 'path': 'home/restart/?pid=' + str(sickbeard.PID), 'confirm': True},
        {'title': 'Shutdown', 'path': 'home/shutdown/?pid=' + str(sickbeard.PID), 'confirm': True},
    ]


class HomePostProcess(MainHandler):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="home_postprocess.tmpl")
        t.submenu = HomeMenu()
        return _munge(t)


    def forceVersionCheck(self, *args, **kwargs):

        # force a check to see if there is a new version
        if sickbeard.versionCheckScheduler.action.check_for_new_version(force=True):
            logger.log(u"Forcing version check")

        redirect("/home/")


class NewHomeAddShows(MainHandler):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="home_addShows.tmpl")
        t.submenu = HomeMenu()
        return _munge(t)


    def getIndexerLanguages(self, *args, **kwargs):
        result = sickbeard.indexerApi().config['valid_languages']

        # Make sure list is sorted alphabetically but 'en' is in front
        if 'en' in result:
            del result[result.index('en')]
        result.sort()
        result.insert(0, 'en')

        return json.dumps({'results': result})


    def sanitizeFileName(self, name):
        return helpers.sanitizeFileName(name)


    def searchIndexersForShowName(self, search_term, lang="en", indexer=None):
        if not lang or lang == 'null':
            lang = "en"

        search_term = search_term.encode('utf-8')

        results = {}
        final_results = []

        # Query Indexers for each search term and build the list of results
        for indexer in sickbeard.indexerApi().indexers if not int(indexer) else [int(indexer)]:
            lINDEXER_API_PARMS = sickbeard.indexerApi(indexer).api_params.copy()
            lINDEXER_API_PARMS['language'] = lang
            lINDEXER_API_PARMS['custom_ui'] = classes.AllShowsListUI
            t = sickbeard.indexerApi(indexer).indexer(**lINDEXER_API_PARMS)

            logger.log("Searching for Show with searchterm: %s on Indexer: %s" % (
                search_term, sickbeard.indexerApi(indexer).name), logger.DEBUG)
            try:
                # add search results
                results.setdefault(indexer, []).extend(t[search_term])
            except Exception, e:
                continue

        map(final_results.extend,
            ([[sickbeard.indexerApi(id).name, id, sickbeard.indexerApi(id).config["show_url"], int(show['id']),
               show['seriesname'], show['firstaired']] for show in shows] for id, shows in results.items()))

        lang_id = sickbeard.indexerApi().config['langabbv_to_id'][lang]
        return json.dumps({'results': final_results, 'langid': lang_id})


    def massAddTable(self, rootDir=None):
        t = PageTemplate(headers=self.request.headers, file="home_massAddTable.tmpl")
        t.submenu = HomeMenu()

        if not rootDir:
            return "No folders selected."
        elif type(rootDir) != list:
            root_dirs = [rootDir]
        else:
            root_dirs = rootDir

        root_dirs = [urllib.unquote_plus(x) for x in root_dirs]

        if sickbeard.ROOT_DIRS:
            default_index = int(sickbeard.ROOT_DIRS.split('|')[0])
        else:
            default_index = 0

        if len(root_dirs) > default_index:
            tmp = root_dirs[default_index]
            if tmp in root_dirs:
                root_dirs.remove(tmp)
                root_dirs = [tmp] + root_dirs

        dir_list = []

        myDB = db.DBConnection()
        for root_dir in root_dirs:
            try:
                file_list = ek.ek(os.listdir, root_dir)
            except:
                continue

            for cur_file in file_list:

                cur_path = ek.ek(os.path.normpath, ek.ek(os.path.join, root_dir, cur_file))
                if not ek.ek(os.path.isdir, cur_path):
                    continue

                cur_dir = {
                    'dir': cur_path,
                    'display_dir': '<b>' + ek.ek(os.path.dirname, cur_path) + os.sep + '</b>' + ek.ek(
                        os.path.basename,
                        cur_path),
                    }

                # see if the folder is in XBMC already
                dirResults = myDB.select("SELECT * FROM tv_shows WHERE location = ?", [cur_path])

                if dirResults:
                    cur_dir['added_already'] = True
                else:
                    cur_dir['added_already'] = False

                dir_list.append(cur_dir)

                indexer_id = show_name = indexer = None
                for cur_provider in sickbeard.metadata_provider_dict.values():
                    (indexer_id, show_name, indexer) = cur_provider.retrieveShowMetadata(cur_path)
                    if show_name: break

                # default to TVDB if indexer was not detected
                if show_name and not (indexer and indexer_id):
                    (sn, idx, id) = helpers.searchIndexerForShowID(show_name, indexer, indexer_id)

                    # set indexer and indexer_id from found info
                    if indexer is None and idx:
                        indexer = idx

                    if indexer_id is None and id:
                        indexer_id = id

                cur_dir['existing_info'] = (indexer_id, show_name, indexer)

                if indexer_id and helpers.findCertainShow(sickbeard.showList, indexer_id):
                    cur_dir['added_already'] = True

        t.dirList = dir_list

        return _munge(t)


    def newShow(self, show_to_add=None, other_shows=None):
        """
        Display the new show page which collects a tvdb id, folder, and extra options and
        posts them to addNewShow
        """
        t = PageTemplate(headers=self.request.headers, file="home_newShow.tmpl")
        t.submenu = HomeMenu()

        indexer, show_dir, indexer_id, show_name = self.split_extra_show(show_to_add)

        if indexer_id and indexer and show_name:
            use_provided_info = True
        else:
            use_provided_info = False

        # tell the template whether we're giving it show name & Indexer ID
        t.use_provided_info = use_provided_info

        # use the given show_dir for the indexer search if available
        if not show_dir:
            t.default_show_name = ''
        elif not show_name:
            t.default_show_name = ek.ek(os.path.basename, ek.ek(os.path.normpath, show_dir)).replace('.', ' ')
        else:
            t.default_show_name = show_name

        # carry a list of other dirs if given
        if not other_shows:
            other_shows = []
        elif type(other_shows) != list:
            other_shows = [other_shows]

        if use_provided_info:
            t.provided_indexer_id = int(indexer_id or 0)
            t.provided_indexer_name = show_name

        t.provided_show_dir = show_dir
        t.other_shows = other_shows
        t.provided_indexer = int(indexer or sickbeard.INDEXER_DEFAULT)
        t.indexers = sickbeard.indexerApi().indexers

        return _munge(t)

    def recommendedShows(self, *args, **kwargs):
        """
        Display the new show page which collects a tvdb id, folder, and extra options and
        posts them to addNewShow
        """
        t = PageTemplate(headers=self.request.headers, file="home_recommendedShows.tmpl")
        t.submenu = HomeMenu()

        return _munge(t)

    def getRecommendedShows(self, *args, **kwargs):
        final_results = []

        logger.log(u"Getting recommended shows from Trakt.tv", logger.DEBUG)
        recommendedlist = TraktCall("recommendations/shows.json/%API%/" + sickbeard.TRAKT_USERNAME,
                                    sickbeard.TRAKT_API,
                                    sickbeard.TRAKT_USERNAME, sickbeard.TRAKT_PASSWORD)
        if recommendedlist is None:
            logger.log(u"Could not connect to trakt service, aborting recommended list update", logger.ERROR)
            return

        map(final_results.append,
            ([int(show['tvdb_id']), show['url'], show['title'], show['overview'],
              datetime.date.fromtimestamp(int(show['first_aired']) / 1000.0).strftime('%Y%m%d')] for show in
             recommendedlist if not helpers.findCertainShow(sickbeard.showList, indexerid=int(show['tvdb_id']))))

        return json.dumps({'results': final_results})

    def addRecommendedShow(self, whichSeries=None, indexerLang="en", rootDir=None, defaultStatus=None,
                           anyQualities=None, bestQualities=None, flatten_folders=None, subtitles=None,
                           fullShowPath=None, other_shows=None, skipShow=None, providedIndexer=None, anime=None,
                           scene=None):

        indexer = 1
        indexer_name = sickbeard.indexerApi(int(indexer)).name
        show_url = whichSeries.split('|')[1]
        indexer_id = whichSeries.split('|')[0]
        show_name = whichSeries.split('|')[2]

        return self.addNewShow('|'.join([indexer_name, str(indexer), show_url, indexer_id, show_name, ""]),
                               indexerLang, rootDir,
                               defaultStatus,
                               anyQualities, bestQualities, flatten_folders, subtitles, fullShowPath, other_shows,
                               skipShow, providedIndexer, anime, scene)

    def trendingShows(self, *args, **kwargs):
        """
        Display the new show page which collects a tvdb id, folder, and extra options and
        posts them to addNewShow
        """
        t = PageTemplate(headers=self.request.headers, file="home_trendingShows.tmpl")
        t.submenu = HomeMenu()

        t.trending_shows = TraktCall("shows/trending.json/%API%/", sickbeard.TRAKT_API_KEY)

        return _munge(t)

    def existingShows(self, *args, **kwargs):
        """
        Prints out the page to add existing shows from a root dir
        """
        t = PageTemplate(headers=self.request.headers, file="home_addExistingShow.tmpl")
        t.submenu = HomeMenu()

        return _munge(t)

    def addTraktShow(self, indexer_id, showName):
        if helpers.findCertainShow(sickbeard.showList, int(indexer_id)):
            return

        root_dirs = sickbeard.ROOT_DIRS.split('|')
        location = root_dirs[int(root_dirs[0]) + 1]

        show_dir = ek.ek(os.path.join, location, helpers.sanitizeFileName(showName))
        dir_exists = helpers.makeDir(show_dir)
        if not dir_exists:
            logger.log(u"Unable to create the folder " + show_dir + ", can't add the show", logger.ERROR)
            return
        else:
            helpers.chmodAsParent(show_dir)

        sickbeard.showQueueScheduler.action.addShow(1, int(indexer_id), show_dir,
                                                    default_status=sickbeard.STATUS_DEFAULT,
                                                    quality=sickbeard.QUALITY_DEFAULT,
                                                    flatten_folders=sickbeard.FLATTEN_FOLDERS_DEFAULT,
                                                    subtitles=sickbeard.SUBTITLES_DEFAULT,
                                                    anime=sickbeard.ANIME_DEFAULT,
                                                    scene=sickbeard.SCENE_DEFAULT)

        ui.notifications.message('Show added', 'Adding the specified show into ' + show_dir)

        # done adding show
        redirect('/home/')

    def addNewShow(self, whichSeries=None, indexerLang="en", rootDir=None, defaultStatus=None,
                   anyQualities=None, bestQualities=None, flatten_folders=None, subtitles=None,
                   fullShowPath=None, other_shows=None, skipShow=None, providedIndexer=None, anime=None,
                   scene=None):
        """
        Receive tvdb id, dir, and other options and create a show from them. If extra show dirs are
        provided then it forwards back to newShow, if not it goes to /home.
        """

        # grab our list of other dirs if given
        if not other_shows:
            other_shows = []
        elif type(other_shows) != list:
            other_shows = [other_shows]

        def finishAddShow():
            # if there are no extra shows then go home
            if not other_shows:
                redirect('/home/')

            # peel off the next one
            next_show_dir = other_shows[0]
            rest_of_show_dirs = other_shows[1:]

            # go to add the next show
            return self.newShow(next_show_dir, rest_of_show_dirs)

        # if we're skipping then behave accordingly
        if skipShow:
            return finishAddShow()

        # sanity check on our inputs
        if (not rootDir and not fullShowPath) or not whichSeries:
            return "Missing params, no Indexer ID or folder:" + repr(whichSeries) + " and " + repr(
                rootDir) + "/" + repr(fullShowPath)

        # figure out what show we're adding and where
        series_pieces = whichSeries.split('|')
        if (whichSeries and rootDir) or (whichSeries and fullShowPath and len(series_pieces) > 1):
            if len(series_pieces) < 6:
                logger.log("Unable to add show due to show selection. Not anough arguments: %s" % (repr(series_pieces)),
                           logger.ERROR)
                ui.notifications.error("Unknown error. Unable to add show due to problem with show selection.")
                redirect('/home/addShows/existingShows/')
            indexer = int(series_pieces[1])
            indexer_id = int(series_pieces[3])
            show_name = series_pieces[4]
        else:
            # if no indexer was provided use the default indexer set in General settings
            if not providedIndexer:
                providedIndexer = sickbeard.INDEXER_DEFAULT

            indexer = int(providedIndexer)
            indexer_id = int(whichSeries)
            show_name = os.path.basename(os.path.normpath(fullShowPath))

        # use the whole path if it's given, or else append the show name to the root dir to get the full show path
        if fullShowPath:
            show_dir = ek.ek(os.path.normpath, fullShowPath)
        else:
            show_dir = ek.ek(os.path.join, rootDir, helpers.sanitizeFileName(show_name))

        # blanket policy - if the dir exists you should have used "add existing show" numbnuts
        if ek.ek(os.path.isdir, show_dir) and not fullShowPath:
            ui.notifications.error("Unable to add show", "Folder " + show_dir + " exists already")
            redirect('/home/addShows/existingShows/')

        # don't create show dir if config says not to
        if sickbeard.ADD_SHOWS_WO_DIR:
            logger.log(u"Skipping initial creation of " + show_dir + " due to config.ini setting")
        else:
            dir_exists = helpers.makeDir(show_dir)
            if not dir_exists:
                logger.log(u"Unable to create the folder " + show_dir + ", can't add the show", logger.ERROR)
                ui.notifications.error("Unable to add show",
                                       "Unable to create the folder " + show_dir + ", can't add the show")
                redirect("/home/")
            else:
                helpers.chmodAsParent(show_dir)

        # prepare the inputs for passing along
        scene = config.checkbox_to_value(scene)
        anime = config.checkbox_to_value(anime)
        flatten_folders = config.checkbox_to_value(flatten_folders)
        subtitles = config.checkbox_to_value(subtitles)

        if not anyQualities:
            anyQualities = []
        if not bestQualities:
            bestQualities = []
        if type(anyQualities) != list:
            anyQualities = [anyQualities]
        if type(bestQualities) != list:
            bestQualities = [bestQualities]
        newQuality = Quality.combineQualities(map(int, anyQualities), map(int, bestQualities))

        # add the show
        sickbeard.showQueueScheduler.action.addShow(indexer, indexer_id, show_dir, int(defaultStatus), newQuality,
                                                    flatten_folders, indexerLang, subtitles, anime,
                                                    scene)  # @UndefinedVariable
        ui.notifications.message('Show added', 'Adding the specified show into ' + show_dir)

        return finishAddShow()

    def split_extra_show(self, extra_show):
        if not extra_show:
            return (None, None, None, None)
        split_vals = extra_show.split('|')
        if len(split_vals) < 4:
            indexer = split_vals[0]
            show_dir = split_vals[1]
            return (indexer, show_dir, None, None)
        indexer = split_vals[0]
        show_dir = split_vals[1]
        indexer_id = split_vals[2]
        show_name = '|'.join(split_vals[3:])

        return (indexer, show_dir, indexer_id, show_name)


    def addExistingShows(self, shows_to_add=None, promptForSettings=None):
        """
        Receives a dir list and add them. Adds the ones with given TVDB IDs first, then forwards
        along to the newShow page.
        """

        # grab a list of other shows to add, if provided
        if not shows_to_add:
            shows_to_add = []
        elif type(shows_to_add) != list:
            shows_to_add = [shows_to_add]

        shows_to_add = [urllib.unquote_plus(x) for x in shows_to_add]

        promptForSettings = config.checkbox_to_value(promptForSettings)

        indexer_id_given = []
        dirs_only = []
        # separate all the ones with Indexer IDs
        for cur_dir in shows_to_add:
            if '|' in cur_dir:
                split_vals = cur_dir.split('|')
                if len(split_vals) < 3:
                    dirs_only.append(cur_dir)
            if not '|' in cur_dir:
                dirs_only.append(cur_dir)
            else:
                indexer, show_dir, indexer_id, show_name = self.split_extra_show(cur_dir)

                if not show_dir or not indexer_id or not show_name:
                    continue

                indexer_id_given.append((int(indexer), show_dir, int(indexer_id), show_name))


        # if they want me to prompt for settings then I will just carry on to the newShow page
        if promptForSettings and shows_to_add:
            return self.newShow(shows_to_add[0], shows_to_add[1:])

        # if they don't want me to prompt for settings then I can just add all the nfo shows now
        num_added = 0
        for cur_show in indexer_id_given:
            indexer, show_dir, indexer_id, show_name = cur_show

            if indexer is not None and indexer_id is not None:
                # add the show
                sickbeard.showQueueScheduler.action.addShow(indexer, indexer_id, show_dir,
                                                            default_status=sickbeard.STATUS_DEFAULT,
                                                            quality=sickbeard.QUALITY_DEFAULT,
                                                            flatten_folders=sickbeard.FLATTEN_FOLDERS_DEFAULT,
                                                            subtitles=sickbeard.SUBTITLES_DEFAULT,
                                                            anime=sickbeard.ANIME_DEFAULT,
                                                            scene=sickbeard.SCENE_DEFAULT)
                num_added += 1

        if num_added:
            ui.notifications.message("Shows Added",
                                     "Automatically added " + str(num_added) + " from their existing metadata files")

        # if we're done then go home
        if not dirs_only:
            redirect('/home/')

        # for the remaining shows we need to prompt for each one, so forward this on to the newShow page
        return self.newShow(dirs_only[0], dirs_only[1:])


ErrorLogsMenu = [
    {'title': 'Clear Errors', 'path': 'errorlogs/clearerrors/'},
    # { 'title': 'View Log',  'path': 'errorlogs/viewlog'  },
]


class ErrorLogs(MainHandler):
    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="errorlogs.tmpl")
        t.submenu = ErrorLogsMenu

        return _munge(t)


    def clearerrors(self, *args, **kwargs):
        classes.ErrorViewer.clear()
        redirect("/errorlogs/")


    def viewlog(self, minLevel=logger.MESSAGE, maxLines=500):

        t = PageTemplate(headers=self.request.headers, file="viewlogs.tmpl")
        t.submenu = ErrorLogsMenu

        minLevel = int(minLevel)

        data = []
        if os.path.isfile(logger.sb_log_instance.log_file_path):
            with ek.ek(open, logger.sb_log_instance.log_file_path) as f:
                data = f.readlines()

        regex = "^(\d\d\d\d)\-(\d\d)\-(\d\d)\s*(\d\d)\:(\d\d):(\d\d)\s*([A-Z]+)\s*(.+?)\s*\:\:\s*(.*)$"

        finalData = []

        numLines = 0
        lastLine = False
        numToShow = min(maxLines, len(data))

        for x in reversed(data):

            x = x.decode('utf-8', 'replace')
            match = re.match(regex, x)

            if match:
                level = match.group(7)
                if level not in logger.reverseNames:
                    lastLine = False
                    continue

                if logger.reverseNames[level] >= minLevel:
                    lastLine = True
                    finalData.append(x)
                else:
                    lastLine = False
                    continue

            elif lastLine:
                finalData.append("AA" + x)

            numLines += 1

            if numLines >= numToShow:
                break

        result = "".join(finalData)

        t.logLines = result
        t.minLevel = minLevel

        return _munge(t)


class Home(MainHandler):
    def is_alive(self, *args, **kwargs):
        if 'callback' in kwargs and '_' in kwargs:
            callback, _ = kwargs['callback'], kwargs['_']
        else:
            return "Error: Unsupported Request. Send jsonp request with 'callback' variable in the query string."

        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')
        self.set_header('Content-Type', 'text/javascript')
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Headers', 'x-requested-with')

        if sickbeard.started:
            return callback + '(' + json.dumps(
                {"msg": str(sickbeard.PID)}) + ');'
        else:
            return callback + '(' + json.dumps({"msg": "nope"}) + ');'


    def index(self, *args, **kwargs):

        t = PageTemplate(headers=self.request.headers, file="home.tmpl")
        t.submenu = HomeMenu()
        t.temps = getTemps()
        t.space = getSpace()
        t.width = divWidth()
        return _munge(t)

    def testBoxcar2(self, accesstoken=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        result = notifiers.boxcar2_notifier.test_notify(accesstoken)
        if result:
            return "Boxcar2 notification succeeded. Check your Boxcar2 clients to make sure it worked"
        else:
            return "Error sending Boxcar2 notification"

    def testXBMC(self, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        host = config.clean_hosts(host)
        finalResult = ''
        for curHost in [x.strip() for x in host.split(",")]:
            curResult = notifiers.xbmc_notifier.test_notify(urllib.unquote_plus(curHost), username, password)
            if len(curResult.split(":")) > 2 and 'OK' in curResult.split(":")[2]:
                finalResult += "Test XBMC notice sent successfully to " + urllib.unquote_plus(curHost)
            else:
                finalResult += "Test XBMC notice failed to " + urllib.unquote_plus(curHost)
            finalResult += "<br />\n"

        return finalResult


    def testPLEX(self, host=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        finalResult = ''
        for curHost in [x.strip() for x in host.split(",")]:
            curResult = notifiers.plex_notifier.test_notify(urllib.unquote_plus(curHost), username, password)
            if len(curResult.split(":")) > 2 and 'OK' in curResult.split(":")[2]:
                finalResult += "Test Plex notice sent successfully to " + urllib.unquote_plus(curHost)
            else:
                finalResult += "Test Plex notice failed to " + urllib.unquote_plus(curHost)
            finalResult += "<br />\n"

        return finalResult

    def testTrakt(self, api=None, username=None, password=None):
        self.set_header('Cache-Control', 'max-age=0,no-cache,no-store')

        result = notifiers.trakt_notifier.test_notify(api, username, password)
        if result:
            return "Test notice sent successfully to Trakt"
        else:
            return "Test notice failed to Trakt"

    def shutdown(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            redirect("/home/")

        threading.Timer(2, sickbeard.invoke_shutdown).start()

        title = "Shutting down"
        message = "SickRage is shutting down..."

        return self._genericMessage(title, message)

    def restart(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            redirect("/home/")

        t = PageTemplate(headers=self.request.headers, file="restart.tmpl")
        t.submenu = HomeMenu()

        # restart
        threading.Timer(5, sickbeard.invoke_restart, [False]).start()

        return _munge(t)

    def update(self, pid=None):

        if str(pid) != str(sickbeard.PID):
            redirect("/home/")

        updated = sickbeard.versionCheckScheduler.action.update()  # @UndefinedVariable
        if updated:
            # do a hard restart
            threading.Timer(2, sickbeard.invoke_restart, [False]).start()

            t = PageTemplate(headers=self.request.headers, file="restart_bare.tmpl")
            return _munge(t)
        else:
            return self._genericMessage("Update Failed",
                                        "Update wasn't successful, not restarting. Check your log for more information.")


    def updateXBMC(self, showName=None):

        # only send update to first host in the list -- workaround for xbmc sql backend users
        if sickbeard.XBMC_UPDATE_ONLYFIRST:
            # only send update to first host in the list -- workaround for xbmc sql backend users
            host = sickbeard.XBMC_HOST.split(",")[0].strip()
        else:
            host = sickbeard.XBMC_HOST

        if notifiers.xbmc_notifier.update_library(showName=showName):
            ui.notifications.message("Library update command sent to XBMC host(s): " + host)
        else:
            ui.notifications.error("Unable to contact one or more XBMC host(s): " + host)
        redirect('/home/')


    def updatePLEX(self, *args, **kwargs):
        urllib.urlopen("http://192.168.0.20:8088/?pause")
        if notifiers.plex_notifier.update_library():
            ui.notifications.message(
                "Library update command sent to Plex Media Server host: " + sickbeard.PLEX_SERVER_HOST)
        else:
            ui.notifications.error("Unable to contact Plex Media Server host: " + sickbeard.PLEX_SERVER_HOST)
        redirect('/home/')

    def buttonsPLEX(self, action, *kwargs):
        actionURL = ("http://192.168.0.20:8088/?%s") % action
        urllib.urlopen(actionURL)
        redirect('/home/')


class UI(MainHandler):
    def add_message(self):
        ui.notifications.message('Test 1', 'This is test number 1')
        ui.notifications.error('Test 2', 'This is test number 2')

        return "ok"

    def get_messages(self):
        messages = {}
        cur_notification_num = 1
        for cur_notification in ui.notifications.get_notifications(self.request.remote_ip):
            messages['notification-' + str(cur_notification_num)] = {'title': cur_notification.title,
                                                                     'message': cur_notification.message,
                                                                     'type': cur_notification.type}
            cur_notification_num += 1

        return json.dumps(messages)
