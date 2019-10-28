import os
import re
##
import requests
from lxml import etree

# https://stackoverflow.com/questions/30232031/how-can-i-strip-namespaces-out-of-an-lxml-tree/30233635#30233635 ?

_patterns = {'raw': re.compile(r'^\s*(?P<xml><(\?xml|aif)\s+.*)\s*$', re.DOTALL|re.MULTILINE),
             'remote': re.compile(r'^(?P<uri>(?P<proto>(https?|ftps?)://)(?P<path>.*))\s*$'),
             'local': re.compile(r'^(file://)?(?P<path>(/?[^/]+)+/?)$')}

class Config(object):
    def __init__(self, *args, **kwargs):
        self.tree = None
        self.namespaced_tree = None
        self.xml = None
        self.namespaced_xml = None
        self.raw = None
        self.xsd = None

    def main(self, validate = True):
        self.fetch()
        self.parseRaw()
        if validate:
            self.validate()

        return()

    def fetch(self):  # Just a fail-safe; this is overridden by specific subclasses.
        pass
        return()

    def getXSD(self, xsdpath = None):
        raw_xsd = None
        if xsdpath:
            xsdpath = os.path.abspath(os.path.expanduser(xsdpath))
            if not os.path.isfile(xsdpath):
                raise ValueError(('An explicit XSD path was specified but '
                                  'does not exist on the local filesystem'))
            with open(xsdpath, 'rb') as fh:
                raw_xsd = fh.read()
        else:
            xsi = self.xml.nsmap.get('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
            schemaLocation = '{{{0}}}schemaLocation'.format(xsi)
            schemaURL = self.xml.attrib.get(schemaLocation,
                                            'https://aif-ng.io/aif.xsd?ref={0}'.format(self.xml.attrib['version']))
            req = requests.get(schemaURL)
            if not req.ok():
                raise RuntimeError('Could not download XSD')
            raw_xsd = req.content
        self.xsd = etree.XMLSchema(etree.XML(raw_xsd))
        return()

    def parseRaw(self):
        self.tree = etree.parse(self.raw)
        self.namespaced_tree = etree.parse(self.raw)
        self.xml = self.tree.getroot()
        self.namespaced_xml = self.namespaced_tree.getroot()
        self.tree.xinclude()
        self.namespaced_tree.xinclude()
        return()

    def stripNS(self):
        # https://stackoverflow.com/questions/30232031/how-can-i-strip-namespaces-out-of-an-lxml-tree/30233635#30233635
        for x in (self.tree, self.xml):
            for e in x.xpath("descendant-or-self::*[namespace-uri()!='']"):
                e.tag = etree.QName(e).localname
        return()

    def validate(self):
        if not self.xsd:
            self.getXSD()

        return()


class LocalFile(Config):
    def __init__(self, path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = ['local', _patterns['local'].search(path).group('path')]

    def fetch(self):
        self.source[1] = os.path.abspath(os.path.expanduser(self.source[1]))
        if not os.path.isfile(self.source[1]):
            raise ValueError('{0} does not exist'.format(self.source[1]))
        with open(self.source[1], 'rb') as fh:
            self.raw = fh.read()
        return()


class RemoteFile(Config):
    def __init__(self, uri, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = ('remote', uri)

    def fetch(self):
        r = requests.get(self.source[1])
        if not r.ok():
            raise RuntimeError('Could not download XML')
        self.raw = r.content
        return()


class ConfigStr(Config):
    def __init__(self, rawxml, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = ('raw', rawxml)

    def fetch(self):
        self.raw = self.source[1].encode('utf-8')
        return()

class ConfigBin(Config):
    def __init__(self, rawbinaryxml, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.source = ('raw_binary', rawbinaryxml)

    def fetch(self):
        self.raw = self.source[1]
        return()


def getConfig(cfg_ref, validate = True):
    cfgobj = None
    # This is kind of gross.
    for configtype, pattern in _patterns.items():
        try:
            if pattern.search(cfg_ref):
                if configtype == 'raw':
                    cfgobj = ConfigStr(cfg_ref)
                elif configtype == 'remote':
                    cfgobj = RemoteFile(cfg_ref)
                elif configtype == 'local':
                    cfgobj = LocalFile(cfg_ref)
                if cfgobj:
                    break
        except TypeError:
            ptrn = re.compile(_patterns['raw'].pattern.encode('utf-8'))
            if not ptrn.search(cfg_ref):
                raise ValueError('Received junk data for cfg_ref')
            else:
                cfgobj = ConfigBin(cfg_ref)
                break
    return(cfgobj)
