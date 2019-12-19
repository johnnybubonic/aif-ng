import logging
import math
import os
import pathlib
import re
import shlex
import subprocess
##
import psutil
##
from . import parser
from . import file_handler
from . import gpg_handler
from . import hash_handler
from . import sources


_logger = logging.getLogger('utils.__init__')


def checkMounted(devpath):
    for p in psutil.disk_partitions(all = True):
        if p.device == devpath:
            _logger.error(('{0} is mounted at {1} but was specified as a target. '
                           'Cowardly refusing to run potentially destructive operations on it.').format(devpath,
                                                                                                        p.mountpoint))
            # TODO: raise only if not dryrun? Raise warning instead if so?
            raise RuntimeError('Device mounted in live environment')
    return(None)


def collapseKeys(d, keylist = None):
    if not keylist:
        keylist = []
    for k, v in d.items():
        if isinstance(v, dict):
            keylist.append(k)
            keylist = collapseKeys(v, keylist = keylist)
        else:
            keylist.append(k)
    return(keylist)


def collapseValues(d, vallist = None):
    if not vallist:
        vallist = []
    for k, v in d.items():
        if isinstance(v, dict):
            vallist = collapseValues(v, vallist = vallist)
        else:
            vallist.append(v)
    return(vallist)


def hasBin(binary_name):
    paths = []
    for p in os.environ.get('PATH', '/usr/bin:/bin').split(':'):
        if binary_name in os.listdir(os.path.realpath(p)):
            return(os.path.join(p, binary_name))
    return(False)


def hasSafeChunks(n):
    if (n % 4) != 0:
        return(False)
    return(True)


def isPowerofTwo(n):
    # So dumb.
    isPowerOf2 = math.ceil(math.log(n, 2)) == math.floor(math.log(n, 2))
    return(isPowerOf2)


# custom Jinja2 filters
def j2_isDict(value):
    return(isinstance(value, dict))


def j2_isList(value):
    return(isinstance(value, list))


j2_filters = {'isDict': j2_isDict,
              'isList': j2_isList}
# end custom Jinja2 filters


def kernelCmdline(chroot_base = '/'):
    cmds = {}
    chroot_base = pathlib.PosixPath(chroot_base)
    cmdline = chroot_base.joinpath('proc', 'cmdline')
    if not os.path.isfile(cmdline):
        return(cmds)
    with open(cmdline, 'r') as fh:
        raw_cmds = fh.read().strip()
    for c in shlex.split(raw_cmds):
        l = c.split('=', 1)
        if len(l) < 2:
            l.append(None)
        cmds[l[0]] = l[1]
    return(cmds)


def kernelFilesystems():
    # I wish there was a better way of doing this.
    # https://unix.stackexchange.com/a/98680
    FS_FSTYPES = ['swap']
    with open('/proc/filesystems', 'r') as fh:
        for line in fh.readlines():
            l = [i.strip() for i in line.split()]
            if not l:
                continue
            if len(l) == 1:
                FS_FSTYPES.append(l[0])
            else:
                FS_FSTYPES.append(l[1])
    _logger.debug('Built list of pre-loaded filesystem types: {0}'.format(','.join(FS_FSTYPES)))
    _mod_dir = os.path.join('/lib/modules',
                            os.uname().release,
                            'kernel/fs')
    _strip_mod_suffix = re.compile(r'(?P<fsname>)\.ko(\.(x|g)?z)?$', re.IGNORECASE)
    try:
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
                if os.getuid() == 0:
                    cmd = subprocess.run(['modprobe', fs_name], stderr = subprocess.PIPE, stdout = subprocess.PIPE)
                    _logger.debug('Executed: {0}'.format(' '.join(cmd.args)))
                    if cmd.returncode != 0:
                        _logger.warning('Command returned non-zero status')
                        _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
                        for a in ('stdout', 'stderr'):
                            x = getattr(cmd, a)
                            if x:
                                _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
                    FS_FSTYPES.append(fs_name)
    except FileNotFoundError:
        # We're running on a kernel that doesn't have modules
        _logger.info('Kernel has no modules available')
        pass
    FS_FSTYPES = sorted(list(set(FS_FSTYPES)))
    _logger.debug('Generated full list of FS_FSTYPES: {0}'.format(','.join(FS_FSTYPES)))
    return(FS_FSTYPES)


