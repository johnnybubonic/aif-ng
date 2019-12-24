import datetime
import logging
import os
import re
import uuid
##
from lxml import etree
##
import aif.utils
import aif.constants
from . import _common
import aif.disk.block as block
import aif.disk.luks as luks
import aif.disk.lvm as lvm


_logger = logging.getLogger(__name__)


_BlockDev = _common.BlockDev


class Member(object):
    def __init__(self, member_xml, partobj):
        self.xml = member_xml
        _logger.debug('member_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.device = partobj
        if not isinstance(self.device, (block.Disk,
                                        block.Partition,
                                        Array,
                                        luks.LUKS,
                                        lvm.LV)):
            _logger.error(('partobj must be of type '
                           'aif.disk.block.Disk, '
                           'aif.disk.block.Partition, '
                           'aif.disk.luks.LUKS, '
                           'aif.disk.lvm.LV, or'
                           'aif.disk.mdadm.Array.'))
            raise TypeError('Invalid partobj type')
        _common.addBDPlugin('mdraid')
        self.devpath = self.device.devpath
        self.is_superblocked = None
        self.superblock = None
        self._parseDeviceBlock()

    def _parseDeviceBlock(self):
        _logger.info('Parsing {0} device block metainfo.'.format(self.devpath))
        # TODO: parity with mdadm_fallback.Member._parseDeviceBlock
        #       key names currently (probably) don't match and need to confirm the information's all present
        block = {}
        try:
            _block = _BlockDev.md.examine(self.devpath)
        except _BlockDev.MDRaidError:
            _logger.debug('Member device is not a member yet.')
            self.is_superblocked = False
            self.superblock = None
            return(None)
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
        _logger.debug('Rendered superblock info: {0}'.format(block))
        self.is_superblocked = True
        return(None)

    def prepare(self):
        try:
            _BlockDev.md.denominate(self.devpath)
        except _BlockDev.MDRaidError:
            pass
        _BlockDev.md.destroy(self.devpath)
        self._parseDeviceBlock()
        return(None)


class Array(object):
    def __init__(self, array_xml, homehost, devpath = None):
        self.xml = array_xml
        _logger.debug('array_xml: {0}'.format(etree.tostring(array_xml, with_tail = False).decode('utf-8')))
        self.id = self.xml.attrib['id']
        self.level = int(self.xml.attrib['level'])
        if self.level not in aif.constants.MDADM_SUPPORTED_LEVELS:
            _logger.error(('RAID level ({0}) must be one of: '
                           '{1}.').format(self.level,
                                          ', '.join([str(i) for i in aif.constants.MDADM_SUPPORTED_LEVELS])))
            raise ValueError('Invalid RAID level')
        self.metadata = self.xml.attrib.get('meta', '1.2')
        if self.metadata not in aif.constants.MDADM_SUPPORTED_METADATA:
            _logger.error(('Metadata version ({0}) must be one of: '
                           '{1}.').format(self.metadata, ', '.join(aif.constants.MDADM_SUPPORTED_METADATA)))
            raise ValueError('Invalid metadata version')
        _common.addBDPlugin('mdraid')
        self.chunksize = int(self.xml.attrib.get('chunkSize', 512))
        if self.level in (4, 5, 6, 10):
            if not aif.utils.isPowerofTwo(self.chunksize):
                # TODO: warn instead of raise exception? Will mdadm lose its marbles if it *isn't* a proper number?
                _logger.error('Chunksize ({0}) must be a power of 2 for RAID level {1}.'.format(self.chunksize,
                                                                                                self.level))
                raise ValueError('Invalid chunksize')
        if self.level in (0, 4, 5, 6, 10):
            if not aif.utils.hasSafeChunks(self.chunksize):
                # TODO: warn instead of raise exception? Will mdadm lose its marbles if it *isn't* a proper number?
                _logger.error('Chunksize ({0}) must be divisible by 4 for RAID level {1}'.format(self.chunksize,
                                                                                                 self.level))
                raise ValueError('Invalid chunksize')
        self.layout = self.xml.attrib.get('layout', 'none')
        if self.level in aif.constants.MDADM_SUPPORTED_LAYOUTS.keys():
            matcher, layout_default = aif.constants.MDADM_SUPPORTED_LAYOUTS[self.level]
            if not matcher.search(self.layout):
                if layout_default:
                    self.layout = layout_default
                else:
                    _logger.warning('Did not detect a valid layout.')
                    self.layout = None
        else:
            self.layout = None
        self.name = self.xml.attrib['name']
        self.fullname = '{0}:{1}'.format(self.homehost, self.name)
        self.devpath = devpath
        if not self.devpath:
            self.devpath = '/dev/md/{0}'.format(self.name)
        self.updateStatus()
        self.homehost = homehost
        self.members = []
        self.state = None
        self.info = None

    def addMember(self, memberobj):
        if not isinstance(memberobj, Member):
            _logger.error('memberobj must be of type aif.disk.mdadm.Member.')
            raise TypeError('Invalid memberobj type')
        memberobj.prepare()
        self.members.append(memberobj)
        return(None)

    def create(self):
        if not self.members:
            _logger.error('Cannot create an array with no members.')
            raise RuntimeError('Missing members')
        opts = [_BlockDev.ExtraArg.new('--homehost',
                                       self.homehost),
                _BlockDev.ExtraArg.new('--name',
                                       self.name)]
        if self.layout:
            opts.append(_BlockDev.ExtraArg.new('--layout',
                                               self.layout))
        _BlockDev.md.create(self.name,
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
        return(None)

    def start(self, scan = False):
        _logger.info('Starting array {0}.'.format(self.name))
        if not any((self.members, self.devpath)):
            _logger.error('Cannot assemble an array with no members (for hints) or device path.')
            raise RuntimeError('Cannot start unspecified array')
        if scan:
            target = None
        else:
            target = self.name
        _BlockDev.md.activate(target,
                              [i.devpath for i in self.members],  # Ignored if scan mode enabled
                              None,
                              True,
                              None)
        self.state = 'assembled'
        return(None)

    def stop(self):
        _logger.error('Stopping aray {0}.'.format(self.name))
        _BlockDev.md.deactivate(self.name)
        self.state = 'disassembled'
        return(None)

    def updateStatus(self):
        _status = _BlockDev.md.detail(self.name)
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
        _logger.debug('Rendered info: {0}'.format(info))
        return(None)

    def writeConf(self, chroot_base):
        conf = os.path.join(chroot_base, 'etc', 'mdadm.conf')
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
                    # TODO: warning and skip instead?
                    _logger.error('An array already exists with that name but not with the same opts/GUID/etc.')
                    raise RuntimeError('Duplicate array')
            if nodev:
                with open(conf, 'a') as fh:
                    fh.write('{0}\n'.format(arrayinfo))
        return(None)
