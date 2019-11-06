from . import _common
import aif.disk.block as block
import aif.disk.luks as luks
import aif.disk.mdadm as mdadm


_BlockDev = _common.BlockDev


class PV(object):
    def __init__(self, pv_xml, partobj):
        self.xml = pv_xml
        _common.addBDPlugin('lvm')
        self.devpath = None
        pass


class VG(object):
    def __init__(self, vg_xml, lv_objs):
        self.xml = vg_xml
        _common.addBDPlugin('lvm')
        self.devpath = None
        pass


class LV(object):
    def __init__(self, lv_xml, pv_objs):
        self.xml = lv_xml
        _common.addBDPlugin('lvm')
        pass
