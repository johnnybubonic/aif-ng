import os
##
from lxml import etree

class Config(object):
    def __init__(self):
        self.xml = None

    def parseLocalFile(self, fpath):
        fpath = os.path.abspath(os.path.expanduser(fpath))
        pass

    def parseRemoteFile(self, url):
        pass

    def parseRawContent(self, content):
        pass
