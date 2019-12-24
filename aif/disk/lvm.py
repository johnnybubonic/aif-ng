import logging
# import uuid
##
from lxml import etree
##
from . import _common
import aif.utils
import aif.disk.block as block
import aif.disk.luks as luks
import aif.disk.mdadm as mdadm


_logger = logging.getLogger(__name__)


_BlockDev = _common.BlockDev


class LV(object):
    def __init__(self, lv_xml, vgobj):
        self.xml = lv_xml
        _logger.debug('lv_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.id = self.xml.attrib('id')
        self.name = self.xml.attrib('name')
        self.vg = vgobj
        self.qualified_name = '{0}/{1}'.format(self.vg.name, self.name)
        _logger.debug('Qualified name: {0}'.format(self.qualified_name))
        self.pvs = []
        if not isinstance(self.vg, VG):
            _logger.debug('vgobj must be of type aif.disk.lvm.VG')
            raise TypeError('Invalid vgobj type')
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
            _logger.debug('Found PV element: {0}'.format(etree.tostring(pe, with_tail = False).decode('utf-8')))
            pv_id = pe.attrib('source')
            if pv_id in _indexed_pvs.keys():
                self.pvs.append(_indexed_pvs[pv_id])
        if not self.pvs:  # We get all in the VG instead since none were explicitly assigned
            _logger.debug('No PVs explicitly designated to VG; adding all.')
            self.pvs = self.vg.pvs
        # Size processing. We have to do this after indexing PVs.
        # If not x['type'], assume *extents*, not sectors
        self.size = self.xml.attrib('size')  # Convert to bytes. Can get max from _BlockDev.lvm.vginfo(<VG>).free TODO
        x = dict(zip(('from_bgn', 'size', 'type'),
                     aif.utils.convertSizeUnit(self.xml.attrib['size'])))
        # self.size is bytes
        self.size = x['size']
        _extents = {'size': self.vg.info['extent_size'],
                    'total': 0}  # We can't use self.vg.info['extent_count'] because selective PVs.
        _sizes = {'total': 0,
                  'free': 0}
        _vg_pe = self.vg.info['extent_size']
        for pv in self.pvs:
            _sizes['total'] += pv.info['pv_size']
            _sizes['free'] += pv.info['pv_free']
            _extents['total'] += int(pv.info['pv_size'] / _extents['size'])
        if x['type'] == '%':
            self.size = int(_sizes['total'] * (0.01 * self.size))
        elif x['type'] is None:
            self.size = int(self.size * _extents['size'])
        else:
            self.size = int(aif.utils.size.convertStorage(x['size'],
                                                          x['type'],
                                                          target = 'B'))
        if self.size >= _sizes['total']:
            self.size = 0
        return(None)

    def create(self):
        if not self.pvs:
            _logger.error('Cannot create LV with no associated PVs')
            raise RuntimeError('Missing PVs')
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
        return(None)

    def start(self):
        _logger.info('Activating LV {0} in VG {1}.'.format(self.name, self.vg.name))
        _BlockDev.lvm.lvactivate(self.vg.name,
                                 self.name,
                                 True,
                                 None)
        self.updateInfo()
        return(None)

    def stop(self):
        _logger.info('Deactivating LV {0} in VG {1}.'.format(self.name, self.vg.name))
        _BlockDev.lvm.lvdeactivate(self.vg.name,
                                   self.name,
                                   None)
        self.updateInfo()
        return(None)

    def updateInfo(self):
        if not self.created:
            _logger.warning('Attempted to updateInfo on an LV not created yet.')
            return(None)
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
        _logger.debug('Rendered info: {0}'.format(info))
        return(None)


class PV(object):
    def __init__(self, pv_xml, partobj):
        self.xml = pv_xml
        _logger.debug('pv_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.id = self.xml.attrib('id')
        self.source = self.xml.attrib('source')
        self.device = partobj
        if not isinstance(self.device, (block.Disk,
                                        block.Partition,
                                        luks.LUKS,
                                        mdadm.Array)):
            _logger.error(('partobj must be of type '
                           'aif.disk.block.Disk, '
                           'aif.disk.block.Partition, '
                           'aif.disk.luks.LUKS, or'
                           'aif.disk.mdadm.Array.'))
            raise TypeError('Invalid partobj type')
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
            _logger.debug('PV device is not a PV yet.')
            self.meta = None
            self.is_pooled = False
            return(None)
        for k in dir(_meta):
            if k.startswith('_'):
                continue
            elif k in ('copy', ):
                continue
            v = getattr(_meta, k)
            meta[k] = v
        self.meta = meta
        _logger.debug('Rendered meta: {0}'.format(meta))
        self.is_pooled = True
        return(None)

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
                # I'd like to take the time now to remind you to NOT RUN AIF-NG ON A "PRODUCTION"-STATE MACHINE.
                # At least until I can maybe find a better way to determine which LVs to reduce on multi-LV VGs
                # so I can *then* use lvresize in a balanced manner, vgreduce, and pvmove/pvremove and not kill
                # everything.
                # TODO.
                for lv in _BlockDev.lvm.lvs():
                    if lv.vg_name == vg:
                        _logger.info('Removing LV {0} from VG {1}.'.format(lv.lv_name, vg))
                        _BlockDev.lvm.lvremove(vg, lv.lv_name)
                        _logger.debug('Reducing VG {0}.'.format(vg))
                        _BlockDev.lvm.vgreduce(vg)
                _logger.info('Removing VG {0}.'.format(vg))
                _BlockDev.lvm.vgremove(vg)  # This *shouldn't* fail. In theory. But LVM is lel.
                _logger.info('Removing PV {0}.'.format(self.devpath))
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
        opts = [_BlockDev.ExtraArg.new('--reportformat', 'json')]
        # FUCK. LVM. You can't *specify* a UUID.
        # u = uuid.uuid4()
        # opts.append(_BlockDev.ExtraArg.new('--uuid', str(u)))
        _BlockDev.lvm.pvcreate(self.devpath,
                               0,
                               0,
                               opts)
        _logger.info('Created PV {0} with opts {1}'.format(self.devpath, opts))
        self._parseMeta()
        return(None)


class VG(object):
    def __init__(self, vg_xml):
        self.xml = vg_xml
        _logger.debug('vg_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.id = self.xml.attrib('id')
        self.name = self.xml.attrib('name')
        self.pe_size = self.xml.attrib.get('extentSize', 0)
        if self.pe_size:
            x = dict(zip(('from_bgn', 'size', 'type'),
                         aif.utils.convertSizeUnit(self.pe_size)))
            if x['type']:
                self.pe_size = aif.utils.size.convertStorage(self.pe_size,
                                                             x['type'],
                                                             target = 'B')
        if not aif.utils.isPowerofTwo(self.pe_size):
            _logger.error('The PE size must be a power of two (in bytes).')
            raise ValueError('Invalid PE value')
        self.lvs = []
        self.pvs = []
        # self.tags = []
        # for te in self.xml.findall('tags/tag'):
        #     self.tags.append(te.text)
        _common.addBDPlugin('lvm')
        self.devpath = '/dev/{0}'.format(self.name)
        self.info = None
        self.created = False

    def addPV(self, pvobj):
        if not isinstance(pvobj, PV):
            _logger.error('pvobj must be of type aif.disk.lvm.PV.')
            raise TypeError('Invalid pvbobj type')
        pvobj.prepare()
        self.pvs.append(pvobj)
        return(None)

    def create(self):
        if not self.pvs:
            _logger.error('Cannot create a VG with no PVs.')
            raise RuntimeError('Missing PVs')
        opts = [_BlockDev.ExtraArg.new('--reportformat', 'json')]
        # FUCK. LVM. You can't *specify* a UUID.
        # u = uuid.uuid4()
        # opts.append(_BlockDev.ExtraArg.new('--uuid', str(u)))
        # for t in self.tags:
        #     opts.append(_BlockDev.ExtraArg.new('--addtag', t))
        _BlockDev.lvm.vgcreate(self.name,
                               [p.devpath for p in self.pvs],
                               self.pe_size,
                               opts)
        for pv in self.pvs:
            pv._parseMeta()
        self.created = True
        self.updateInfo()
        return(None)

    def createLV(self, lv_xml = None):
        if not self.created:
            _logger.info('Attempted to add an LV to a VG before it was created.')
            raise RuntimeError('LV before VG creation')
        # If lv_xml is None, we loop through our own XML.
        if lv_xml:
            _logger.debug('Explicit lv_xml specified: {0}'.format(etree.tostring(lv_xml,
                                                                                 with_tail = False).decode('utf-8')))
            lv = LV(lv_xml, self)
            lv.create()
            # self.lvs.append(lv)
        else:
            for le in self.xml.findall('logicalVolumes/lv'):
                _logger.debug('Found lv element: {0}'.format(etree.tostring(le, with_tail = False).decode('utf-8')))
                lv = LV(le, self)
                lv.create()
                # self.lvs.append(lv)
        self.updateInfo()
        return(None)

    def start(self):
        _logger.info('Activating VG: {0}.'.format(self.name))
        _BlockDev.lvm.vgactivate(self.name)
        self.updateInfo()
        return(None)

    def stop(self):
        _logger.info('Deactivating VG: {0}.'.format(self.name))
        _BlockDev.lvm.vgdeactivate(self.name)
        self.updateInfo()
        return(None)

    def updateInfo(self):
        if not self.created:
            _logger.warning('Attempted to updateInfo on a VG not created yet.')
            return(None)
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
        _logger.debug('Rendered info: {0}'.format(info))
        return(None)
