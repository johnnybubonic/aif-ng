import datetime
import re
import uuid
##
import aif.utils
import aif.constants
from . import _common
import aif.disk.block as block
import aif.disk.luks as luks
import aif.disk.lvm as lvm


_BlockDev = _common.BlockDev


class Member(object):
    def __init__(self, member_xml, partobj):
        self.xml = member_xml
        self.device = partobj
        if not isinstance(self.device, (block.Partition,
                                        block.Disk,
                                        Array,
                                        lvm.LV,
                                        luks.LUKS)):
            raise ValueError(('partobj must be of type '
                              'aif.disk.block.Disk, '
                              'aif.disk.block.Partition, '
                              'aif.disk.luks.LUKS, '
                              'aif.disk.lvm.LV, or'
                              'aif.disk.mdadm.Array'))
        _common.addBDPlugin('mdraid')
        self.devpath = self.device.devpath
        self.is_superblocked = None
        self.superblock = None
        self._parseDeviceBlock()

    def _parseDeviceBlock(self):
        # TODO: parity with mdadm_fallback.Member._parseDeviceBlock
        #       key names currently (probably) don't match and need to confirm the information's all present
        block = {}
        try:
            _block = _BlockDev.md.examine(self.devpath)
        except _BlockDev.MDRaidError:
            self.is_superblocked = False
            self.superblock = None
            return()
        for k in dir(_block):
            if k.startswith('_'):
                continue
            elif k in ('copy', 'eval'):
                continue
            v = getattr(_block, k)
            if k == 'level':
                v = int(re.sub(r'^raid', '', v))
            elif k == 'update_time':
                v = datetime.datetime.fromtimestamp(v)
            elif re.search('^(dev_)?uuid$', k):
                v = uuid.UUID(hex = v)
            block[k] = v
        self.superblock = block
        self.is_superblocked = True
        return()

    def prepare(self):
        try:
            _BlockDev.md.denominate(self.devpath)
        except _BlockDev.MDRaidError:
            pass
        _BlockDev.md.destroy(self.devpath)
        return()


class Array(object):
    def __init__(self, array_xml, homehost, devpath = None):
        self.xml = array_xml
        self.id = array_xml.attrib['id']
        self.level = int(self.xml.attrib['level'])
        if self.level not in aif.constants.MDADM_SUPPORTED_LEVELS:
            raise ValueError('RAID level must be one of: {0}'.format(', '.join([str(i)
                                                                                for i in
                                                                                aif.constants.MDADM_SUPPORTED_LEVELS])))
        self.metadata = self.xml.attrib.get('meta', '1.2')
        if self.metadata not in aif.constants.MDADM_SUPPORTED_METADATA:
            raise ValueError('Metadata version must be one of: {0}'.format(', '.join(
                                                                            aif.constants.MDADM_SUPPORTED_METADATA)))
        _common.addBDPlugin('mdraid')
        self.chunksize = int(self.xml.attrib.get('chunkSize', 512))
        if self.level in (4, 5, 6, 10):
            if not aif.utils.isPowerofTwo(self.chunksize):
                # TODO: log.warn instead of raise exception? Will mdadm lose its marbles if it *isn't* a proper number?
                raise ValueError('chunksize must be a power of 2 for the RAID level you specified')
        if self.level in (0, 4, 5, 6, 10):
            if not aif.utils.hasSafeChunks(self.chunksize):
                # TODO: log.warn instead of raise exception? Will mdadm lose its marbles if it *isn't* a proper number?
                raise ValueError('chunksize must be divisible by 4 for the RAID level you specified')
        self.layout = self.xml.attrib.get('layout', 'none')
        if self.level in aif.constants.MDADM_SUPPORTED_LAYOUTS.keys():
            matcher, layout_default = aif.constants.MDADM_SUPPORTED_LAYOUTS[self.level]
            if not matcher.search(self.layout):
                if layout_default:
                    self.layout = layout_default
                else:
                    self.layout = None  # TODO: log.warn?
        else:
            self.layout = None
        self.devname = self.xml.attrib['name']
        self.fulldevname = '{0}:{1}'.format(self.homehost, self.devname)
        self.devpath = devpath
        if not self.devpath:
            self.devpath = '/dev/md/{0}'.format(self.devname)
        self.updateStatus()
        self.homehost = homehost
        self.members = []
        self.state = None
        self.info = None

    def addMember(self, memberobj):
        if not isinstance(memberobj, Member):
            raise ValueError('memberobj must be of type aif.disk.mdadm.Member')
        memberobj.prepare()
        self.members.append(memberobj)
        return()

    def create(self):
        if not self.members:
            raise RuntimeError('Cannot create an array with no members')
        opts = [_BlockDev.ExtraArg.new('--homehost',
                                       self.homehost),
                _BlockDev.ExtraArg.new('--name',
                                       self.devname)]
        if self.layout:
            opts.append(_BlockDev.ExtraArg.new('--layout',
                                               self.layout))
        _BlockDev.md.create(self.devname,
                            str(self.level),
                            [i.devpath for i in self.members],
                            0,
                            self.metadata,
                            True,
                            (self.chunksize * 1024),
                            opts)
        for m in self.members:
            m._parseDeviceBlock()
        self.updateStatus()
        self.writeConf()
        self.devpath = self.info['device']
        self.state = 'new'
        return()

    def start(self, scan = False):
        if not any((self.members, self.devpath)):
            raise RuntimeError('Cannot assemble an array with no members (for hints) or device path')
        if scan:
            target = None
        else:
            target = self.devname
        _BlockDev.md.activate(target,
                              [i.devpath for i in self.members],  # Ignored if scan mode enabled
                              None,
                              True,
                              None)
        self.state = 'assembled'
        return()

    def stop(self):
        _BlockDev.md.deactivate(self.devname)
        self.state = 'disassembled'
        return()

    def updateStatus(self):
        _status = _BlockDev.md.detail(self.devname)
        # TODO: parity with mdadm_fallback.Array.updateStatus
        #       key names currently (probably) don't match and need to confirm the information's all present
        info = {}
        for k in dir(_status):
            if k.startswith('_'):
                continue
            elif k in ('copy',):
                continue
            v = getattr(_status, k)
            if k == 'level':
                v = int(re.sub(r'^raid', '', v))
            elif k == 'creation_time':
                # TODO: Is this portable/correct? Or do I need to do something like '%a %b %d %H:%M:%s %Y'?
                v = datetime.datetime.strptime(v, '%c')
            elif k == 'uuid':
                v = uuid.UUID(hex = v)
            info[k] = v
        self.info = info
        return()

    def writeConf(self, conf = '/etc/mdadm.conf'):
        with open(conf, 'r') as fh:
            conflines = fh.read().splitlines()
        arrayinfo = ('ARRAY '
                     '{device} '
                     'metadata={metadata} '
                     'name={name} '
                     'UUID={converted_uuid}').format(**self.info,
                                                     converted_uuid = _BlockDev.md.get_md_uuid(str(self.info['uuid'])))
        if arrayinfo not in conflines:
            r = re.compile(r'^ARRAY\s+{0}'.format(self.info['device']))
            nodev = True
            for l in conflines:
                if r.search(l):
                    nodev = False
                    # TODO: logging?
                    # and/or Raise an exception here;
                    # an array already exists with that name but not with the same opts/GUID/etc.
                    break
            if nodev:
                with open(conf, 'a') as fh:
                    fh.write('{0}\n'.format(arrayinfo))
        return()