def xmlBool(xmlobj):
    # https://bugs.launchpad.net/lxml/+bug/1850221
    if isinstance(xmlobj, bool):
        return (xmlobj)
    if xmlobj.lower() in ('1', 'true'):
        return(True)
    elif xmlobj.lower() in ('0', 'false'):
        return(False)
    else:
        return(None)


class _Sizer(object):
    # We use different methods for converting between storage and BW, and different multipliers for each subtype.
    # https://stackoverflow.com/a/12912296/733214
    # https://stackoverflow.com/a/52684562/733214
    # https://stackoverflow.com/questions/5194057/better-way-to-convert-file-sizes-in-python
    # https://en.wikipedia.org/wiki/Orders_of_magnitude_(data)
    # https://en.wikipedia.org/wiki/Binary_prefix
    # 'decimal' is base-10, 'binary' is base-2. (Duh.)
    # "b" = bytes, "n" = given value, and "u" = unit suffix's key in below notes.
    storageUnits = {
        'decimal': {  # n * (10 ** u) = b; b / (10 ** u) = u
            0: (None, 'B', 'byte'),
            3: ('k', 'kB', 'kilobyte'),
            6: ('M', 'MB', 'megabyte'),
            9: ('G', 'GB', 'gigabyte'),
            12: ('T', 'TB', 'teraybte'),
            13: ('P', 'PB', 'petabyte'),  # yeah, right.
            15: ('E', 'EB', 'exabyte'),
            18: ('Z', 'ZB', 'zettabyte'),
            19: ('Y', 'YB', 'yottabyte')
            },
        'binary': {  # n * (2 ** u) = b; b / (2 ** u) = u
            -1: ('nybble', 'nibble', 'nyble', 'half-byte', 'tetrade', 'nibble'),
            10: ('Ki', 'KiB', 'kibibyte'),
            20: ('Mi', 'MiB', 'mebibyte'),
            30: ('Gi', 'GiB', 'gibibyte'),
            40: ('Ti', 'TiB', 'tebibyte'),
            50: ('Pi', 'PiB', 'pebibyte'),
            60: ('Ei', 'EiB', 'exbibyte'),
            70: ('Zi', 'ZiB', 'zebibyte'),
            80: ('Yi', 'YiB', 'yobibyte')
            }}
    # https://en.wikipedia.org/wiki/Bit#Multiple_bits - note that 8 bits = 1 byte
    bwUnits = {
        'decimal': {  # n * (10 ** u) = b; b / (10 ** u) = u
            0: (None, 'b', 'bit'),
            3: ('k', 'kb', 'kilobit'),
            6: ('M', 'Mb', 'megabit'),
            9: ('G', 'Gb', 'gigabit'),
            12: ('T', 'Tb', 'terabit'),
            13: ('P', 'Pb', 'petabit'),
            15: ('E', 'Eb', 'exabit'),
            18: ('Z', 'Zb', 'zettabit'),
            19: ('Y', 'Yb', 'yottabit')
            },
        'binary': {  # n * (2 ** u) = b; b / (2 ** u) = u
            -1: ('semi-octet', 'quartet', 'quadbit'),
            10: ('Ki', 'Kib', 'kibibit'),
            20: ('Mi', 'Mib', 'mebibit'),
            30: ('Gi', 'Gib', 'gibibit'),
            40: ('Ti', 'Tib', 'tebibit'),
            50: ('Pi', 'Pib', 'pebibit'),
            60: ('Ei', 'Eib', 'exbibit'),
            70: ('Zi', 'Zib', 'zebibit'),
            80: ('Yi', 'Yib', 'yobibit')
            }}
    valid_storage = []
    for unit_type, convpair in storageUnits.items():
        for f, l in convpair.items():
            for suffix in l:
                if suffix not in valid_storage and suffix:
                    valid_storage.append(suffix)
    valid_bw = []
    for unit_type, convpair in bwUnits.items():
        for f, l in convpair.items():
            for suffix in l:
                if suffix not in valid_bw and suffix:
                    valid_bw.append(suffix)

    def __init__(self):
        pass

    def convert(self, n, suffix):
        conversion = {}
        if suffix in self.valid_storage:
            conversion.update(self.convertStorage(n, suffix))
            b = conversion['B'] * 8
            conversion.update(self.convertBW(b, 'b'))
        elif suffix in self.valid_bw:
            conversion.update(self.convertBW(n, suffix))
            b = conversion['b'] / 8
            conversion.update(self.convertStorage(b, 'B'))
        return(conversion)

    def convertBW(self, n, suffix, target = None):
        inBits = None
        conversion = None
        base_factors = []
        if suffix not in self.valid_bw:
            _logger.error('Suffix {0} is invalid; must be one of {1}'.format(suffix, ','.join(self.valid_bw)))
            raise ValueError('suffix is not a valid unit notation for this conversion')
        if target and target not in self.valid_bw:
            _logger.error('Target {0} is invalid; must be one of {1}'.format(target, ','.join(self.valid_bw)))
            raise ValueError('target is not a valid unit notation for this conversion')
        for (_unit_type, _base) in (('decimal', 10), ('binary', 2)):
            if target and base_factors:
                break
            for u, suffixes in self.bwUnits[_unit_type].items():
                if all((target, inBits, base_factors)):
                    break
                if suffix in suffixes:
                    inBits = n * float(_base ** u)
                if target and target in suffixes:
                    base_factors.append((_base, u, suffixes[1]))
                elif not target:
                    base_factors.append((_base, u, suffixes[1]))
        if target:
            conversion = float(inBits) / float(base_factors[0][0] ** base_factors[0][1])
        else:
            if not isinstance(conversion, dict):
                conversion = {}
            for base, factor, suffix in base_factors:
                conversion[suffix] = float(inBits) / float(base ** factor)
        return(conversion)

    def convertStorage(self, n, suffix, target = None):
        inBytes = None
        conversion = None
        base_factors = []
        if suffix not in self.valid_storage:
            _logger.error('Suffix {0} is invalid; must be one of {1}'.format(suffix, ','.join(self.valid_storage)))
            raise ValueError('suffix is not a valid unit notation for this conversion')
        if target and target not in self.valid_storage:
            _logger.error('Target {0} is invalid; must be one of {1}'.format(target, ','.join(self.valid_storage)))
            raise ValueError('target is not a valid unit notation for this conversion')
        for (_unit_type, _base) in (('decimal', 10), ('binary', 2)):
            if target and base_factors:
                break
            for u, suffixes in self.storageUnits[_unit_type].items():
                if all((target, inBytes, base_factors)):
                    break
                if suffix in suffixes:
                    inBytes = n * float(_base ** u)
                if target and target in suffixes:
                    base_factors.append((_base, u, suffixes[1]))
                elif not target:
                    base_factors.append((_base, u, suffixes[1]))
        if target:
            conversion = float(inBytes) / float(base_factors[0][0] ** base_factors[0][1])
        else:
            if not isinstance(conversion, dict):
                conversion = {}
            for base, factor, suffix in base_factors:
                conversion[suffix] = float(inBytes) / float(base ** factor)
        return(conversion)


size = _Sizer()


# We do this as base level so they aren't compiled on every invocation/instantiation.
# Unfortunately it has to be at the bottom so we can call the instantiated _Sizer() class.
# parted lib can do SI or IEC. So can we.
_pos_re = re.compile((r'^(?P<pos_or_neg>-|\+)?\s*'
                      r'(?P<size>[0-9]+)\s*'
                      # empty means size in sectors
                      r'(?P<pct_unit_or_sct>%|{0}|)\s*$'.format('|'.join(size.valid_storage))
                      ))


def convertSizeUnit(pos):
    orig_pos = pos
    pos = _pos_re.search(pos)
    if pos:
        pos_or_neg = (pos.group('pos_or_neg') if pos.group('pos_or_neg') else None)
        if pos_or_neg == '+':
            from_beginning = True
        elif pos_or_neg == '-':
            from_beginning = False
        else:
            from_beginning = pos_or_neg
        _size = int(pos.group('size'))
        amt_type = pos.group('pct_unit_or_sct').strip()
    else:
        _logger.error('Size {0} is invalid; did not match {1}'.format(orig_pos, _pos_re.pattern))
        raise ValueError('Invalid size specified')
    return((from_beginning, _size, amt_type))
