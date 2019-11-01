import aif.disk.block_fallback as block
import aif.disk.lvm_fallback as lvm
import aif.disk.mdadm_fallback as mdadm


class LUKS(object):
    def __init__(self, partobj):
        self.devpath = None
        pass
