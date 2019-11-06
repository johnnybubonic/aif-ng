from . import _common
import aif.disk.block as block
import aif.disk.lvm as lvm
import aif.disk.mdadm as mdadm


BlockDev = _common.BlockDev


class LUKS(object):
    def __init__(self, partobj):
        self.devpath = None
        pass
