import logging
import re


_logger = logging.getLogger('utils:{0}'.format(__name__))


_uri_re = re.compile((r'^(?P<scheme>[\w]+)://'
                      r'(?:(?P<user>[^:@]+)(?::(?P<password>[^@]+)?)?@)?'
                      r'(?P<base>[^/:]+)?'
                      r'(?::(?P<port>[0-9]+))?'
                      r'(?P<path>/.*)$'),
                     re.IGNORECASE)


class URI(object):
    def __init__(self, uri):
        self.orig_uri = uri
        r = _uri_re.search(self.orig_uri)
        if not r:
            raise ValueError('Not a valid URI')
        for k, v in dict(zip(list(_uri_re.groupindex.keys()), r.groups())).items():
            setattr(self, k, v)
        if self.port:
            self.port = int(self.port)
        for a in ('base', 'scheme'):
            v = getattr(self, a)
            if v:
                setattr(self, a, v.lower())
