try:
    import dbus
    has_mod = True
except ImportError:
    # This is ineffecient; the native dbus module is preferred.
    # In Arch, this can be installed via the 'extra' repository package "python-dbus".
    import subprocess
    has_mod = False
##
from aif.disk.block import Disk, Partition
from aif.disk.luks import LUKS
from aif.disk.mdadm import Array


class PV(object):
    def __init__(self, partobj):
        self.devpath = None
        pass


class VG(object):
    def __init__(self, vg_xml, lv_objs):
        self.devpath = None
        pass


class LV(object):
    def __init__(self, lv_xml, pv_objs):
        pass
