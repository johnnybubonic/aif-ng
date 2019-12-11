import os
import subprocess
##
import psutil
##
import aif.disk.block_fallback as block
import aif.disk.luks_fallback as luks
import aif.disk.lvm_fallback as lvm
import aif.disk.mdadm_fallback as mdadm
import aif.utils


FS_FSTYPES = aif.utils.kernelFilesystems()


class FS(object):
    def __init__(self, fs_xml, sourceobj):
        self.xml = fs_xml
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
        self.id = self.xml.attrib['id']
        self.source = sourceobj
        self.devpath = sourceobj.devpath
        self.formatted = False
        self.fstype = self.xml.attrib.get('type')

    def format(self):
        if self.formatted:
            return ()
        # This is a safeguard. We do *not* want to high-format a disk that is mounted.
        aif.utils.checkMounted(self.devpath)
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
    def __init__(self, mount_xml, fsobj):
        self.xml = mount_xml
        self.id = self.xml.attrib['id']
        if not isinstance(fsobj, FS):
            raise ValueError('partobj must be of type aif.disk.filesystem.FS')
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
        # TODO: logging
        cmd = ['/usr/bin/mount',
               '--types', self.fs.fstype]
        if opts:
            cmd.extend(['--options', ','.join(opts)])
        cmd.extend([self.source, self.target])
        subprocess.run(cmd)
        self.mounted = True
        return(None)

    def unmount(self, lazy = False, force = False):
        self.updateMount()
        if not self.mounted and not force:
            return(None)
        # TODO: logging
        cmd = ['/usr/bin/umount']
        if lazy:
            cmd.append('--lazy')
        if force:
            cmd.append('--force')
        cmd.append(self.target)
        subprocess.run(cmd)
        self.mounted = False
        return(None)

    def updateMount(self):
        if self.source in [p.device for p in psutil.disk_partitions(all = True)]:
            self.mounted = True
        else:
            self.mounted = False
        return(None)
