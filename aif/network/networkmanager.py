import configparser
import datetime
import os
import uuid
##
import aif.utils
from . import _common


class Connection(_common.BaseConnection):
    def __init__(self, iface_xml):
        super().__init__(iface_xml)
        self.provider_type = 'NetworkManager'
        self.packages = set('networkmanager')
        self.services = {
            ('/usr/lib/systemd/system/NetworkManager.service'): ('etc/systemd/system/'
                                                                 'multi-user.target.wants/'
                                                                 'NetworkManager.service'),
            ('/usr/lib/systemd/system/NetworkManager-dispatcher.service'): ('etc/systemd/system/'
                                                                            'dbus-org.freedesktop.'
                                                                            'nm-dispatcher.service'),
            ('/usr/lib/systemd/system/NetworkManager-wait-online.service'): ('etc/systemd/'
                                                                             'system/'
                                                                             'network-online.target.wants/'
                                                                             'NetworkManager-wait-online.service')}
        self.uuid = uuid.uuid4()

    def _initCfg(self):
        if self.device == 'auto':
            self.device = _common.getDefIface(self.connection_type)
        self._cfg = configparser.ConfigParser()
        self._cfg.optionxform = str
        self._cfg['connection'] = {'id': self.id,
                                   'uuid': self.uuid,
                                   'type': self.connection_type,
                                   'interface-name': self.device,
                                   'permissions': '',
                                   'timestamp': datetime.datetime.utcnow().timestamp()}
        # We *theoretically* could do this in _initAddrs() but we do it separately so we can trim out duplicates.
        # TODO: rework this? we technically don't need to split in ipv4/ipv6 since ipaddress does that for us.
        for addrtype, addrs in self.addrs.items():
            self._cfg[addrtype] = {}
            cidr_gws = {}
            # Routing
            if not self.is_defroute:
                self._cfg[addrtype]['never-default'] = 'true'
            if not self.auto['routes'][addrtype]:
                self._cfg[addrtype]['ignore-auto-routes'] = 'true'
            # DNS
            self._cfg[addrtype]['dns-search'] = (self.domain if self.domain else '')
            if not self.auto['resolvers'][addrtype]:
                self._cfg[addrtype]['ignore-auto-dns'] = 'true'
            # Address handling
            if addrtype == 'ipv6':
                self._cfg[addrtype]['addr-gen-mode'] = 'stable-privacy'
            if not addrs and not self.auto['addresses'][addrtype]:
                self._cfg[addrtype]['method'] = 'ignore'
            elif self.auto['addresses'][addrtype]:
                if addrtype == 'ipv4':
                    self._cfg[addrtype]['method'] = 'auto'
                else:
                    self._cfg[addrtype]['method'] = ('auto' if self.auto['addresses'][addrtype] == 'slaac'
                                                     else 'dhcp6')
            else:
                self._cfg[addrtype]['method'] = 'manual'
            for idx, (ip, cidr, gw) in enumerate(addrs):
                if cidr not in cidr_gws.keys():
                    cidr_gws[cidr] = gw
                    new_cidr = True
                else:
                    new_cidr = False
                addrnum = idx + 1
                addr_str = '{0}/{1}'.format(str(ip), str(cidr.prefixlen))
                if new_cidr:
                    addr_str = '{0},{1}'.format(addr_str, str(gw))
                self._cfg[addrtype]['address{0}'.format(addrnum)] = addr_str
            # Resolvers
            for resolver in self.resolvers:
                if addrtype == 'ipv{0}'.format(resolver.version):
                    if 'dns' not in self._cfg[addrtype]:
                        self._cfg[addrtype]['dns'] = []
                    self._cfg[addrtype]['dns'].append(str(resolver))
            if 'dns' in self._cfg[addrtype].keys():
                self._cfg[addrtype]['dns'] = '{0};'.format(';'.join(self._cfg[addrtype]['dns']))
            # Routes
            for idx, (dest, net, gw) in self.routes[addrtype]:
                routenum = idx + 1
                self._cfg[addrtype]['route{0}'.format(routenum)] = '{0}/{1},{2}'.format(str(dest),
                                                                                        str(net.prefixlen),
                                                                                        str(gw))
        self._initConnCfg()
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
        self._cfg[self.connection_type] = {'mac-address-blacklist': ''}
        return()


class Wireless(Connection):
    def __init__(self, iface_xml):
        super().__init__(iface_xml)
        self.connection_type = 'wireless'
        self._initCfg()

    def _initConnCfg(self):
        self._cfg['wifi'] = {'mac-address-blacklist': '',
                             'mode': 'infrastructure',
                             'ssid': self.xml.attrib['essid']}
        try:
            bssid = self.xml.attrib.get('bssid').strip()
        except AttributeError:
            bssid = None
        if bssid:
            bssid = _common.canonizeEUI(bssid)
            self._cfg['wifi']['bssid'] = bssid
            self._cfg['wifi']['seen-bssids'] = '{0};'.format(bssid)
        crypto = self.xml.find('encryption')
        if crypto:
            self.packages.add('wpa_supplicant')
            self._cfg['wifi-security'] = {}
            crypto = _common.convertWifiCrypto(crypto, self._cfg['wifi']['ssid'])
            # if crypto['type'] in ('wpa', 'wpa2', 'wpa3'):
            if crypto['type'] in ('wpa', 'wpa2'):
                # TODO: WPA2 enterprise
                self._cfg['wifi-security']['key-mgmt'] = 'wpa-psk'
            # if crypto['type'] in ('wep', 'wpa', 'wpa2', 'wpa3'):
            if crypto['type'] in ('wpa', 'wpa2'):
                self._cfg['wifi-security']['psk'] = crypto['auth']['psk']
        return()
