import os
##
from lxml import etree

# https://stackoverflow.com/questions/30232031/how-can-i-strip-namespaces-out-of-an-lxml-tree/30233635#30233635 ?

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
