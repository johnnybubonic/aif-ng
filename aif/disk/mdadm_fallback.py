import copy
import datetime
import logging
import os
import re
import subprocess
import uuid
##
import mdstat
from lxml import etree
##
import aif.disk.block_fallback as block
import aif.disk.luks_fallback as luks
import aif.disk.lvm_fallback as lvm
import aif.utils
import aif.constants


_logger = logging.getLogger(__name__)


_mdblock_size_re = re.compile(r'^(?P<sectors>[0-9]+)\s+'
                              r'\((?P<GiB>[0-9.]+)\s+GiB\s+'
                              r'(?P<GB>[0-9.]+)\s+GB\)')
_mdblock_unused_re = re.compile(r'^before=(?P<before>[0-9]+)\s+sectors,'
                                r'\s+after=(?P<after>[0-9]+)\s+sectors$')
_mdblock_badblock_re = re.compile(r'^(?P<entries>[0-9]+)\s+entries'
                                  r'[A-Za-z\s]+'
                                  r'(?P<offset>[0-9]+)\s+sectors$')


class Member(object):
    def __init__(self, member_xml, partobj):
        self.xml = member_xml
        _logger.debug('member_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.device = partobj
        if not isinstance(self.device, (block.Partition,
                                        block.Disk,
                                        Array,
                                        lvm.LV,
                                        luks.LUKS)):
            _logger.error(('partobj must be of type '
                           'aif.disk.block.Partition, '
                           'aif.disk.block.Disk, or '
                           'aif.disk.mdadm.Array'))
            raise TypeError('Invalid partobj type')
        self.devpath = self.device.devpath
        self.is_superblocked = None
        self.superblock = None
        self._parseDeviceBlock()

    def _parseDeviceBlock(self):
        # I can't believe the mdstat module doesn't really have a way to do this.
        _super = subprocess.run(['mdadm', '--examine', self.devpath],
                                stdout = subprocess.PIPE,
                                stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(_super.args)))
        if _super.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(_super.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(_super, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            self.is_superblocked = False
            self.superblock = None
            return(None)
        block = {}
        for idx, line in enumerate(super.stdout.decode('utf-8').splitlines()):
            line = line.strip()
            if idx == 0:  # This is just the same as self.device.devpath.
                continue
            if line == '':
                continue
            k, v = [i.strip() for i in line.split(':', 1)]
            orig_k = k
            k = re.sub(r'\s+', '_', k.lower())
            if k in ('raid_devices', 'events'):
                v = int(v)
            elif k == 'magic':
                v = bytes.fromhex(v)
            elif k == 'name':
                # TODO: Will this *always* give 2 values?
                name, local_to = [i.strip() for i in v.split(None, 1)]
                local_to = re.sub(r'[()]', '', local_to)
                v = (name, local_to)
            elif k == 'raid_level':
                v = int(re.sub(r'^raid', '', v))
            elif k == 'checksum':
                cksum, status = [i.strip() for i in v.split('-')]
                v = (bytes.fromhex(cksum), status)
            elif k == 'unused_space':
                r = _mdblock_unused_re.search(v)
                if not r:
                    _logger.error('Could not parse {0} for {1}\'s superblock'.format(orig_k, self.devpath))
                    raise RuntimeError('Could not parse unused space in superblock')
                v = {}
                for i in ('before', 'after'):
                    v[i] = int(r.group(i))  # in sectors
            elif k == 'bad_block_log':
                k = 'badblock_log_entries'
                r = _mdblock_badblock_re.search(v)
                if not r:
                    _logger.error('Could not parse {0} for {1}\'s superblock'.format(orig_k, self.devpath))
                    raise RuntimeError('Could not parse badblocks in superblock')
                v = {}
                for i in ('entries', 'offset'):
                    v[i] = int(r.group(i)) # offset is in sectors
            elif k == 'array_state':
                v = [i.strip() for i in v.split(None, 1)][0].split()
            elif k == 'device_uuid':
                v = uuid.UUID(hex = v.replace(':', '-'))
            elif re.search((r'^(creation|update)_time$'), k):
                # TODO: Is this portable/correct? Or do I need to do '%a %b %d %H:%M:%s %Y'?
                v = datetime.datetime.strptime(v, '%c')
            elif re.search(r'^((avail|used)_dev|array)_size$', k):
                r = _mdblock_size_re.search(v)
                if not r:
                    _logger.error('Could not parse {0} for {1}\'s superblock'.format(orig_k, self.devpath))
                    raise RuntimeError('Could not parse size value in superblock')
                v = {}
                for i in ('sectors', 'GB', 'GiB'):
                    v[i] = float(r.group(i))
                    if i == 'sectors':
                        v[i] = int(v[i])
            elif re.search(r'^(data|super)_offset$', k):
                v = int(v.split(None, 1)[0])
            block[k] = v
        self.superblock = block
        _logger.debug('Rendered superblock info: {0}'.format(block))
        self.is_superblocked = True
        return(None)

    def prepare(self):
        if self.is_superblocked:
            cmd = subprocess.run(['mdadm', '--misc', '--zero-superblock', self.devpath],
                                 stdout = subprocess.PIPE,
                                 stderr = subprocess.PIPE)
            _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
            if cmd.returncode != 0:
                _logger.warning('Command returned non-zero status')
                _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
                for a in ('stdout', 'stderr'):
                    x = getattr(cmd, a)
                    if x:
                        _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            self.is_superblocked = False
        self._parseDeviceBlock()
        return(None)


class Array(object):
    def __init__(self, array_xml, homehost, devpath = None):
        self.xml = array_xml
        _logger.debug('array_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.id = self.xml.attrib['id']
        self.level = int(self.xml.attrib['level'])
        if self.level not in aif.constants.MDADM_SUPPORTED_LEVELS:
            _logger.error(('RAID level ({0}) must be one of: '
                           '{1}').format(self.level, ', '.join([str(i) for i in aif.constants.MDADM_SUPPORTED_LEVELS])))
            raise ValueError('Invalid RAID level')
        self.metadata = self.xml.attrib.get('meta', '1.2')
        if self.metadata not in aif.constants.MDADM_SUPPORTED_METADATA:
            _logger.error(('Metadata version ({0}) must be one of: '
                           '{1}').format(self.metadata, ', '.join(aif.constants.MDADM_SUPPORTED_METADATA)))
            raise ValueError('Invalid metadata version')
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
            _logger.error('memberobj must be of type aif.disk.mdadm.Member')
            raise TypeError('Invalid memberobj type')
        memberobj.prepare()
        self.members.append(memberobj)
        return(None)

    def create(self):
        if not self.members:
            _logger.error('Cannot create an array with no members.')
            raise RuntimeError('Missing members')
        cmd_str = ['mdadm', '--create',
                   '--name={0}'.format(self.name),
                   '--bitmap=internal',
                   '--level={0}'.format(self.level),
                   '--metadata={0}'.format(self.metadata),
                   '--chunk={0}'.format(self.chunksize),
                   '--homehost={0}'.format(self.homehost),
                   '--raid-devices={0}'.format(len(self.members))]
        if self.layout:
            cmd_str.append('--layout={0}'.format(self.layout))
        cmd_str.append(self.devpath)
        for m in self.members:
            cmd_str.append(m.devpath)
        # TODO: logging!
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to create array successfully')
        for m in self.members:
            m._parseDeviceBlock()
        self.updateStatus()
        self.writeConf()
        self.state = 'new'
        return(None)

    def start(self, scan = False):
        _logger.info('Starting array {0}.'.format(self.name))
        if not any((self.members, self.devpath)):
            _logger.error('Cannot assemble an array with no members (for hints) or device path.')
            raise RuntimeError('Cannot start unspecified array')
        cmd_str = ['mdadm', '--assemble', self.devpath]
        if not scan:
            for m in self.members:
                cmd_str.append(m.devpath)
        else:
            cmd_str.append('--scan')
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to start array successfully')
        self.updateStatus()
        self.state = 'assembled'
        return(None)

    def stop(self):
        _logger.error('Stopping aray {0}.'.format(self.name))
        cmd = subprocess.run(['mdadm', '--stop', self.devpath],
                             stdout = subprocess.PIPE,
                             stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to stop array successfully')
        self.state = 'disassembled'
        return(None)

    def updateStatus(self):
        _info = mdstat.parse()
        for k, v in _info['devices'].items():
            if k != self.name:
                del(_info['devices'][k])
        self.info = copy.deepcopy(_info)
        _logger.debug('Rendered info: {0}'.format(_info))
        return(None)

    def writeConf(self, chroot_base):
        conf = os.path.join(chroot_base, 'etc', 'mdadm.conf')
        with open(conf, 'r') as fh:
            conflines = fh.read().splitlines()
        cmd = subprocess.run(['mdadm', '--detail', '--brief', self.devpath],
                             stdout = subprocess.PIPE,
                             stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to get information about array successfully')
        arrayinfo = cmd.stdout.decode('utf-8').strip()
        if arrayinfo not in conflines:
            r = re.compile(r'^ARRAY\s+{0}'.format(self.devpath))
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
