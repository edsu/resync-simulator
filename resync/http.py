#!/usr/bin/env python
# encoding: utf-8
"""
http.py: The source's HTTP Web interface running on the
non-blocking Tornado web server (http://www.tornadoweb.org/)

Created by Bernhard Haslhofer on 2012-04-24.
Copyright 2012, ResourceSync.org. All rights reserved.
"""

import threading
import os.path

import tornado.httpserver
import tornado.ioloop
import tornado.web


class HTTPInterface(threading.Thread):
    """The repository's HTTP interface. To make sure it doesn't interrupt
    the simulation, it runs in a separate thread.
    
    http://stackoverflow.com/questions/323972/
        is-there-any-way-to-kill-a-thread-in-python (Stoppable Threads)
        
    http://www.slideshare.net/juokaz/
        restful-web-services-with-python-dynamic-languages-conference
    
    """
    
    def __init__(self, source):
        """Initializes HTTP interface with default settings and handlers"""
        super(HTTPInterface, self).__init__()
        self._stop = threading.Event()
        self.source = source
        self.port = source.port
        self.settings = dict(
            title=u"ResourceSync Change Simulator",
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            autoescape=None,        
        )
        self.handlers = [
            (r"/", HomeHandler, dict(source = self.source)),
            (r"/resources/?", ResourceListHandler,
                                dict(source = self.source)),
            (r"/resources/([0-9]+)", ResourceHandler,
                                dict(source = self.source)),
            (r"/(favicon\.ico)", tornado.web.StaticFileHandler,
                                dict(path = self.settings['static_path'])),
            (r"/sitemap.xml", InventoryHandler, 
                                dict(source = self.source)),
        ]
        
        if self.source.has_changememory:
            self.handlers = self.handlers + \
                [(r"%s" % self.source.changememory.url, 
                    DynamicChangeSetHandler,
                    dict(changememory = self.source.changememory)),
                    (r"%s/([0-9]+)/diff" % self.source.changememory.url,
                    DynamicChangeSetDiffHandler,
                    dict(changememory = self.source.changememory))]
            
    
    def run(self):
        print "*** Starting up HTTP Interface on port %i ***\n" % (self.port)
        application = tornado.web.Application(
                        handlers = self.handlers, 
                        debug = True,
                        **self.settings)
        self.http_server = tornado.httpserver.HTTPServer(application)
        self.http_server.listen(self.port)
        tornado.ioloop.IOLoop.instance().start()
        
    def stop(self):
        print "*** Stopping HTTP Interface ***\n"
        tornado.ioloop.IOLoop.instance().stop()
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()
    

class BaseRequestHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ("GET")
    
    def initialize(self, source):
        self.source = source
    

class HomeHandler(BaseRequestHandler):
    """Root URI handler"""
    def get(self):
        self.render("home.html",
                    resource_count = self.source.resource_count,
                    source = self.source)

# Resource Handlers

class ResourceListHandler(BaseRequestHandler):
    """Resource list selection handler"""
    def get(self):
        rand_res = sorted(self.source.random_resources(100), 
            key = lambda res: int(res.basename))
        self.render("resource.index.html", resources = rand_res)
                        

class ResourceHandler(BaseRequestHandler):
    """Resource handler"""
    def get(self, basename):
        resource = self.source.resource(basename)
        if resource == None:
            self.send_error(404)
        else:
            self.set_header("Content-Type", "text/plain")
            self.set_header("Content-Length", resource.size)
            self.set_header("Last-Modified", resource.lastmod)
            self.set_header("Etag", "\"%s\"" % resource.md5)
            payload = self.source.resource_payload(basename)
            self.write(payload)

# Inventory Handlers
            
class InventoryHandler(tornado.web.RequestHandler):
    """The HTTP request handler for the Inventory"""

    def initialize(self, source):
        self.source = source
    
    @property
    def next_changeset_uri(self):
        """The URI of the next changeset"""
        if not self.source.has_changememory:
            return None
        else:
            return "http://" + self.request.host + \
                    self.source.changememory.url + "/" + \
                    self.source.changememory.latest_event_id + "/diff"
    
    def get(self):
        self.set_header("Content-Type", "application/xml")
        self.render("sitemap.xml",
                    next_changeset_uri = self.next_changeset_uri,
                    resources = self.source.inventory.resources.values())

# Changememory Handlers

class DynamicChangeSetHandler(tornado.web.RequestHandler):
    """The HTTP request handler for the DynamicDigest"""

    def initialize(self, changememory):
        self.changememory = changememory
    
    @property
    def this_changeset_uri(self):
        """Constructs the URI of this (self) changeset"""
        return "http://" + self.request.host + self.changememory.url + "/" + \
                self.changememory.first_event_id + "/diff"
    
    @property
    def next_changeset_uri(self):
        """Constructs the URI of the next changeset"""
        return "http://" + self.request.host + self.changememory.url + "/" + \
                self.changememory.latest_event_id + "/diff"
    
    def get(self):
        self.set_header("Content-Type", "application/xml")
        self.render("changedigest.xml",
                    this_changeset_uri = self.this_changeset_uri,
                    next_changeset_uri = self.next_changeset_uri,
                    changes = self.changememory.changes)
                    

class DynamicChangeSetDiffHandler(DynamicChangeSetHandler):
    """The HTTP request handler for the DynamicDigest"""

    @property
    def this_changeset_uri(self):
        """Constructs the URI of this (self) changeset"""
        return "http://" + self.request.host + self.changememory.url + "/" + \
                self.event_id + "/diff"
    
    def get(self, event_id):
        self.event_id = event_id
        self.set_header("Content-Type", "application/xml")
        self.render("changedigest.xml",
                    this_changeset_uri = self.this_changeset_uri,
                    next_changeset_uri = self.next_changeset_uri,
                    changes = self.changememory.changes_from(event_id))
