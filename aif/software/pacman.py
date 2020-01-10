# We can manually bootstrap and alter pacman's keyring. But check the bootstrap tarball; we might not need to.
# TODO.

import logging
import os
import re
##
import pyalpm
from lxml import etree
##
from . import keyring
from . import objtypes

_logger = logging.getLogger(__name__)


# TODO: There is some duplication here that we can get rid of in the future. Namely:
#       - Mirror URI parsing
#       - Unified function for parsing Includes
#       - At some point, ideally there should be a MirrorList class that can take (or generate?) a list of Mirrors
#         and have a write function to write out a mirror list to a specified location.


class PackageManager(object):
    def __init__(self, chroot_base, pacman_xml):
        self.xml = pacman_xml
        _logger.debug('pacman_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.chroot_base = chroot_base
        self.pacman_dir = os.path.join(self.chroot_base, 'var', 'lib', 'pacman')
        self.configfile = os.path.join(self.chroot_base, 'etc', 'pacman.conf')
        self.keyring = keyring.PacmanKey(self.chroot_base)
        self.config = None
        self.handler = None
        self.repos = []
        self.packages = []
        self.mirrorlist = []
        self._initHandler()
        self._initMirrors()
        self._initRepos()

    def _initHandler(self):
        # TODO: Append mirrors/repos to pacman.conf here before we parse?
        self.opts = {'Architecture': 'x86_64',  # Technically, "auto" but Arch proper only supports x86_64.
                     'CacheDir': '/var/cache/pacman/pkg/',
                     'CheckSpace': True,
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
        for k, v in self.opts.items():
            if k in ('CacheDir', 'DBPath', 'GPGDir', 'HookDir', 'LogFile', 'RootDir'):
                v = re.sub(r'^/+', r'', v)
                self.opts[k] = os.path.join(self.chroot_base, v)
            if k in ('HoldPkg', 'IgnoreGroup', 'IgnorePkg', 'NoExtract', 'NoUpgrade', 'SigLevel'):
                v = v.split()
        if not self.handler:
            self.handler = pyalpm.Handle(self.chroot_base, self.pacman_dir)
        # Pretty much blatantly ripped this off of pycman:
        # https://github.com/archlinux/pyalpm/blob/master/pycman/config.py
        for k in ('LogFile', 'GPGDir', 'NoExtract', 'NoUpgrade'):
            setattr(self.handler, k.lower(), self.opts[k])
        self.handler.arch = self.opts['Architecture']
        if self.opts['IgnoreGroup']:
            self.handler.ignoregrps = self.opts['IgnoreGroup']
        if self.opts['IgnorePkg']:
            self.handler.ignorepkgs = self.opts['IgnorePkg']
        return(None)

    def _initMirrors(self):
        mirrors = self.xml.find('mirrorList')
        if mirrors:
            _mirrorlist = os.path.join(self.chroot_base, 'etc', 'pacman.d', 'mirrorlist')
            with open(_mirrorlist, 'a') as fh:
                fh.write('\n# Added by AIF-NG.\n')
                for m in mirrors.findall('mirror'):
                    mirror = objtypes.Mirror(m)
                    self.mirrorlist.append(mirror)
                    fh.write('Server = {0}\n'.format(mirror.uri))
            _logger.info('Appended: {0}'.format(_mirrorlist))
        return(None)

    def _initRepos(self):
        repos = self.xml.find('repos')
        _conf = os.path.join(self.chroot_base, 'etc', 'pacman.conf')
        with open(_conf, 'a') as fh:
            fh.write('\n# Added by AIF-NG.\n')
            for r in repos.findall('repo'):
                repo = objtypes.Repo(self.chroot_base, r)
                if repo.enabled:
                    fh.write('[{0}]\n'.format(repo.name))
                    if repo.siglevel:
                        fh.write('SigLevel = {0}\n'.format(repo.siglevel))
                    if repo.uri:
                        fh.write('Server = {0}\n'.format(repo.uri))
                    else:
                        fh.write('Include = /etc/pacman.d/mirrorlist\n')
                else:
                    fh.write('#[{0}]\n'.format(repo.name))
                    if repo.siglevel:
                        fh.write('#SigLevel = {0}\n'.format(repo.siglevel))
                    if repo.uri:
                        fh.write('#Server = {0}\n'.format(repo.uri))
                    else:
                        fh.write('#Include = /etc/pacman.d/mirrorlist\n')
                self.repos.append(repo)
        _logger.info('Appended: {0}'.format(_conf))
        return(None)
