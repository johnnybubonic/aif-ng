import copy
import datetime
import math
import re
import subprocess
import uuid
##
import mdstat
##
from aif.disk.block import Disk, Partition
from aif.disk.luks import LUKS
from aif.disk.lvm import LV


SUPPORTED_LEVELS = (0, 1, 4, 5, 6, 10)
SUPPORTED_METADATA = ('0', '0.90', '1', '1.0', '1.1', '1.2', 'default', 'ddf', 'imsm')
SUPPORTED_LAYOUTS = {5: (re.compile(r'^((left|right)-a?symmetric|[lr][as]|'
                                    r'parity-(fir|la)st|'
                                    r'ddf-(N|zero)-restart|ddf-N-continue)$'),
                         'left-symmetric'),
                     6: (re.compile(r'^((left|right)-a?symmetric(-6)?|[lr][as]|'
                                    r'parity-(fir|la)st|'
                                    r'ddf-(N|zero)-restart|ddf-N-continue|'
                                    r'parity-first-6)$'),
                         None),
                     10: (re.compile(r'^[nof][0-9]+$'),
                          None)}

_mdblock_size_re = re.compile(r'^(?P<sectors>[0-9]+)\s+'
                              r'\((?P<GiB>[0-9.]+)\s+GiB\s+'
                              r'(?P<GB>[0-9.]+)\s+GB\)')
_mdblock_unused_re = re.compile(r'^before=(?P<before>[0-9]+)\s+sectors,'
                                r'\s+after=(?P<after>[0-9]+)\s+sectors$')
_mdblock_badblock_re = re.compile(r'^(?P<entries>[0-9]+)\s+entries'
                                  r'[A-Za-z\s]+'
                                  r'(?P<offset>[0-9]+)\s+sectors$')

def _itTakesTwo(n):
    # So dumb.
    isPowerOf2 = math.ceil(math.log(n, 2)) == math.floor(math.log(n, 2))
    return(isPowerOf2)

def _safeChunks(n):
    if (n % 4) != 0:
        return(False)
    return(True)


class Member(object):
    def __init__(self, member_xml, partobj):
        self.xml = member_xml
        self.device = partobj
        if not isinstance(self.device, (Partition, Disk, Array)):
            raise ValueError(('partobj must be of type aif.disk.block.Partition, '
                              'aif.disk.block.Disk, or aif.disk.mdadm.Array'))
        self.devpath = self.device.devpath
        self.is_superblocked = None
        self.superblock = None
        self._parseDeviceBlock()

    def _parseDeviceBlock(self):
        # I can't believe the mdstat module doesn't really have a way to do this.
        super = subprocess.run(['mdadm', '--examine', self.devpath],
                               stdout = subprocess.PIPE,
                               stderr = subprocess.PIPE)
        if super.returncode != 0:
            # TODO: logging?
            self.is_superblocked = False
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
                v = re.sub(r'^raid', '', v)
            elif k == 'checksum':
                cksum, status = [i.strip() for i in v.split('-')]
                v = (bytes.fromhex(cksum), status)
            elif k == 'unused_space':
                r = _mdblock_unused_re.search(v)
                if not r:
                    raise ValueError(('Could not parse {0} for '
                                      '{1}\'s superblock').format(orig_k,
                                                                  self.devpath))
                v = {}
                for i in ('before', 'after'):
                    v[i] = int(r.group(i))  # in sectors
            elif k == 'bad_block_log':
                k = 'badblock_log_entries'
                r = _mdblock_badblock_re.search(v)
                if not r:
                    raise ValueError(('Could not parse {0} for '
                                      '{1}\'s superblock').format(orig_k,
                                                                  self.devpath))
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
                    raise ValueError(('Could not parse {0} for '
                                      '{1}\'s superblock').format(orig_k,
                                                                  self.devpath))
                v = {}
                for i in ('sectors', 'GB', 'GiB'):
                    v[i] = float(r.group(i))
                    if i == 'sectors':
                        v[i] = int(v[i])
            elif re.search(r'^(data|super)_offset$', k):
                v = int(v.split(None, 1)[0])
            block[k] = v
        self.superblock = block
        self.is_superblocked = True
        return()

    def prepare(self):
        if self.is_superblocked:
            # TODO: logging
            subprocess.run(['mdadm', '--misc', '--zero-superblock', self.devpath])
            self.is_superblocked = False
        return()

