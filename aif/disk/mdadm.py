import copy
import subprocess
##
import mdstat
##
from aif.disk.block import Disk
from aif.disk.block import Partition


SUPPORTED_LEVELS = (0, 1, 4, 5, 6)

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
    def __init__(self, array_xml):
        self.xml = array_xml
        self.id = array_xml.attrib['id']
        self.level = int(array_xml.attrib['level'])
        if self.level not in SUPPORTED_LEVELS:
            raise ValueError('RAID level must be one of: {0}'.format(', '.join(SUPPORTED_LEVELS)))
        self.devname = self.xml.attrib['name']
        self.devpath = '/dev/md/{0}'.format(self.devname)
        self.updateStatus()
        self.members = []

    def addMember(self, memberobj):
        if not isinstance(memberobj, Member):
            raise ValueError('memberobj must be of type aif.disk.mdadm.Member')

    def assemble(self):
        cmd = ['mdadm', '--assemble', self.devpath]
        for m in self.members:
            cmd.append(m.devpath)
        subprocess.run(cmd)

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
