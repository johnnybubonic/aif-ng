import logging
import os
import subprocess
##
import psutil
from lxml import etree
##
import aif.disk.block as block
import aif.disk.luks as luks
import aif.disk.lvm as lvm
import aif.disk.mdadm as mdadm
import aif.utils
from . import _common


_BlockDev = _common.BlockDev
_logger = logging.getLogger(__name__)


FS_FSTYPES = aif.utils.kernelFilesystems()


class FS(object):
    def __init__(self, fs_xml, sourceobj):
        # http://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Filesystem.html#gdbus-interface-org-freedesktop-UDisks2-Filesystem.top_of_page
        # http://storaged.org/doc/udisks2-api/latest/ ?
        self.xml = fs_xml
        _logger.debug('fs_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.id = self.xml.attrib['id']
        if not isinstance(sourceobj, (block.Disk,
                                      block.Partition,
                                      luks.LUKS,
                                      lvm.LV,
                                      mdadm.Array)):
            _logger.error(('sourceobj must be of type '
                           'aif.disk.block.Partition, '
                           'aif.disk.luks.LUKS, '
                           'aif.disk.lvm.LV, or'
                           'aif.disk.mdadm.Array.'))
            raise TypeError('Invalid sourceobj type')
        self.source = sourceobj
        self.devpath = sourceobj.devpath
        self.formatted = False
        self.fstype = self.xml.attrib.get('type')
        if self.fstype not in FS_FSTYPES:
            _logger.error('{0} is not a supported filesystem type on this system.'.format(self.fstype))
            raise ValueError('Invalid filesystem type')

    def format(self):
        if self.formatted:
            return(None)
        # This is a safeguard. We do *not* want to high-format a disk that is mounted.
        aif.utils.checkMounted(self.devpath)
        # TODO: Can I format with DBus/gobject-introspection? I feel like I *should* be able to, but BlockDev's fs
        #  plugin is *way* too limited in terms of filesystems and UDisks doesn't let you format that high-level.
        _logger.info('Formatting {0}.'.format(self.devpath))
        cmd_str = ['mkfs',
                   '-t', self.fstype]
        for o in self.xml.findall('opt'):
            cmd_str.append(o.attrib['name'])
            if o.text:
                cmd_str.append(o.text)
        cmd_str.append(self.devpath)
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to format successfully')
        else:
            self.formatted = True
        return(None)


class Mount(object):
    # http://storaged.org/doc/udisks2-api/latest/gdbus-org.freedesktop.UDisks2.Filesystem.html#gdbus-method-org-freedesktop-UDisks2-Filesystem.Mount
    def __init__(self, mount_xml, fsobj):
        self.xml = mount_xml
        _logger.debug('mount_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        if not isinstance(fsobj, FS):
            _logger.error('partobj must be of type aif.disk.filesystem.FS.')
            raise TypeError('Invalid fsobj type')
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
        _logger.debug('Rendered mount opts: {0}'.format(opts))
        return(opts)

    def mount(self):
        if self.mounted:
            return(None)
        _logger.info('Mounting {0} at {1} as {2}.'.format(self.source, self.target, self.fs.fstype))
        os.makedirs(self.target, exist_ok = True)
        opts = self._parseOpts()
        _BlockDev.fs.mount(self.source,
                           self.target,
                           self.fs.fstype,
                           (','.join(opts) if opts else None))
        self.mounted = True
        _logger.debug('{0} mounted.'.format(self.source))
        return(None)

    def unmount(self, lazy = False, force = False):
        self.updateMount()
        if not self.mounted and not force:
            return(None)
        _logger.info('Unmounting {0}.'.format(self.target))
        _BlockDev.fs.unmount(self.target,
                             lazy,
                             force)
        self.mounted = False
        return(None)

    def updateMount(self):
        _logger.debug('Fetching mount status for {0}'.format(self.source))
        if self.source in [p.device for p in psutil.disk_partitions(all = True)]:
            self.mounted = True
        else:
            self.mounted = False
        return(None)
