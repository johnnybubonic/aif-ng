import copy
import logging
import os
import re
##
import requests
from lxml import etree, objectify

_logger = logging.getLogger('config:{0}'.format(__name__))


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
        self.obj = None
        _logger.info('Instantiated {0}.'.format(type(self).__name__))

    def main(self, validate = True, populate_defaults = True):
        self.fetch()
        self.parseRaw()
        if populate_defaults:
            self.populateDefaults()
        if validate:
            self.validate()
        self.pythonize()
        return(None)

    def fetch(self):  # Just a fail-safe; this is overridden by specific subclasses.
        pass
        return(None)

    def getXSD(self, xsdpath = None):
        if not xsdpath:
            xsdpath = self.xsd_path
        raw_xsd = None
        base_url = None
        if xsdpath:
            _logger.debug('XSD path specified.')
            orig_xsdpath = xsdpath
            xsdpath = os.path.abspath(os.path.expanduser(xsdpath))
            _logger.debug('Transformed XSD path: {0} => {1}'.format(orig_xsdpath, xsdpath))
            if not os.path.isfile(xsdpath):
                _logger.error('The specified XSD path {0} does not exist on the local filesystem.'.format(xsdpath))
                raise ValueError('Specified XSD path does not exist')
            with open(xsdpath, 'rb') as fh:
                raw_xsd = fh.read()
            base_url = os.path.split(xsdpath)[0]
        else:
            _logger.debug('No XSD path specified; getting it from the configuration file.')
            xsi = self.xml.nsmap.get('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
            _logger.debug('xsi: {0}'.format(xsi))
            schemaLocation = '{{{0}}}schemaLocation'.format(xsi)
            schemaURL = self.xml.attrib.get(schemaLocation,
                                            'https://schema.xml.r00t2.io/projects/aif.xsd')
            _logger.debug('Detected schema map: {0}'.format(schemaURL))
            split_url = schemaURL.split()
            if len(split_url) == 2:  # a properly defined schemaLocation
                schemaURL = split_url[1]
            else:
                schemaURL = split_url[0]  # a LAZY schemaLocation
            _logger.info('Detected schema location: {0}'.format(schemaURL))
            if schemaURL.startswith('file://'):
                schemaURL = re.sub(r'^file://', r'', schemaURL)
                _logger.debug('Fetching local file {0}'.format(schemaURL))
                with open(schemaURL, 'rb') as fh:
                    raw_xsd = fh.read()
                base_url = os.path.dirname(schemaURL)
            else:
                _logger.debug('Fetching remote file: {0}'.format(schemaURL))
                req = requests.get(schemaURL)
                if not req.ok:
                    _logger.error('Unable to fetch XSD.')
                    raise RuntimeError('Could not download XSD')
                raw_xsd = req.content
                base_url = os.path.split(req.url)[0]  # This makes me feel dirty.
        _logger.debug('Loaded XSD at {0} ({1} bytes).'.format(xsdpath, len(raw_xsd)))
        _logger.debug('Parsed XML base URL: {0}'.format(base_url))
        self.xsd = etree.XMLSchema(etree.XML(raw_xsd, base_url = base_url))
        _logger.info('Rendered XSD.')
        return(None)

    def parseRaw(self, parser = None):
        self.xml = etree.fromstring(self.raw, parser = parser)
        _logger.debug('Generated xml.')
        self.namespaced_xml = etree.fromstring(self.raw, parser = parser)
        _logger.debug('Generated namespaced xml.')
        self.tree = self.xml.getroottree()
        _logger.debug('Generated tree.')
        self.namespaced_tree = self.namespaced_xml.getroottree()
        _logger.debug('Generated namespaced tree.')
        self.tree.xinclude()
        _logger.debug('Parsed XInclude for tree.')
        self.namespaced_tree.xinclude()
        _logger.debug('Parsed XInclude for namespaced tree.')
        self.stripNS()
        return(None)

    def populateDefaults(self):
        _logger.info('Populating missing values with defaults from XSD.')
        if not self.xsd:
            self.getXSD()
        if not self.defaultsParser:
            self.defaultsParser = etree.XMLParser(schema = self.xsd, attribute_defaults = True)
        self.parseRaw(parser = self.defaultsParser)
        return(None)

    def pythonize(self, stripped = True, obj = 'tree'):
        # https://bugs.launchpad.net/lxml/+bug/1850221
        _logger.debug('Pythonizing to native objects')
        strobj = self.toString(stripped = stripped, obj = obj)
        self.obj = objectify.fromstring(strobj)
        objectify.annotate(self.obj)
        objectify.xsiannotate(self.obj)
        return(None)

    def removeDefaults(self):
        _logger.info('Removing default values from missing values.')
        self.parseRaw()
        return(None)

    def stripNS(self, obj = None):
        _logger.debug('Stripping namespace.')
        # https://stackoverflow.com/questions/30232031/how-can-i-strip-namespaces-out-of-an-lxml-tree/30233635#30233635
        xpathq = "descendant-or-self::*[namespace-uri()!='']"
        if not obj:
            _logger.debug('No XML object selected; using instance\'s xml and tree.')
            for x in (self.tree, self.xml):
                for e in x.xpath(xpathq):
                    e.tag = etree.QName(e).localname
        elif isinstance(obj, (etree._Element, etree._ElementTree)):
            _logger.debug('XML object provided: {0}'.format(etree.tostring(obj, with_tail = False).decode('utf-8')))
            obj = copy.deepcopy(obj)
            for e in obj.xpath(xpathq):
                e.tag = etree.QName(e).localname
            return(obj)
        else:
            _logger.error('A non-XML object was provided.')
            raise ValueError('Did not know how to parse obj parameter')
        return(None)

    def toString(self, stripped = False, obj = None):
        if isinstance(obj, (etree._Element, etree._ElementTree)):
            _logger.debug('Converting an XML object to a string')
            if stripped:
                _logger.debug('Stripping before stringifying.')
                obj = self.stripNS(obj)
        elif obj in ('tree', None):
            if not stripped:
                _logger.debug('Converting the instance\'s namespaced tree to a string.')
                obj = self.namespaced_tree
            else:
                _logger.debug('Converting the instance\'s stripped tree to a string.')
                obj = self.tree
        elif obj == 'xml':
            if not stripped:
                _logger.debug('Converting instance\'s namespaced XML to a string')
                obj = self.namespaced_xml
            else:
                _logger.debug('Converting instance\'s stripped XML to a string')
                obj = self.xml
        else:
            raise ValueError(('obj parameter must be "tree", "xml", or of type '
                              'lxml.etree._Element or lxml.etree._ElementTree'))
        obj = copy.deepcopy(obj)
        strxml = etree.tostring(obj,
                                encoding = 'utf-8',
                                xml_declaration = True,
                                pretty_print = True,
                                with_tail = True,
                                inclusive_ns_prefixes = True)
        _logger.debug('Rendered string output successfully.')
        return(strxml)

    def validate(self):
        if not self.xsd:
            self.getXSD()
        _logger.debug('Checking validation against namespaced tree.')
        self.xsd.assertValid(self.namespaced_tree)
        return(None)


class LocalFile(Config):
    def __init__(self, path, xsd_path = None, *args, **kwargs):
        super().__init__(xsd_path = xsd_path, *args, **kwargs)
        self.type = 'local'
        self.source = path

    def fetch(self):
        orig_src = self.source
        self.source = os.path.abspath(os.path.expanduser(self.source))
        _logger.debug('Canonized path: {0} => {1}'.format(orig_src, self.source))
        if not os.path.isfile(self.source):
            _logger.error('Config at {0} not found.'.format(self.source))
            raise ValueError('Config file does not exist'.format(self.source))
        with open(self.source, 'rb') as fh:
            self.raw = fh.read()
        _logger.debug('Fetched configuration ({0} bytes).'.format(len(self.raw)))
        return(None)


class RemoteFile(Config):
    def __init__(self, uri, xsd_path = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type = 'remote'
        self.source = uri

    def fetch(self):
        r = requests.get(self.source)
        if not r.ok():
            _logger.error('Could not fetch {0}'.format(self.source))
            raise RuntimeError('Could not download XML')
        self.raw = r.content
        _logger.debug('Fetched configuration ({0} bytes).'.format(len(self.raw)))
        return(None)


class ConfigStr(Config):
    def __init__(self, rawxml, xsd_path = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type = 'raw_str'
        self.source = rawxml

    def fetch(self):
        self.raw = self.source.encode('utf-8')
        _logger.debug('Raw configuration (str) passed in ({0} bytes); converted to bytes.'.format(len(self.raw)))
        return(None)


class ConfigBin(Config):
    def __init__(self, rawbinaryxml, xsd_path = None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.type = 'raw_bin'
        self.source = rawbinaryxml

    def fetch(self):
        self.raw = self.source
        _logger.debug('Raw configuration (binary) passed in ({0} bytes); converted to bytes.'.format(len(self.raw)))
        return(None)


detector = {'raw': (re.compile(r'^\s*(?P<xml><(\?xml|aif)\s+.*)\s*$', re.DOTALL | re.MULTILINE), ConfigStr),
            'remote': (re.compile(r'^(?P<uri>(?P<scheme>(https?|ftps?)://)(?P<path>.*))\s*$'), RemoteFile),
            'local': (re.compile(r'^(file://)?(?P<path>(/?[^/]+)+/?)$'), LocalFile)}


def getConfig(cfg_ref, validate = True, populate_defaults = True, xsd_path = None):
    cfgobj = None
    # This is kind of gross.
    for configtype, (pattern, configClass) in detector.items():
        try:
            if pattern.search(cfg_ref):
                cfgobj = configClass(cfg_ref, xsd_path = xsd_path)
                _logger.info('Config detected as {0}.'.format(configtype))
                break
        except TypeError:
            ptrn = re.compile(detector['raw'][0].pattern.encode('utf-8'))
            if not ptrn.search(cfg_ref):
                _logger.error('Could not detect which configuration type was passed.')
                raise ValueError('Unespected/unparseable cfg_ref.')
            else:
                _logger.info('Config detected as ConfigBin.')
                cfgobj = ConfigBin(cfg_ref, xsd_path = xsd_path)
                break
    if cfgobj:
        _logger.info('Parsing configuration.')
        cfgobj.main(validate = validate, populate_defaults = populate_defaults)
    return(cfgobj)
