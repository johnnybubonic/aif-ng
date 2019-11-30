import os


class Network(object):
    def __init__(self, network_xml):
        self.xml = network_xml
        self.hostname = self.xml.attrib['hostname'].strip()
        self.provider = self.xml.attrib.get('provider', 'systemd').strip()
        handler = None
        if self.provider == 'netctl':
            import aif.network.netctl as handler
        elif self.provider == 'nm':
            import aif.network.networkmanager as handler
        elif self.provider == 'systemd':
            import aif.network.networkd as handler
        self.provider = handler
        if not self.provider:
            raise RuntimeError('Could not determine handler')
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

    def apply(self, chroot_base):
        cfg = os.path.join(chroot_base, 'etc', 'hostname')
        with open(cfg, 'w') as fh:
            fh.write('{0}\n'.format(self.hostname))
        os.chown(cfg, 0, 0)
        os.chmod(cfg, 0o0644)
        # TODO: symlinks for systemd for provider
        # TODO: writeConf for provider

        return()
