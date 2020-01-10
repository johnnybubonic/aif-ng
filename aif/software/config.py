import copy
import logging
import os
import re
import shutil
from collections import OrderedDict
##
import jinja2
##
import aif.utils


_logger = logging.getLogger(__name__)


class PacmanConfig(object):
    _sct_re = re.compile(r'^\s*\[(?P<sect>[^]]+)\]\s*$')
    _kv_re = re.compile(r'^\s*(?P<key>[^\s=[]+)((?:\s*=\s*)(?P<value>.*))?$')
    _skipline_re = re.compile(r'^\s*(#.*)?$')
    # TODO: Append mirrors/repos to pacman.conf here before we parse?
    # I copy a log of logic from pycman/config.py here.
    _list_keys = ('CacheDir', 'HookDir', 'HoldPkg', 'SyncFirst', 'IgnoreGroup', 'IgnorePkg', 'NoExtract', 'NoUpgrade',
                  'Server')
    _single_keys = ('RootDir', 'DBPath', 'GPGDir', 'LogFile', 'Architecture', 'XferCommand', 'CleanMethod', 'SigLevel',
                    'LocalFileSigLevel', 'RemoteFileSigLevel')
    _noval_keys = ('UseSyslog', 'ShowSize', 'TotalDownload', 'CheckSpace', 'VerbosePkgLists', 'ILoveCandy', 'Color',
                   'DisableDownloadTimeout')
    # These are the default (commented-out) values in the stock /etc/pacman.conf as of January 5, 2020.
    defaults = OrderedDict({'options': {'Architecture': 'auto',
                                        'CacheDir': '/var/cache/pacman/pkg/',
                                        'CheckSpace': None,
                                        'CleanMethod': 'KeepInstalled',
                                        # 'Color': None,
                                        'DBPath': '/var/lib/pacman/',
                                        'GPGDir': '/etc/pacman.d/gnupg/',
                                        'HoldPkg': 'pacman glibc',
                                        'HookDir': '/etc/pacman.d/hooks/',
                                        'IgnoreGroup': [],
                                        'IgnorePkg': [],
                                        'LocalFileSigLevel': ['Optional'],
                                        'LogFile': '/var/log/pacman.log',
                                        'NoExtract': [],
                                        'NoUpgrade': [],
                                        'RemoteFileSigLevel': ['Required'],
                                        'RootDir': '/',
                                        'SigLevel': ['Required', 'DatabaseOptional'],
                                        # 'TotalDownload': None,
                                        # 'UseSyslog': None,
                                        # 'VerbosePkgLists': None,
                                        'XferCommand': '/usr/bin/curl -L -C - -f -o %o %u'},
                            # These should be explicitly included in the AIF config.
                            # 'core': {'Include': '/etc/pacman.d/mirrorlist'},
                            # 'extra': {'Include': '/etc/pacman.d/mirrorlist'},
                            # 'community': {'Include': '/etc/pacman.d/mirrorlist'}
                            })

    def __init__(self, chroot_base, confpath = '/etc/pacman.conf'):
        self.chroot_base = chroot_base
        self.confpath = os.path.join(self.chroot_base, re.sub(r'^/+', '', confpath))
        self.confbak = '{0}.bak'.format(self.confpath)
        self.mirrorlstpath = os.path.join(self.chroot_base, 'etc', 'pacman.d', 'mirrorlist')
        self.mirrorlstbak = '{0}.bak'.format(self.mirrorlstpath)
        if not os.path.isfile(self.confbak):
            shutil.copy2(self.confpath, self.confbak)
            _logger.info('Copied: {0} => {1}'.format(self.confpath, self.confbak))
        if not os.path.isfile(self.mirrorlstbak):
            shutil.copy2(self.mirrorlstpath, self.mirrorlstbak)
            _logger.info('Copied: {0} => {1}'.format(self.mirrorlstpath, self.mirrorlstbak))
        self.j2_env = jinja2.Environment(loader = jinja2.FileSystemLoader(searchpath = './'))
        self.j2_env.filters.update(aif.utils.j2_filters)
        self.j2_conf = self.j2_env.get_template('pacman.conf.j2')
        self.j2_mirror = self.j2_env.get_template('mirrorlist.j2')
        self.conf = None
        self.mirrors = []

    def _includeExpander(self, lines):
        curlines = []
        for line in lines:
            r = self._kv_re.search(line)
            if r and (r.group('key') == 'Include') and r.group('value'):
                path = os.path.join(self.chroot_base, re.sub(r'^/?', '', r.group('path')))
                with open(path, 'r') as fh:
                    curlines.extend(self._includeExpander(fh.read().splitlines()))
            else:
                curlines.append(line)
        return(curlines)

    def parse(self, defaults = True):
        self.conf = OrderedDict()
        rawlines = {}
        with open(self.confpath, 'r') as fh:
            rawlines['orig'] = [line for line in fh.read().splitlines() if not self._skipline_re.search(line)]
        rawlines['parsed'] = self._includeExpander(rawlines['orig'])
        for conftype, cfg in rawlines.items():
            _confdict = copy.deepcopy(self.defaults)
            _sect = None
            for line in cfg:
                if self._sct_re.search(line):
                    _sect = self._sct_re.search(line).group('sect')
                    if _sect not in _confdict.keys():
                        _confdict[_sect] = OrderedDict()
                elif self._kv_re.search(line):
                    r = self._kv_re.search(line)
                    k = r.group('key')
                    v = r.group('value')
                    if k in self._noval_keys:
                        _confdict[_sect][k] = None
                    elif k in self._single_keys:
                        _confdict[_sect][k] = v
                    elif k in self._list_keys:
                        if k not in _confdict[_sect].keys():
                            _confdict[_sect][k] = []
                        _confdict[_sect][k].append(v)
            if _confdict['options']['Architecture'] == 'auto':
                _confdict['options']['Architecture'] = os.uname().machine
            self.conf[conftype] = copy.deepcopy(_confdict)
        return(None)

    def writeConf(self):
        with open(self.confpath, 'w') as fh:
            fh.write(self.j2_conf.render(cfg = self.conf))
        with open(self.mirrorlstpath, 'w') as fh:
            fh.write(self.j2_mirror.render(mirrors = self.mirrors))
        return(None)
