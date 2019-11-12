class Network(object):
    def __init__(self, network_xml):
        self.xml = network_xml
        self.hostname = self.xml.attrib['hostname']
        self.provider = self.xml.attrib.get('provider', 'netctl')
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

    def _initConns(self):
        for e in self.xml.xpath('ethernet|wireless'):
            if e.tag == 'ethernet':
                conn = self.provider.Ethernet(e)
            elif e.tag == 'wireless':
                conn = self.provider.Wireless(e)
            self.connections.append(conn)
