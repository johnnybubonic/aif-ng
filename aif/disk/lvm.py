import uuid
##
from . import _common
import aif.disk.block as block
import aif.disk.luks as luks
import aif.disk.mdadm as mdadm


_BlockDev = _common.BlockDev


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
        _common.addBDPlugin('lvm')
        self.devpath = self.device.devpath
        self.is_pooled = False
        self.meta = None
        self._parseMeta()

    def _parseMeta(self):
        # Note, the "UUID" for LVM is *not* a true UUID (RFC4122) so we don't convert it.
        # https://unix.stackexchange.com/questions/173722/what-is-the-uuid-format-used-by-lvm
        # TODO: parity with lvm_fallback.PV._parseMeta
        #       key names currently (probably) don't match and need to confirm the information's all present
        meta = {}
        try:
            _meta = _BlockDev.lvm.pvinfo(self.devpath)
        except _BlockDev.LVMError:
            self.meta = None
            self.is_pooled = False
            return()
        for k in dir(_meta):
            if k.startswith('_'):
                continue
            elif k in ('copy',):
                continue
            v = getattr(_meta, k)
            meta[k] = v
        self.meta = meta
        self.is_pooled = True
        return()

    def prepare(self):
        try:
            if not self.meta:
                self._parseMeta()
            if self.meta:
                vg = self.meta['vg_name']
                # LVM is SO. DUMB.
                # If you're using LVM, seriously - just switch your model to mdadm. It lets you do things like
                # remove disks live without restructuring the entire thing.
                # That said, because the config references partitions/disks/arrays/etc. created *in the same config*,
                # and it's all dependent on block devices defined in the thing, we can be reckless here.
                # I'd like to take the time now to remind you to NOT RUN AIF-NG ON A "LIVE" MACHINE.
                # At least until I can maybe find a better way to determine which LVs to reduce on multi-LV VGs
                # so I can *then* use lvresize in a balanced manner, vgreduce, and pvmove/pvremove and not kill
                # everything.
                # TODO.
                for lv in _BlockDev.lvm.lvs():
                    if lv.vg_name == vg:
                        _BlockDev.lvm.lvremove(vg, lv.lv_name)
                        _BlockDev.lvm.vgreduce(vg)
                _BlockDev.lvm.vgremove(vg)  # This *shouldn't* fail. In theory. But LVM is lel.
                _BlockDev.lvm.pvremove(self.devpath)
                # Or if I can get this working properly. Shame it isn't automagic.
                # Seems to kill the LV by dropping a PV under it. Makes sense, but STILL. LVM IS SO DUMB.
                # _BlockDev.lvm.vgdeactivate(vg)
                # _BlockDev.lvm.pvremove(self.devpath)
                # _BlockDev.lvm.vgreduce(vg)
                # _BlockDev.lvm.vgactivate(vg)
                ##
                self.meta = None
                self.is_pooled = False
        except _BlockDev.LVMError:
            self.meta = None
            self.is_pooled = False
        u = uuid.uuid4()
        opts = [_BlockDev.ExtraArg.new('--reportformat', 'json')]
        # FUCK. LVM. You can't *specify* a UUID.
        # u = uuid.uuid4()
        # opts.append(_BlockDev.ExtraArg.new('--uuid', str(u)))
        _BlockDev.lvm.pvcreate(self.devpath,
                               0,
                               0,
                               opts)
        self._parseMeta()
        return()


