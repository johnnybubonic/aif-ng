# We can manually bootstrap and alter pacman's keyring. But check the bootstrap tarball; we might not need to.
# TODO.

import configparser
import logging
import os
import re
##
import pyalpm
import gpg
from lxml import etree
##
from . import _common
from . import keyring


_logger = logging.getLogger(__name__)


# TODO: There is some duplication here that we can get rid of in the future. Namely:
#       - Mirror URI parsing
#       - Unified function for parsing Includes
#       - At some point, ideally there should be a MirrorList class that can take (or generate?) a list of Mirrors
#         and have a write function to write out a mirror list to a specified location.


class Mirror(object):
    def __init__(self, mirror_xml, repo = None, arch = None):
        self.xml = mirror_xml
        _logger.debug('mirror_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.uri = self.xml.text
        self.real_uri = None
        self.aif_uri = None

    def parse(self, chroot_base, repo, arch):
        self.real_uri = self.uri.replace('$repo', repo).replace('$arch', arch)
        if self.uri.startswith('file://'):
            self.aif_uri = os.path.join(chroot_base, re.sub(r'^file:///?', ''))


class Package(object):
    def __init__(self, package_xml):
        self.xml = package_xml
        _logger.debug('package_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.name = self.xml.text
        self.repo = self.xml.attrib.get('repo')
        if self.repo:
            self.qualified_name = '{0}/{1}'.format(self.repo, self.name)
        else:
            self.qualified_name = self.name


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
                    mirror = Mirror(m)
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
                repo = Repo(self.chroot_base, r)
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


class Repo(object):
    def __init__(self, chroot_base, repo_xml, arch = 'x86_64'):
        # TODO: support Usage? ("REPOSITORY SECTIONS", pacman.conf(5))
        self.xml = repo_xml
        _logger.debug('repo_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        # TODO: SigLevels?!
        self.name = self.xml.attrib['name']
        self.mirrors = {}
        self.parsed_mirrors = []
        _mirrors = self.xml.xpath('mirror|include')  # "Server" and "Include" respectively in pyalpm lingo.
        if _mirrors:
            for m in _mirrors:
                k = m.tag.title()
                if k == 'Mirror':
                    k = 'Server'
                if k not in self.mirrors.keys():
                    self.mirrors[k] = []
                self.mirrors[k].append(m.text)
                if m.tag == 'include':
                    file_uri = os.path.join(chroot_base, re.sub(r'^file:///?', '', m.text))
                    if not os.path.isfile(file_uri):
                        _logger.error('Include file ({0}) does not exist: {1}'.format(m.text, file_uri))
                        raise FileNotFoundError('Include file does not exist')
                    with open(file_uri, 'r') as fh:
                        for line in fh.read().splitlines():
        else:
            # Default (mirrorlist)
            self.mirrors['Include'] = ['file:///etc/pacman.d/mirrorlist']
        self.enabled = (True if self.xml.attrib.get('enabled', 'true') in ('1', 'true') else False)
        self.siglevel = self.xml.attrib.get('sigLevel')
        self.real_uri = None
        if self.uri:
            self.real_uri = self.uri.replace('$repo', self.name).replace('$arch', arch)
