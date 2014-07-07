import os
import traceback
import sickbeard
import webserve

from sickbeard import logger
from tornado.web import Application, StaticFileHandler, RedirectHandler, HTTPError
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop

server = None


class MultiStaticFileHandler(StaticFileHandler):
    def initialize(self, paths, default_filename=None):
        self.paths = paths
        self.default_filename = default_filename

    def get(self, path, include_body=True):
        for p in self.paths:
            try:
                # Initialize the Static file with a path
                super(MultiStaticFileHandler, self).initialize(p)
                # Try to get the file
                return super(MultiStaticFileHandler, self).get(path)
            except HTTPError as exc:
                # File not found, carry on
                if exc.status_code == 404:
                    continue
                raise

        # Oops file not found anywhere!
        raise HTTPError(404)


def initWebServer(options={}):
    options.setdefault('port', 8081)
    options.setdefault('host', '0.0.0.0')
    options.setdefault('log_dir', None)
    options.setdefault('username', '')
    options.setdefault('password', '')
    options.setdefault('web_root', '/')
    assert isinstance(options['port'], int)
    assert 'data_root' in options

    # tornado setup

    # Load the app
    app = Application([],
                        debug=False,
                        gzip=True,
                        xheaders=sickbeard.HANDLE_REVERSE_PROXY,
                        cookie_secret='61oETzKXQAGaYdkL5gEmGeJJFuYh7EQnp2XdTP1o/Vo='
    )

    # Main Handler
    app.add_handlers(".*$", [
        (r"%s" % options['web_root'], RedirectHandler, {'url': '%s/home/' % options['web_root']}),
        (r'%s/(.*)(/?)' % options['web_root'], webserve.MainHandler)
    ])

    # Static Path Handler
    app.add_handlers(".*$", [
        (r'%s/(favicon\.ico)' % options['web_root'], MultiStaticFileHandler,
         {'paths': [os.path.join(options['data_root'], 'images/ico/favicon.ico')]}),
        (r'%s/%s/(.*)(/?)' % (options['web_root'], 'images'), MultiStaticFileHandler,
         {'paths': [os.path.join(options['data_root'], 'images')]}),
        (r'%s/%s/(.*)(/?)' % (options['web_root'], 'css'), MultiStaticFileHandler,
         {'paths': [os.path.join(options['data_root'], 'css')]}),
        (r'%s/%s/(.*)(/?)' % (options['web_root'], 'js'), MultiStaticFileHandler,
         {'paths': [os.path.join(options['data_root'], 'js')]})

    ])

    global server

    protocol = "http"
    server = HTTPServer(app, no_keep_alive=True)

    logger.log(u"Starting SickRage on " + protocol + "://" + str(options['host']) + ":" + str(
        options['port']) + "/")

    server.listen(options['port'], options['host'])

def shutdown():

    logger.log('Shutting down tornado IO loop')
    try:
        IOLoop.current().stop()
    except RuntimeError:
        pass
    except:
        logger.log('Failed shutting down tornado IO loop: %s' % traceback.format_exc(), logger.ERROR)