class VG(object):
    def __init__(self, vg_xml):
        self.xml = vg_xml
        self.id = self.xml.attrib('id')
        self.name = self.xml.attrib('name')
        self.lvs = []
        self.pvs = []
        # self.tags = []
        # for te in self.xml.findall('tags/tag'):
        #     self.tags.append(te.text)
        _common.addBDPlugin('lvm')
        self.devpath = self.name
        self.info = None
        self.created = False

    def addPV(self, pvobj):
        if not isinstance(pvobj, PV):
            raise ValueError('pvobj must be of type aif.disk.lvm.PV')
        pvobj.prepare()
        self.pvs.append(pvobj)
        return()

    def create(self):
        if not self.pvs:
            raise RuntimeError('Cannot create a VG with no PVs')
        opts = [_BlockDev.ExtraArg.new('--reportformat', 'json')]
        # FUCK. LVM. You can't *specify* a UUID.
        # u = uuid.uuid4()
        # opts.append(_BlockDev.ExtraArg.new('--uuid', str(u)))
        # for t in self.tags:
        #     opts.append(_BlockDev.ExtraArg.new('--addtag', t))
        _BlockDev.lvm.vgcreate(self.name,
                               [p.devpath for p in self.pvs],
                               0,
                               opts)
        for p in self.pvs:
            p._parseMeta()
        self.created = True
        self.updateInfo()
        return()

    def createLV(self, lv_xml = None):
        if not self.created:
            raise RuntimeError('VG must be created before LVs can be added')
        # If lv_xml is None, we loop through our own XML.
        if lv_xml:
            lv = LV(lv_xml, self)
            lv.create()
            # self.lvs.append(lv)
        else:
            for le in self.xml.findall('logicalVolumes/lv'):
                lv = LV(le, self)
                lv.create()
                # self.lvs.append(lv)
        self.updateInfo()
        return()

    def start(self):
        _BlockDev.lvm.vgactivate(self.name)
        self.updateInfo()
        return()

    def stop(self):
        _BlockDev.lvm.vgdeactivate(self.name)
        self.updateInfo()
        return()

    def updateInfo(self):
        if not self.created:
            return()
        _info = _BlockDev.lvm.vginfo(self.name)
        # TODO: parity with lvm_fallback.VG.updateInfo
        #       key names currently (probably) don't match and need to confirm the information's all present
        info = {}
        for k in dir(_info):
            if k.startswith('_'):
                continue
            elif k in ('copy',):
                continue
            v = getattr(_info, k)
            info[k] = v
        self.info = info
        return()


class LV(object):
    def __init__(self, lv_xml, vgobj):
        self.xml = lv_xml
        self.id = self.xml.attrib('id')
        self.name = self.xml.attrib('name')
        self.size = self.xml.attrib('size')  # Convert to bytes. Can get max from _BlockDev.lvm.vginfo(<VG>).free TODO
        self.vg = vgobj
        self.pvs = []
        if not isinstance(self.vg, VG):
            raise ValueError('vgobj must be of type aif.disk.lvm.VG')
        _common.addBDPlugin('lvm')
        self.info = None
        self.devpath = '/dev/{0}/{1}'.format(self.vg.name, self.name)
        self.created = False
        self.updateInfo()
        self._initLV()

    def _initLV(self):
        self.pvs = []
        _indexed_pvs = {i.id: i for i in self.vg.pvs}
        for pe in self.xml.findall('pvMember'):
            pv_id = pe.attrib('source')
            if pv_id in _indexed_pvs.keys():
                self.pvs.append(_indexed_pvs[pv_id])
        if not self.pvs:  # We get all in the VG instead since none were explicitly assigned
            self.pvs = self.vg.pvs
        return()

    def create(self):
        if not self.pvs:
            raise RuntimeError('Cannot create LV with no associated LVs')
        opts = [_BlockDev.ExtraArg.new('--reportformat', 'json')]
        # FUCK. LVM. You can't *specify* a UUID.
        # u = uuid.uuid4()
        # opts.append(_BlockDev.ExtraArg.new('--uuid', str(u)))
        # for t in self.tags:
        #     opts.append(_BlockDev.ExtraArg.new('--addtag', t))
        _BlockDev.lvm.lvcreate(self.vg.name,
                               self.name,
                               self.size,
                               None,
                               [i.devpath for i in self.pvs],
                               opts)
        self.vg.lvs.append(self)
        self.created = True
        self.updateInfo()
        self.vg.updateInfo()
        return()

    def start(self):
        _BlockDev.lvm.lvactivate(self.vg.name,
                                 self.name,
                                 True,
                                 None)
        self.updateInfo()
        return()

    def stop(self):
        _BlockDev.lvm.lvdeactivate(self.vg.name,
                                   self.name,
                                   None)
        self.updateInfo()
        return()

    def updateInfo(self):
        if not self.created:
            return()
        _info = _BlockDev.lvm.lvinfo(self.vg.name, self.name)
        # TODO: parity with lvm_fallback.LV.updateInfo
        #       key names currently (probably) don't match and need to confirm the information's all present
        info = {}
        for k in dir(_info):
            if k.startswith('_'):
                continue
            elif k in ('copy',):
                continue
            v = getattr(_info, k)
            info[k] = v
        self.info = info
        return()
