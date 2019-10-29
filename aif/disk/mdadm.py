import copy
import math
import re
import subprocess
##
import mdstat
##
from aif.disk.block import Disk
from aif.disk.block import Partition


SUPPORTED_LEVELS = (0, 1, 4, 5, 6)
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

    def prepare(self):
        # TODO: logging
        subprocess.run(['mdadm', '--misc', '--zero-superblock', self.devpath])
        return()

class Array(object):
    def __init__(self, array_xml, homehost):
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
        self.devpath = '/dev/md/{0}'.format(self.devname)
        self.updateStatus()
        self.members = []
        self.state = None

    def addMember(self, memberobj):
        if not isinstance(memberobj, Member):
            raise ValueError('memberobj must be of type aif.disk.mdadm.Member')
        memberobj.prepare()
        self.members.append(memberobj)
        return()

    def assemble(self, scan = False):
        cmd = ['mdadm', '--assemble', self.devpath]
        if not scan:
            for m in self.members:
                cmd.append(m.devpath)
        else:
            cmd.extend([''])
        # TODO: logging!
        subprocess.run(cmd)

        pass
        return()

    def create(self):
        if not self.members:
            raise RuntimeError('Cannot create an array with no members')
        cmd = ['mdadm', '--create',
               '--level={0}'.format(self.level),
               '--metadata={0}'.format(self.metadata),
               '--chunk={0}'.format(self.chunksize),
               '--raid-devices={0}'.format(len(self.members))]
        if self.layout:
            cmd.append('--layout={0}'.format(self.layout))
        cmd.append(self.devpath)
        for m in self.members:
            cmd.append(m.devpath)
        # TODO: logging!
        subprocess.run(cmd)

        pass
        return()

    def stop(self):
        # TODO: logging
        subprocess.run(['mdadm', '--stop', self.devpath])
        return()

    def updateStatus(self):
        _info = mdstat.parse()
        for k, v in _info['devices'].items():
            if k != self.devname:
                del(_info['devices'][k])
        self.info = copy.deepcopy(_info)
        return()

    def writeConf(self, conf = '/etc/mdadm.conf'):
        pass
