from aif.disk.block import Disk, Partition
from aif.disk.lvm import LV
from aif.disk.mdadm import Array

class LUKS(object):
    def __init__(self, partobj):
        self.devpath = None
        pass
