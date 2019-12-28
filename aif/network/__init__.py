import logging
import os
##
from lxml import etree
##
from . import _common
from . import netctl
from . import networkd
from . import networkmanager

# No longer necessary:
# try:
#     from . import _common
# except ImportError:
#     pass  # GI isn't supported, so we don't even use a fallback.

# http://0pointer.net/blog/the-new-sd-bus-api-of-systemd.html
# https://www.youtube.com/watch?v=ZUX9Fx8Rwzg
# https://www.youtube.com/watch?v=lBQgMGPxqNo
# https://github.com/facebookincubator/pystemd has some unit/service examples
# try:
#     from . import networkd
# except ImportError:
#     from . import networkd_fallback as networkd


_logger = logging.getLogger(__name__)


class Net(object):
    def __init__(self, chroot_base, network_xml):
        self.xml = network_xml
        # We don't bother logging the entirety of network_xml here because we do it in the respective networks
        self.chroot_base = chroot_base
        self.hostname = self.xml.attrib['hostname'].strip()
        _logger.info('Hostname: {0}'.format(self.hostname))
        self.provider = self.xml.attrib.get('provider', 'networkd').strip()
        if self.provider == 'netctl':
            self.provider = netctl
        elif self.provider == 'nm':
            self.provider = networkmanager
        elif self.provider == 'networkd':
            self.provider = networkd
        else:
            raise RuntimeError('Could not determine provider')
        self.connections = []
        self._initConns()

    def _initConns(self):
        for e in self.xml.xpath('ethernet|wireless'):
            conn = None
            if e.tag == 'ethernet':
                conn = self.provider.Ethernet(e)
            elif e.tag == 'wireless':
                conn = self.provider.Wireless(e)
            self.connections.append(conn)
            _logger.info('Added connection of type {0}.'.format(type(conn).__name__))

    def apply(self, chroot_base):
        cfg = os.path.join(chroot_base, 'etc', 'hostname')
        with open(cfg, 'w') as fh:
            fh.write('{0}\n'.format(self.hostname))
        os.chown(cfg, 0, 0)
        os.chmod(cfg, 0o0644)
        for iface in self.connections:
            for src, dest in iface.services.items():
                realdest = os.path.join(chroot_base, dest)
                os.symlink(src, realdest)
            iface.writeConf(chroot_base)
        return(None)
