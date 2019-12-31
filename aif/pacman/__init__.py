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


_logger = logging.getLogger(__name__)


class Mirror(object):
    def __init__(self, mirror_xml):
        self.xml = mirror_xml
        _logger.debug('mirror_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.uri = self.xml.text


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
        self.config = None
        self.handler = None
        self.repos = []
        self.packages = []
        self.mirrorlist = []
        # We need to run this twice; first to get some defaults.
        self._parseConf()
        self._initMirrors()
        self._initRepos()
        self._appendConf()
        self._parseConf()

    def _initMirrors(self):
        mirrors = self.xml.find('mirrorList')
        if mirrors is not None:
            for m in mirrors.findall('mirror'):
                mirror = Mirror(m)
                self.mirrorlist.append(mirror)
        return(None)

    def _initRepos(self):
        repos = self.xml.find('repos')
        for r in repos.findall('repo'):
            repo = Repo(r)
            self.repos.append(repo)
        return(None)

    def _parseConf(self):
        # TODO: Append mirrors/repos to pacman.conf here before we parse?
        with open(self.configfile, 'r') as fh:
            _cf = '\n'.join([i for i in fh.read().splitlines() if i.strip() != ''])
        self.config = configparser.ConfigParser(allow_no_value = True,
                                                interpolation = None,
                                                strict = False,
                                                dict_type = _common.MultiOrderedDict)
        self.config.optionxform = str
        self.config.read_string(_cf)
        self.opts = {'Architecture': 'auto',
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
        _opts = dict(self.config.items('options'))
        self.config.
        for k in ('CheckSpace', 'Color', 'TotalDownload', 'UseSyslog', 'VerbosePkgLists'):
            if k in _opts.keys():
                _opts[k] = True
            else:
                _opts[k] = False
        self.opts.update(_opts)
        self.config.remove_section('options')
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
        # These are the bare minimum that come enabled.
        for repo in self.config.sections():
            # TODO: figure out what the heck to do with the SigLevels
            self.handler.register_syncdb(repo, 0)
            self.config.get(repo, )

        return(None)


class Repo(object):
    def __init__(self, repo_xml):
        # TODO: support Usage? ("REPOSITORY SECTIONS", pacman.conf(5))
        self.xml = repo_xml
        _logger.debug('repo_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        _siglevelmap = {'default': }
        self.name = self.xml.attrib['name']
        self.uri = self.xml.attrib['mirror']  # "server" in pyalpm lingo.
        self.enabled = (True if self.xml.attrib.get('enabled', 'true') in ('1', 'true') else False)
        _sigs = 0
        for siglevel in self.xml.attrib['sigLevel'].split():
            sl = _siglevelmap[siglevel]
