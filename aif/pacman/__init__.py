# We can manually bootstrap and alter pacman's keyring. But check the bootstrap tarball; we might not need to.
# TODO.

import configparser
import logging
import os
import re
##
import pyalpm
import gpg
##
from . import _common


_logger = logging.getLogger(__name__)


_skipconfline_re = re.compile(r'^[ \t]*#([ \t]+.*)?$')


class PackageManager(object):
    def __init__(self, chroot_base):
        self.chroot_base = chroot_base
        self.pacman_dir = os.path.join(self.chroot_base, 'var', 'lib', 'pacman')
        self.configfile = os.path.join(self.chroot_base, 'etc', 'pacman.conf')
        self.config = None
        self._parseConf()

    def _parseConf(self):
        _cf = []
        with open(self.configfile, 'r') as fh:
            for line in fh.read().splitlines():
                if _skipconfline_re.search(line) or line.strip() == '':
                    continue
                _cf.append(re.sub(r'^#', '', line))
        self.config = configparser.ConfigParser(allow_no_value = True,
                                                interpolation = None,
                                                strict = False,
                                                dict_type = _common.MultiOrderedDict)
        self.config.optionxform = str
        self.config.read_string('\n'.join(_cf))
        self.opts = {'Architecture': 'auto',
                     'CacheDir': '/var/cache/pacman/pkg/',
                     'CheckSpace': None,
                     'CleanMethod': 'KeepInstalled',
                     # 'Color': None,
                     'DBPath': '/var/lib/pacman/',
                     'GPGDir': '/etc/pacman.d/gnupg/',
                     'HoldPkg': 'pacman glibc',
                     'HookDir': '/etc/pacman.d/hooks/',
                     'IgnoreGroup': '',
                     'IgnorePkg': '',
                     'LocalFileSigLevel': 'Optional',
                     'LogFile': '/var/log/pacman.log',
                     'NoExtract': '',
                     'NoUpgrade': '',
                     'RemoteFileSigLevel': 'Required',
                     'RootDir': '/',
                     'SigLevel': 'Required DatabaseOptional',
                     # 'TotalDownload': None,
                     # 'UseSyslog': None,
                     # 'VerbosePkgLists': None,
                     'XferCommand': '/usr/bin/curl -L -C - -f -o %o %u'
                     }
        self.distro_repos = ['']
        _opts = dict(self.config.items('options'))
        self.opts.update(_opts)
        self.config.remove_section('options')
