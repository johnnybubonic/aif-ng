import re
##
import aif.utils
import aif.constants
from . import _common
import aif.disk.block as block
import aif.disk.luks as luks
import aif.disk.lvm as lvm


_BlockDev = _common.BlockDev


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
        self.devpath = self.device.devpath
        self.is_superblocked = None
        self.superblock = None
        self._parseDeviceBlock()

    def _parseDeviceBlock(self):
        pass

    def prepare(self):
        pass


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

    def addMember(self, memberobj):
        pass

    def create(self):
        pass

    def start(self, scan = False):
        pass

    def stop(self):
        pass

    def updateStatus(self):
        pass

    def writeConf(self):
        pass
