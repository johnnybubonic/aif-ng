import os
import re
import subprocess
##
import psutil
##
from aif.disk.block import Partition
from aif.disk.luks import LUKS
from aif.disk.lvm import Group as LVMGroup
from aif.disk.mdadm import Array as MDArray

# I wish there was a better way of doing this.
# https://unix.stackexchange.com/a/98680
FS_FSTYPES = []
with open('/proc/filesystems', 'r') as fh:
    for line in fh.readlines():
        l = [i.strip() for i in line.split()]
        if not l:
            continue
        if len(l) == 1:
            FS_FSTYPES.append(l[0])
        else:
            FS_FSTYPES.append(l[1])
_mod_dir = os.path.join('/lib/modules',
                        os.uname().release,
                        'kernel/fs')
_strip_mod_suffix = re.compile(r'(?P<fsname>)\.ko(\.(x|g)?z)?$', re.IGNORECASE)
for i in os.listdir(_mod_dir):
    path = os.path.join(_mod_dir, i)
    fs_name = None
    if os.path.isdir(path):
        fs_name = i
    elif os.path.isfile(path):
        mod_name = _strip_mod_suffix.search(i)
        fs_name = mod_name.group('fsname')
    if fs_name:
        # The kernel *probably* has autoloading enabled, but in case it doesn't...
        # TODO: logging!
        subprocess.run(['modprobe', fs_name])
        FS_FSTYPES.append(fs_name)


class FS(object):
    def __init__(self, fs_xml, sourceobj):
        self.xml = fs_xml
        if not isinstance(sourceobj, (Partition, LUKS, LVMGroup, MDArray)):
            raise ValueError(('sourceobj must be of type '
                              'aif.disk.block.Partition, '
                              'aif.disk.luks.LUKS, '
                              'aif.disk.lvm.Group, or'
                              'aif.disk.mdadm.Array'))
        self.source = sourceobj
        self.devpath = sourceobj.devpath
        self.formatted = False
        self.fstype = self.xml.attrib.get('type')

    def format(self):
        if self.formatted:
            return ()
        # This is a safeguard. We do *not* want to high-format a disk that is mounted.
        for p in psutil.disk_partitions(all = True):
            if self.devpath in p:
                raise RuntimeError(('{0} is mounted;'
                                    'we are cowardly refusing to apply a filesystem to it').format(self.devpath))
        # TODO! Logging
        cmd = ['mkfs',
               '-t', self.fstype]
        for o in self.xml.findall('opt'):
            cmd.append(o.attrib['name'])
            if o.text:
                cmd.append(o.text)
        cmd.append(self.devpath)
        subprocess.run(cmd)
        self.is_hiformatted = True
        return()
