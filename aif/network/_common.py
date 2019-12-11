import binascii
import ipaddress
import os
import pathlib
import re
##
from passlib.crypto.digest import pbkdf2_hmac
from pyroute2 import IPDB
##
import aif.utils

# Not needed
# import gi
# gi.require_version('NM', '1.0')
# from gi.repository import GObject, NM, GLib


def canonizeEUI(phyaddr):
    # The easy transformations first.
    phyaddr = re.sub(r'[.:-]', '', phyaddr.upper().strip())
    eui = ':'.join(['{0}'.format(phyaddr[i:i+2]) for i in range(0, 12, 2)])
    return(eui)


def convertIpTuples(addr_xmlobj):
    # These tuples follow either:
    #   ('dhcp'/'dhcp6'/'slaac', None, None) for auto configuration
    #   (ipaddress.IPv4/6Address(IP), CIDR, ipaddress.IPv4/6Address(GW)) for static configuration
    if addr_xmlobj.text in ('dhcp', 'dhcp6', 'slaac'):
        addr = addr_xmlobj.text.strip()
        net = None
        gw = None
    else:
        components = addr_xmlobj.text.strip().split('/')
        if len(components) > 2:
            raise ValueError('Invalid IP/CIDR format: {0}'.format(addr_xmlobj.text))
        if len(components) == 1:
            addr = ipaddress.ip_address(components[0])
            if addr.version == 4:
                components.append('24')
            elif addr.version == 6:
                components.append('64')
        addr = ipaddress.ip_address(components[0])
        net = ipaddress.ip_network('/'.join(components), strict = False)
        try:
            gw = ipaddress.ip_address(addr_xmlobj.attrib.get('gateway').strip())
        except (ValueError, AttributeError):
            gw = next(net.hosts())
    return((addr, net, gw))


def convertPSK(ssid, passphrase):
    try:
        passphrase = passphrase.encode('utf-8').decode('ascii').strip('\r').strip('\n')
    except UnicodeDecodeError:
        raise ValueError('passphrase must be an ASCII string')
    if len(ssid) > 32:
        raise ValueError('ssid must be <= 32 characters')
    if not 7 < len(passphrase) < 64:
        raise ValueError('passphrase must be >= 8 and <= 32 characters')
    raw_psk = pbkdf2_hmac('sha1', str(passphrase), str(ssid), 4096, 32)
    hex_psk = binascii.hexlify(raw_psk)
    str_psk = hex_psk.decode('utf-8')
    return(str_psk)


def convertWifiCrypto(crypto_xmlobj, ssid):
    crypto = {'type': crypto_xmlobj.find('type').text.strip(),
              'auth': {}}
    creds_xml = crypto_xmlobj.xpath('psk|enterprise')[0]
    # if crypto['type'] in ('wpa', 'wpa2', 'wpa3'):
    if crypto['type'] in ('wpa', 'wpa2'):
        crypto['mode'] = creds_xml.tag
        if crypto['mode'] == 'psk':
            crypto['mode'] = 'personal'
    else:
        crypto['mode'] = None
    if crypto['mode'] == 'personal':
        psk_xml = creds_xml.find('psk')
        if aif.utils.xmlBool(psk_xml.attrib.get('isKey', 'false')):
            try:
                crypto['auth']['passphrase'] = psk_xml.text.strip('\r').strip('\n')
            except UnicodeDecodeError:
                raise ValueError('WPA-PSK passphrases must be ASCII')
            crypto['auth']['psk'] = convertPSK(ssid, crypto['auth']['passphrase'])
        else:
            crypto['auth']['psk'] = psk_xml.text.strip().lower()
    # TODO: enterprise support
    # elif crypto['mode'] == 'enterprise':
    #     pass
    return(crypto)


def getDefIface(ifacetype):
    if ifacetype == 'ethernet':
        if isNotPersistent():
            prefix = 'eth'
        else:
            prefix = 'en'
    elif ifacetype == 'wireless':
        prefix = 'wl'
    else:
        raise ValueError('ifacetype must be one of "ethernet" or "wireless"')
    ifname = None
    with IPDB() as ipdb:
        for iface in ipdb.interfaces.keys():
            if iface.startswith(prefix):
                ifname = iface
                break
    if not ifname:
        return(None)
    return(ifname)


def isNotPersistent(chroot_base = '/'):
    chroot_base = pathlib.Path(chroot_base)
    systemd_override = chroot_base.joinpath('etc',
                                            'systemd',
                                            'network',
                                            '99-default.link')
    kernel_cmdline = chroot_base.joinpath('proc', 'cmdline')
    devnull = chroot_base.joinpath('dev', 'null')
    rootdevnull = pathlib.PosixPath('/dev/null')
    if os.path.islink(systemd_override) and pathlib.Path(systemd_override).resolve() in (devnull, rootdevnull):
        return(True)
    cmds = aif.utils.kernelCmdline(chroot_base)
    if 'net.ifnames' in cmds.keys() and cmds['net.ifnames'] == '0':
        return(True)
    return(False)


