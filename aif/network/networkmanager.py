import ipaddress
##
from . import _common

_NM = _common.NM


class Connection(object):
    def __init__(self, iface_xml):
        self.xml = iface_xml
        self.connection_type = None
        self.provider_type = 'NetworkManager'
        self.client = _NM.Client.new()
        self.addrs = {'ipv4': [],
                      'ipv6': []}
        self.resolvers = []
        self._initAddrs()
        self._initResolvers()

    def _initAddrs(self):
        for t in ('ipv4', 'ipv6'):
            for a in self.xml.findall('addresses/{0}/address'.format(t)):
                if a.text in ('dhcp', 'dhcp6', 'slaac'):
                    addr = net = None
                else:
                    components = a.text.split('/')
                    if len(components) > 2:
                        raise ValueError('Invalid IP/CIDR format: {0}'.format(a.text))
                    if len(components) == 1:
                        addr = components[0]
                        if t == 'ipv4':
                            components.append('24')
                        elif t == 'ipv6':
                            components.append('64')
                    addr = ipaddress.ip_address(components[0])
                    net = ipaddress.ip_network('/'.join(components), strict = False)
                self.addrs[t].append((addr, net))
        return()

    def _initResolvers(self):
        for r in self.xml.findall('resolvers/resolver'):
            self.resolvers.append(ipaddress.ip_address(r.text))
        return()


class Ethernet(Connection):
    def __init__(self, iface_xml):
        super().__init__(iface_xml)
        self.connection_type = 'ethernet'


class Wireless(Connection):
    def __init__(self, iface_xml):
        super().__init__(iface_xml)
        self.connection_type = 'wireless'
