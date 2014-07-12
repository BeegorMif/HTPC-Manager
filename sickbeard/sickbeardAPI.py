import urllib2

from hashlib import sha1
from sickbeard import logger
 
try:
    import json
except ImportError:
    from lib import simplejson as json

def SickbeardCall(command, host, api, data={}):
    """
    Altered Trakt methods from SickBeard/SickRage
    A generic method for communicating with trakt. Uses the method and data provided along
    with the auth info to send the command.

    method: The URL to use at trakt, relative, no leading slash.
    api: The API string to provide to trakt
    username: The username to use when logging in
    password: The unencrypted password to use when logging in

    Returns: A boolean representing success
    """
    #logger.log("trakt: Call method " + method, logger.DEBUG)

    # if the API isn't given then it failed
    if not api:
        return None

    # replace the API string with what we found
    connection = host + "/api/" + api
    #url = method.replace("%CONNECTOR%", connection)
    logger.log(command)
    url = connection + "/?cmd=" + command
    logger.log(url)
    # request the URL from trakt and parse the result as json
    try:
        logger.log("sickbeard: Calling method " + url, logger.DEBUG)
        stream = urllib2.urlopen( url)
        resp = stream.read()

        resp = json.loads(resp)

        if ("error" in resp):
            raise Exception(resp["error"])

    except (IOError):
        #logger.log("trakt: Failed calling method", logger.ERROR)
        return None

    #logger.log("trakt: Failed calling method", logger.ERROR)
    return resp