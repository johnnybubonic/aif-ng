import subprocess
##
import aif.disk.block_fallback as block
import aif.disk.luks_fallback as luks
import aif.disk.mdadm_fallback as mdadm


class PV(object):
    def __init__(self, pv_xml, partobj):
        self.xml = pv_xml
        self.id = self.xml.attrib('id')
        self.source = self.xml.attrib('source')
        self.device = partobj
        if not isinstance(self.device, (block.Disk,
                                        block.Partition,
                                        luks.LUKS,
                                        mdadm.Array)):
            raise ValueError(('partobj must be of type '
                              'aif.disk.block.Disk, '
                              'aif.disk.block.Partition, '
                              'aif.disk.luks.LUKS, or'
                              'aif.disk.mdadm.Array'))
        # TODO
        self.devpath = self.device.devpath
        pass


class LV(object):
    def __init__(self, lv_xml, pv_objs, vg_obj):
        self.xml = lv_xml
        self.id = self.xml.attrib('id')
        self.name = self.xml.attrib('name')
        self.size = self.xml.attrib('size')  # Convert to bytes. Can get max from _BlockDev.lvm.vginfo(<VG>).free
        self.pvs = pv_objs
        self.vg = vg_obj
        for p in self.pvs:
            if not isinstance(p, PV):
                raise ValueError('pv_objs must be a list-like containing aif.disk.lvm.PV items')
        if not isinstance(self.vg, VG):
            raise ValueError('vg_obj must be of type aif.disk.lvm.VG')
        # TODO
        self.devpath = None
        pass


class VG(object):
    def __init__(self, vg_xml, lv_objs):
        self.xml = vg_xml
        self.id = self.xml.attrib('id')
        self.name = self.xml.attrib('name')
        self.lvs = lv_objs
        for l in self.lvs:
            if not isinstance(l, LV):
                raise ValueError('lv_objs must be a list-like containing aif.disk.lvm.LV items')
        # TODO
        self.devpath = None
        pass

