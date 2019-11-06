import subprocess
##
import aif.disk.block_fallback as block
import aif.disk.luks_fallback as luks
import aif.disk.mdadm_fallback as mdadm


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
