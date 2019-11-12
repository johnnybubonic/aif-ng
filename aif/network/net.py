class Network(object):
    def __init__(self, network_xml):
        self.xml = network_xml
        self.hostname = self.xml.attrib['hostname']
        self.provider = self.xml.attrib.get('provider', 'netctl')
        handler = None
        if self.provider == 'netctl':
            from . import netctl as handler
        elif self.provider == 'nm':
            from . import networkmanager as handler
        elif self.provider == 'systemd':
            from . import networkd as handler
        self.provider = handler
        if not self.provider:
            raise RuntimeError('Could not determine handler')
        self.connections = []

    def _initConns(self):
        pass
