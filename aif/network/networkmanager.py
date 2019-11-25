import configparser
import datetime
import ipaddress
import os
import uuid
##
import aif.utils

# TODO: auto dev assignment


class Connection(object):
    def __init__(self, iface_xml):
        self.xml = iface_xml
        self.id = self.xml.attrib['id']
        self.device = self.xml.attrib['device']
        self.is_defroute = aif.utils.xmlBool(self.xml.attrib.get('defroute', 'false'))
        self.domain = self.xml.attrib.get('searchDomain', None)
        self._cfg = None
        self.connection_type = None
        self.provider_type = 'NetworkManager'
        self.addrs = {'ipv4': set(),
                      'ipv6': set()}
        self.resolvers = []
        self.uuid = uuid.uuid4()
        self._initAddrs()
        self._initResolvers()

    def _initAddrs(self):
        # These tuples follow either:
        #   ('dhcp'/'dhcp6'/'slaac', None, None) for auto configuration
        #   (ipaddress.IPv4/6Address(IP), CIDR, ipaddress.IPv4/6Address(GW)) for static configuration
        for addrtype in ('ipv4', 'ipv6'):
            for a in self.xml.findall('addresses/{0}/address'.format(addrtype)):
                if a.text in ('dhcp', 'dhcp6', 'slaac'):
                    addr = a.text
                    net = None
                    gw = None
                else:
                    components = a.text.split('/')
                    if len(components) > 2:
                        raise ValueError('Invalid IP/CIDR format: {0}'.format(a.text))
                    if len(components) == 1:
                        addr = components[0]
                        if addrtype == 'ipv4':
                            components.append('24')
                        elif addrtype == 'ipv6':
                            components.append('64')
                    addr = ipaddress.ip_address(components[0])
                    net = ipaddress.ip_network('/'.join(components), strict = False)
                    gw = ipaddress.ip_address(a.attrib.get('gateway'))
                self.addrs[addrtype].add((addr, net, gw))
            self.addrs[addrtype] = list(self.addrs[addrtype])
        return()

    def _initCfg(self):
        self._cfg = configparser.ConfigParser()
        self._cfg.optionxform = str
        self._cfg['connection'] = {'id': self.id,
                                   'uuid': self.uuid,
                                   'type': self.connection_type,
                                   'interface-name': self.device,
                                   'permissions': '',
                                   'timestamp': datetime.datetime.utcnow().timestamp()}
        # We *theoretically* could do this in _initAddrs() but we do it separately so we can trim out duplicates.
        for addrtype, addrs in self.addrs.items():
            self._cfg[addrtype] = {}
            cidr_gws = {}
            self._cfg[addrtype]['dns-search'] = (self.domain if self.domain else '')
            if addrtype == 'ipv6':
                self._cfg[addrtype]['addr-gen-mode'] = 'stable-privacy'
            if not addrs:
                self._cfg[addrtype]['method'] = 'ignore'
            else:
                self._cfg[addrtype]['method'] = 'manual'
                for idx, (ip, cidr, gw) in enumerate(addrs):
                    if cidr not in cidr_gws.keys():
                        cidr_gws[cidr] = gw
                        new_cidr = True
                    else:
                        new_cidr = False
                    if addrtype == 'ipv4':
                        if ip == 'dhcp':
                            self._cfg[addrtype]['method'] = 'auto'
                            continue
                    elif addrtype == 'ipv6':
                        if ip == 'dhcp6':
                            self._cfg[addrtype]['method'] = 'dhcp'
                            continue
                        elif ip == 'slaac':
                            self._cfg[addrtype]['method'] = 'auto'
                            continue
                    addrnum = idx + 1
                    addr_str = '{0}/{1}'.format(str(ip), str(cidr.prefixlen))
                    if new_cidr:
                        addr_str = '{0},{1}'.format(addr_str, str(gw))
                    self._cfg[addrtype]['address{0}'.format(addrnum)] = addr_str
            for r in self.resolvers:
                if addrtype == 'ipv{0}'.format(r.version):
                    if 'dns' not in self._cfg[addrtype]:
                        self._cfg[addrtype]['dns'] = []
                    self._cfg[addrtype]['dns'].append(str(r))
            if 'dns' in self._cfg[addrtype].keys():
                self._cfg[addrtype]['dns'] = '{0};'.format(';'.join(self._cfg[addrtype]['dns']))
        self._initConnCfg()
        return()

    def _initConnCfg(self):
        # A dummy method; this is overridden by the subclasses.
        # It's honestly here to make my IDE stop complaining. :)
        pass
        return()

    def _initResolvers(self):
        for r in self.xml.findall('resolvers/resolver'):
            resolver = ipaddress.ip_address(r.text)
            if resolver not in self.resolvers:
                self.resolvers.append(resolver)
        return()

    def writeConf(self, chroot_base):
        cfgroot = os.path.join(chroot_base, 'etc', 'NetworkManager')
        cfgdir = os.path.join(cfgroot, 'system-connections')
        cfgpath = os.path.join(cfgdir, '{0}.nmconnection'.format(self.id))
        os.makedirs(cfgdir, exist_ok = True)
        with open(cfgpath, 'w') as fh:
            self._cfg.write(fh, space_around_delimiters = False)
        for root, dirs, files in os.walk(cfgroot):
            os.chown(root, 0, 0)
            for d in dirs:
                dpath = os.path.join(root, d)
                os.chown(dpath, 0, 0)
            for f in files:
                fpath = os.path.join(root, f)
                os.chown(fpath, 0, 0)
        os.chmod(cfgroot, 0o0755)
        os.chmod(cfgdir, 0o0700)
        os.chmod(cfgpath, 0o0600)
        return()


class Ethernet(Connection):
    def __init__(self, iface_xml):
        super().__init__(iface_xml)
        self.connection_type = 'ethernet'
        self._initCfg()

    def _initConnCfg(self):
        pass


class Wireless(Connection):
    def __init__(self, iface_xml):
        super().__init__(iface_xml)
        self.connection_type = 'wireless'
        self._initCfg()

    def _initConnCfg(self):
        pass
