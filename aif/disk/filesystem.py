import os
import subprocess
##
import psutil
##
import aif.disk.block as block
import aif.disk.luks as luks
import aif.disk.lvm as lvm
import aif.disk.mdadm as mdadm
import aif.utils
from . import _common

_BlockDev = _common.BlockDev


FS_FSTYPES = aif.utils.kernelFilesystems()


class FS(object):
    def __init__(self, fs_xml, sourceobj):
        # http://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Filesystem.html#gdbus-interface-org-freedesktop-UDisks2-Filesystem.top_of_page
        # http://storaged.org/doc/udisks2-api/latest/ ?
        self.xml = fs_xml
        self.id = self.xml.attrib['id']
        if not isinstance(sourceobj, (block.Disk,
                                      block.Partition,
                                      luks.LUKS,
                                      lvm.LV,
                                      mdadm.Array)):
            raise ValueError(('sourceobj must be of type '
                              'aif.disk.block.Partition, '
                              'aif.disk.luks.LUKS, '
                              'aif.disk.lvm.LV, or'
                              'aif.disk.mdadm.Array'))
        self.source = sourceobj
        self.devpath = sourceobj.devpath
        self.formatted = False
        self.fstype = self.xml.attrib.get('type')
        if self.fstype not in FS_FSTYPES:
            raise ValueError('{0} is not a supported filesystem type on this system'.format(self.fstype))

    def format(self):
        if self.formatted:
            return ()
        # This is a safeguard. We do *not* want to high-format a disk that is mounted.
        aif.utils.checkMounted(self.devpath)
        # TODO: Can I format with DBus/gobject-introspection? I feel like I *should* be able to, but BlockDev's fs
        #  plugin is *way* too limited in terms of filesystems and UDisks doesn't let you format that high-level.
        # TODO! Logging
        cmd = ['mkfs',
               '-t', self.fstype]
        for o in self.xml.findall('opt'):
            cmd.append(o.attrib['name'])
            if o.text:
                cmd.append(o.text)
        cmd.append(self.devpath)
        subprocess.run(cmd)
        self.formatted = True
        return(None)


class Mount(object):
    # http://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Filesystem.html#gdbus-method-org-freedesktop-UDisks2-Filesystem.Mount
    def __init__(self, mount_xml, fsobj):
        self.xml = mount_xml
        if not isinstance(fsobj, FS):
            raise ValueError('partobj must be of type aif.disk.filesystem.FS')
        _common.addBDPlugin('fs')  # We *could* use the UDisks dbus to mount too, but best to stay within libblockdev.
        self.id = self.xml.attrib['id']
        self.fs = fsobj
        self.source = self.fs.devpath
        self.target = os.path.realpath(self.xml.attrib['target'])
        self.opts = {}
        for o in self.xml.findall('opt'):
            self.opts[o.attrib['name']] = o.text
        self.mounted = False

    def _parseOpts(self):
        opts = []
        for k, v in self.opts.items():
            if v and v is not True:  # Python's boolean determination is weird sometimes.
                opts.append('{0}={1}'.format(k, v))
            else:
                opts.append(k)
        return(opts)

    def mount(self):
        if self.mounted:
            return(None)
        os.makedirs(self.target, exist_ok = True)
        opts = self._parseOpts()
        _BlockDev.fs.mount(self.source,
                           self.target,
                           self.fs.fstype,
                           (','.join(opts) if opts else None))
        self.mounted = True
        return(None)

    def unmount(self, lazy = False, force = False):
        self.updateMount()
        if not self.mounted and not force:
            return(None)
        _BlockDev.fs.unmount(self.target,
                             lazy,
                             force)
        self.mounted = False
        return(None)

    def updateMount(self):
        if self.source in [p.device for p in psutil.disk_partitions(all = True)]:
            self.mounted = True
        else:
            self.mounted = False
        return(None)
