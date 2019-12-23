import datetime
import json
import logging
import subprocess
##
from lxml import etree
##
import aif.utils
import aif.disk.block_fallback as block
import aif.disk.luks_fallback as luks
import aif.disk.mdadm_fallback as mdadm


_logger = logging.getLogger(__name__)


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
            raise ValueError('Invalid vgobj type')
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
        cmd_str = ['lvcreate',
                   '--reportformat', 'json']
        if self.size > 0:
            cmd_str.extend(['--size', self.size])
        elif self.size == 0:
            cmd_str.extend(['--extents', '100%FREE'])
        cmd_str.extend([self.name,
                        self.vg.name])
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to create LV successfully')
        self.vg.lvs.append(self)
        self.created = True
        self.updateInfo()
        self.vg.updateInfo()
        return(None)

    def start(self):
        _logger.info('Activating LV {0} in VG {1}.'.format(self.name, self.vg.name))
        cmd_str = ['lvchange',
                   '--activate', 'y',
                   '--reportformat', 'json',
                   self.qualified_name]
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to activate LV successfully')
        self.updateInfo()
        return(None)

    def stop(self):
        _logger.info('Deactivating LV {0} in VG {1}.'.format(self.name, self.vg.name))
        cmd_str = ['lvchange',
                   '--activate', 'n',
                   '--reportformat', 'json',
                   self.qualified_name]
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to deactivate successfully')
        self.updateInfo()
        return(None)

    def updateInfo(self):
        if not self.created:
            _logger.warning('Attempted to updateInfo on an LV not created yet.')
            return(None)
        info = {}
        cmd = ['lvs',
               '--binary',
               '--nosuffix',
               '--units', 'b',
               '--options', '+lvall',
               '--reportformat', 'json',
               self.qualified_name]
        _info = subprocess.run(cmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(_info.args)))
        if _info.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(_info.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            self.info = None
            self.created = False
            return(None)
        _info = json.loads(_info.stdout.decode('utf-8'))['report'][0]['vg'][0]
        for k, v in _info.items():
            # ints
            if k in ('lv_fixed_minor', 'lv_kernel_major', 'lv_kernel_minor', 'lv_kernel_read_ahead', 'lv_major',
                     'lv_metadata_size', 'lv_minor', 'lv_size', 'seg_count'):
                try:
                    v = int(v)
                except ValueError:
                    v = 0
            # booleans - LVs apparently have a third value, "-1", which is "unknown". We translate to None.
            elif k in ('lv_active_exclusively', 'lv_active_locally', 'lv_active_remotely', 'lv_allocation_locked',
                       'lv_check_needed', 'lv_converting', 'lv_device_open', 'lv_historical', 'lv_image_synced',
                       'lv_inactive_table', 'lv_initial_image_sync', 'lv_live_table', 'lv_merge_failed', 'lv_merging',
                       'lv_skip_activation', 'lv_snapshot_invalid', 'lv_suspended'):
                if v == '-1':
                    v = None
                else:
                    v = (True if int(v) == 1 else False)
            # lists
            elif k in ('lv_ancestors', 'lv_descendants', 'lv_full_ancestors', 'lv_full_descendants', 'lv_lockargs',
                       'lv_modules', 'lv_permissions', 'lv_tags'):
                v = [i.strip() for i in v.split(',') if i.strip() != '']
            # date time strings
            elif k in ('lv_time', ):
                v = datetime.datetime.strptime(v, '%Y-%m-%d %H:%M:%S %z')
            elif v.strip() == '':
                v = None
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
            raise ValueError('Invalid partobj type')
        self.devpath = self.device.devpath
        self.is_pooled = False
        self.meta = None
        self._parseMeta()

    def _parseMeta(self):
        # Note, the "UUID" for LVM is *not* a true UUID (RFC4122) so we don't convert it.
        # https://unix.stackexchange.com/questions/173722/what-is-the-uuid-format-used-by-lvm
        meta = {}
        cmd = ['pvs',
               '--binary',
               '--nosuffix',
               '--units', 'b',
               '--options', '+pvall',
               '--reportformat', 'json',
               self.devpath]
        _meta = subprocess.run(cmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(_meta.args)))
        if _meta.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(_meta.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            self.meta = None
            self.is_pooled = False
            return(None)
        _meta = json.loads(_meta.stdout.decode('utf-8'))['report'][0]['pv'][0]
        for k, v in _meta.items():
            # We *could* regex this but the pattern would be a little more complex than idea,
            # especially for such predictable strings.
            # These are ints.
            if k in ('dev_size', 'pe_start', 'pv_ba_size', 'pv_ba_start', 'pv_ext_vsn', 'pv_free', 'pv_major',
                     'pv_mda_count', 'pv_mda_free', 'pv_mda_size', 'pv_mda_used_count', 'pv_minor', 'pv_pe_alloc_count',
                     'pv_pe_alloc_count', 'pv_size', 'pv_used'):
                v = int(v)
            # These are boolean.
            elif k in ('pv_allocatable', 'pv_duplicate', 'pv_exported', 'pv_in_use', 'pv_missing'):
                v = (True if int(v) == 1 else False)
            # This is a list.
            elif k == 'pv_tags':
                v = [i.strip() for i in v.split(',') if i.strip() != '']
            elif v.strip() == '':
                v = None
            meta[k] = v
        self.meta = meta
        self.is_pooled = True
        _logger.debug('Rendered meta: {0}'.format(meta))
        return(None)

    def prepare(self):
        if not self.meta:
            self._parseMeta()
        # *Technically*, we should vgreduce before pvremove, but eff it.
        cmd_str = ['pvremove',
                   '--force', '--force',
                   '--reportformat', 'json',
                   self.devpath]
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to remove PV successfully')
        cmd_str = ['pvcreate',
                   '--reportformat', 'json',
                   self.devpath]
        cmd = subprocess.run(cmd_str)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to format successfully')
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
        self.devpath = self.name
        self.info = None
        self.created = False

    def addPV(self, pvobj):
        if not isinstance(pvobj, PV):
            _logger.error('pvobj must be of type aif.disk.lvm.PV.')
            raise ValueError('Invalid pvbobj type')
        pvobj.prepare()
        self.pvs.append(pvobj)
        return(None)

    def create(self):
        if not self.pvs:
            _logger.error('Cannot create a VG with no PVs.')
            raise RuntimeError('Missing PVs')
        cmd_str = ['vgcreate',
                   '--reportformat', 'json',
                   '--physicalextentsize', '{0}b'.format(self.pe_size),
                   self.name]
        for pv in self.pvs:
            cmd_str.append(pv.devpath)
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to create VG successfully')
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
        cmd_str = ['vgchange',
                   '--activate', 'y',
                   '--reportformat', 'json',
                   self.name]
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to activate VG successfully')
        self.updateInfo()
        return(None)

    def stop(self):
        _logger.info('Deactivating VG: {0}.'.format(self.name))
        cmd_str = ['vgchange',
                   '--activate', 'n',
                   '--reportformat', 'json',
                   self.name]
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to deactivate VG successfully')
        self.updateInfo()
        return(None)

    def updateInfo(self):
        if not self.created:
            _logger.warning('Attempted to updateInfo on a VG not created yet.')
            return(None)
        info = {}
        cmd_str = ['vgs',
                   '--binary',
                   '--nosuffix',
                   '--units', 'b',
                   '--options', '+vgall',
                   '--reportformat', 'json',
                   self.name]
        _info = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(_info.args)))
        if _info.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(_info.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(_info, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            self.info = None
            self.created = False
            return(None)
        _info = json.loads(_info.stdout.decode('utf-8'))['report'][0]['vg'][0]
        for k, v in _info.items():
            # ints
            if k in ('lv_count', 'max_lv', 'max_pv', 'pv_count', 'snap_count', 'vg_extent_count', 'vg_extent_size',
                     'vg_free', 'vg_free_count', 'vg_mda_count', 'vg_mda_free', 'vg_mda_size', 'vg_mda_used_count',
                     'vg_missing_pv_count', 'vg_seqno', 'vg_size'):
                v = int(v)
            # booleans
            elif k in ('vg_clustered', 'vg_exported', 'vg_extendable', 'vg_partial', 'vg_shared'):
                v = (True if int(v) == 1 else False)
            # lists
            elif k in ('vg_lock_args', 'vg_permissions', 'vg_tags'):  # not 100% sure about vg_permissions...
                v = [i.strip() for i in v.split(',') if i.strip() != '']
            elif v.strip() == '':
                v = None
            info[k] = v
        self.info = info
        _logger.debug('Rendered info: {0}'.format(info))
        return(None)
