from . import _common
import aif.disk.block as block
import aif.disk.lvm as lvm
import aif.disk.mdadm as mdadm


_BlockDev = _common.BlockDev


class LUKS(object):
    def __init__(self, luks_xml, partobj):
        self.xml = luks_xml
        _common.addBDPlugin('crypto')
        self.devpath = None
        pass