class BaseConnection(object):
    def __init__(self, iface_xml):
        self.xml = iface_xml
        self.id = self.xml.attrib['id'].strip()
        self.device = self.xml.attrib['device'].strip()
        self.is_defroute = aif.utils.xmlBool(self.xml.attrib.get('defroute', 'false').strip())
        try:
            self.domain = self.xml.attrib.get('searchDomain').strip()
        except AttributeError:
            self.domain = None
        self.dhcp_client = self.xml.attrib.get('dhcpClient', 'dhcpcd').strip()
        self._cfg = None
        self.connection_type = None
        self.provider_type = None
        self.packages = []
        self.services = {}
        self.resolvers = []
        self.addrs = {'ipv4': [],
                      'ipv6': []}
        self.routes = {'ipv4': [],
                       'ipv6': []}
        self.auto = {}
        for x in ('resolvers', 'routes', 'addresses'):
            self.auto[x] = {}
            x_xml = self.xml.find(x)
            for t in ('ipv4', 'ipv6'):
                if t == 'ipv6' and x == 'addresses':
                    self.auto[x][t] = 'slaac'
                else:
                    self.auto[x][t] = True
                if x_xml:
                    t_xml = x_xml.find(t)
                    if t_xml:
                        if t == 'ipv6' and x == 'addresses':
                            a = t_xml.attrib.get('auto', 'slaac').strip()
                            if a.lower() in ('false', '0', 'none'):
                                self.auto[x][t] = False
                            else:
                                self.auto[x][t] = a
                        else:
                            self.auto[x][t] = aif.utils.xmlBool(t_xml.attrib.get('auto', 'true').strip())
        # These defaults are from the man page. However, we might want to add:
        # domain-search, netbios-scope, interface-mtu, rfc3442-classless-static-routes, ntp-servers,
        # dhcp6.fqdn, dhcp6.sntp-servers
        # under requests and for requires, maybe:
        # routers, domain-name-servers, domain-name, domain-search, host-name
        self.dhcp_defaults = {
            'dhclient': {'requests': {'ipv4': ('subnet-mask', 'broadcast-address', 'time-offset', 'routers',
                                               'domain-name', 'domain-name-servers', 'host-name'),
                                      'ipv6': ('dhcp6.name-servers',
                                               'dhcp6.domain-search')},
                         'requires': {'ipv4': tuple(),
                                      'ipv6': tuple()}},
            'dhcpcd': {'default_opts': ('hostname', 'duid', 'persistent', 'slaac private', 'noipv4ll'),
                       # dhcpcd -V to display variables.
                       # "option <foo>", prepend "dhcp6_" for ipv6. if no ipv6 opts present, same are mapped to ipv6.
                       # But we explicitly add them for munging downstream.
                       'requests': {'ipv4': ('rapid_commit', 'domain_name_servers', 'domain_name', 'domain_search',
                                             'host_name', 'classless_static_routes', 'interface_mtu'),
                                    'ipv6': ('dhcp6_rapid_commit', 'dhcp6_domain_name_servers', 'dhcp6_domain_name',
                                             'dhcp6_domain_search', 'dhcp6_host_name', 'dhcp6_classless_static_routes',
                                             'dhcp6_interface_mtu')},
                       # "require <foo>"
                       'requires': {'ipv4': ('dhcp_server_identifier', ),
                                    'ipv6': tuple()}}}
        self._initAddrs()
        self._initResolvers()
        self._initRoutes()

    def _initAddrs(self):
        for addrtype in ('ipv4', 'ipv6'):
            for a in self.xml.findall('addresses/{0}/address'.format(addrtype)):
                addrset = convertIpTuples(a)
                if addrset not in self.addrs[addrtype]:
                    self.addrs[addrtype].append(addrset)
        return(None)

    def _initCfg(self):
        # A dummy method; this is overridden by the subclasses.
        # It's honestly here to make my IDE stop complaining. :)
        pass
        return(None)

    def _initConnCfg(self):
        # A dummy method; this is overridden by the subclasses.
        # It's honestly here to make my IDE stop complaining. :)
        pass
        return(None)

    def _initResolvers(self):
        resolvers_xml = self.xml.find('resolvers')
        if resolvers_xml:
            for r in resolvers_xml.findall('resolver'):
                resolver = ipaddress.ip_address(r.text.strip())
                if resolver not in self.resolvers:
                    self.resolvers.append(resolver)
        return(None)

    def _initRoutes(self):
        routes_xml = self.xml.find('routes')
        if routes_xml:
            for addrtype in ('ipv4', 'ipv6'):
                for a in self.xml.findall('routes/{0}/route'.format(addrtype)):
                    addrset = convertIpTuples(a)
                    if addrset not in self.routes[addrtype]:
                        self.routes[addrtype].append(addrset)
        return(None)

    def _writeConnCfg(self, chroot_base):
        # Dummy method.
        pass
        return(None)
