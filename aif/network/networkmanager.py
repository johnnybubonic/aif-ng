from . import _common

_NM = _common.NM


class Connection(object):
    def __init__(self, iface_xml):
        self.xml = iface_xml
        self.connection_type = None
        self.provider_type = 'NetworkManager'
        self.client = _NM.Client.new()


class Ethernet(Connection):
    def __init__(self, iface_xml):
        super().__init__(iface_xml)
        self.connection_type = 'ethernet'


class Wireless(Connection):
    def __init__(self, iface_xml):
        super().__init__(iface_xml)
        self.connection_type = 'wireless'