class Array(object):
    def __init__(self, array_xml, homehost, devpath = None):
        self.xml = array_xml
        self.id = array_xml.attrib['id']
        self.level = int(self.xml.attrib['level'])
        if self.level not in SUPPORTED_LEVELS:
            raise ValueError('RAID level must be one of: {0}'.format(', '.join([str(i) for i in SUPPORTED_LEVELS])))
        self.metadata = self.xml.attrib.get('meta', '1.2')
        if self.metadata not in SUPPORTED_METADATA:
            raise ValueError('Metadata version must be one of: {0}'.format(', '.join(SUPPORTED_METADATA)))
        self.chunksize = int(self.xml.attrib.get('chunkSize', 512))
        if self.level in (4, 5, 6, 10):
            if not _itTakesTwo(self.chunksize):
                # TODO: log.warn instead of raise exception? Will mdadm lose its marbles if it *isn't* a proper number?
                raise ValueError('chunksize must be a power of 2 for the RAID level you specified')
        if self.level in (0, 4, 5, 6, 10):
            if not _safeChunks(self.chunksize):
                # TODO: log.warn instead of raise exception? Will mdadm lose its marbles if it *isn't* a proper number?
                raise ValueError('chunksize must be divisible by 4 for the RAID level you specified')
        self.layout = self.xml.attrib.get('layout', 'none')
        if self.level in SUPPORTED_LAYOUTS.keys():
            matcher, layout_default = SUPPORTED_LAYOUTS[self.level]
            if not matcher.search(self.layout):
                if layout_default:
                    self.layout = layout_default
                else:
                    self.layout = None  # TODO: log.warn?
        else:
            self.layout = None
        self.devname = self.xml.attrib['name']
        self.devpath = devpath
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

    def start(self, scan = False):
        if not any((self.members, self.devpath)):
            raise RuntimeError('Cannot assemble an array with no members (for hints) or device path')
        cmd = ['mdadm', '--assemble', self.devpath]
        if not scan:
            for m in self.members:
                cmd.append(m.devpath)
        else:
            cmd.append('--scan')
        # TODO: logging!
        subprocess.run(cmd)
        self.state = 'assembled'
        return()

    def create(self):
        if not self.members:
            raise RuntimeError('Cannot create an array with no members')
        cmd = ['mdadm', '--create',
               '--level={0}'.format(self.level),
               '--metadata={0}'.format(self.metadata),
               '--chunk={0}'.format(self.chunksize),
               '--homehost={0}'.format(self.homehost),
               '--raid-devices={0}'.format(len(self.members))]
        if self.layout:
            cmd.append('--layout={0}'.format(self.layout))
        cmd.append(self.devpath)
        for m in self.members:
            cmd.append(m.devpath)
        # TODO: logging!
        subprocess.run(cmd)
        self.writeConf()
        self.state = 'new'
        return()

    def stop(self):
        # TODO: logging
        subprocess.run(['mdadm', '--stop', self.devpath])
        self.state = 'disassembled'
        return()

    def updateStatus(self):
        _info = mdstat.parse()
        for k, v in _info['devices'].items():
            if k != self.devname:
                del(_info['devices'][k])
        self.info = copy.deepcopy(_info)
        return()

    def writeConf(self, conf = '/etc/mdadm.conf'):
        with open(conf, 'r') as fh:
            conflines = fh.read().splitlines()
        # TODO: logging
        arrayinfo = subprocess.run(['mdadm', '--detail', '--brief', self.devpath],
                                   stdout = subprocess.PIPE).stdout.decode('utf-8').strip()
        if arrayinfo not in conflines:
            r = re.compile(r'^ARRAY\s+{0}'.format(self.devpath))
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
