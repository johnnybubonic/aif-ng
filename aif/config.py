import os
import re
##
import requests
from lxml import etree

_patterns = {'raw': re.compile(r'^\s*(?P<xml><(\?xml|aif)\s+.*)\s*$', re.DOTALL|re.MULTILINE),
             'remote': re.compile(r'^(?P<uri>(?P<proto>(https?|ftps?)://)(?P<path>.*))\s*$'),
             'local': re.compile(r'^(file://)?(?P<path>(/?[^/]+)+/?)$')}


class Config(object):
    def __init__(self, xsd_path = None, *args, **kwargs):
        self.xsd_path = None
        self.tree = None
        self.namespaced_tree = None
        self.xml = None
        self.namespaced_xml = None
        self.raw = None
        self.xsd = None
        self.defaultsParser = None

    def main(self, validate = True, populate_defaults = True):
        self.fetch()
        self.parseRaw()
        if populate_defaults:
            self.populateDefaults()
        if validate:
            self.validate()
        return()

    def fetch(self):  # Just a fail-safe; this is overridden by specific subclasses.
        pass
        return()

    def getXSD(self, xsdpath = None):
        if not xsdpath:
            xsdpath = self.xsd_path
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
            split_url = schemaURL.split()
            if len(split_url) == 2:  # a properly defined schemaLocation
                schemaURL = split_url[1]
            else:
                schemaURL = split_url[0]
            req = requests.get(schemaURL)
            if not req.ok:
                # TODO: logging!
                raise RuntimeError('Could not download XSD')
            raw_xsd = req.content
        self.xsd = etree.XMLSchema(etree.XML(raw_xsd))
        return()

    def parseRaw(self, parser = None):
        # self.xml = etree.parse(self.raw, parser = parser)
        self.xml = etree.fromstring(self.raw, parser = parser)
        # self.namespaced_xml = etree.parse(self.raw, parser = parser)
        self.namespaced_xml = etree.fromstring(self.raw, parser = parser)
        self.tree = self.xml.getroottree()
        self.namespaced_tree = self.namespaced_xml.getroottree()
        self.tree.xinclude()
        self.namespaced_tree.xinclude()
        self.stripNS()
        return()

    def populateDefaults(self):
        if not self.xsd:
            self.getXSD()
        if not self.defaultsParser:
            self.defaultsParser = etree.XMLParser(schema = self.xsd, attribute_defaults = True)
        self.parseRaw(parser = self.defaultsParser)
        return()

    def removeDefaults(self):
        self.parseRaw()
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
        self.xsd.assertValid(self.tree)
        self.xsd.assertValid(self.namespaced_tree)
        return()


class LocalFile(Config):
    def __init__(self, path, xsd_path = None, *args, **kwargs):
        super().__init__(xsd_path = xsd_path, *args, **kwargs)
        self.type = 'local'
        self.source = _patterns['local'].search(path).group('path')

    def fetch(self):
        self.source = os.path.realpath(self.source)
        if not os.path.isfile(self.source):
            raise ValueError('{0} does not exist'.format(self.source))
        with open(self.source, 'rb') as fh:
            self.raw = fh.read()
        return()


class RemoteFile(Config):
    def __init__(self, uri, xsd_path = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type = 'remote'
        self.source = uri

    def fetch(self):
        r = requests.get(self.source)
        if not r.ok():
            raise RuntimeError('Could not download XML')
        self.raw = r.content
        return()


class ConfigStr(Config):
    def __init__(self, rawxml, xsd_path = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type = 'raw_str'
        self.source = rawxml

    def fetch(self):
        self.raw = self.source.encode('utf-8')
        return()


class ConfigBin(Config):
    def __init__(self, rawbinaryxml, xsd_path = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type = 'raw_bin'
        self.source = rawbinaryxml

    def fetch(self):
        self.raw = self.source
        return()


def getConfig(cfg_ref, validate = True, populate_defaults = True, xsd_path = None):
    cfgobj = None
    # This is kind of gross.
    for configtype, pattern in _patterns.items():
        try:
            if pattern.search(cfg_ref):
                if configtype == 'raw':
                    cfgobj = ConfigStr(cfg_ref, xsd_path = xsd_path)
                elif configtype == 'remote':
                    cfgobj = RemoteFile(cfg_ref, xsd_path = xsd_path)
                elif configtype == 'local':
                    cfgobj = LocalFile(cfg_ref, xsd_path = xsd_path)
                if cfgobj:
                    break
        except TypeError:
            ptrn = re.compile(_patterns['raw'].pattern.encode('utf-8'))
            if not ptrn.search(cfg_ref):
                raise ValueError('Received junk data for cfg_ref')
            else:
                cfgobj = ConfigBin(cfg_ref, xsd_path = xsd_path)
                break
    if cfgobj:
        cfgobj.main(validate = validate, populate_defaults = populate_defaults)
    return(cfgobj)
