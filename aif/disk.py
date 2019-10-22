# To reproduce sgdisk behaviour in v1 of AIF-NG:
# https://gist.github.com/herry13/5931cac426da99820de843477e41e89e
# https://github.com/dcantrell/pyparted/blob/master/examples/query_device_capacity.py
# TODO: Remember to replicate genfstab behaviour.

import os
import re
import subprocess
try:
    # https://stackoverflow.com/a/34812552/733214
    # https://github.com/karelzak/util-linux/blob/master/libmount/python/test_mount_context.py#L6
    import libmount as mount
except ImportError:
    # We should never get here. util-linux is part of core (base) in Arch and uses "libmount".
    import pylibmount as mount
##
import blkinfo
import parted  # https://www.gnu.org/software/parted/api/index.html
import psutil
##
from .aif_util import xmlBool
from .constants import PARTED_FSTYPES


# parted lib can do SI or IEC (see table to right at https://en.wikipedia.org/wiki/Binary_prefix)
# We bit-shift to do conversions:
# https://stackoverflow.com/a/12912296/733214
# https://stackoverflow.com/a/52684562/733214
_units = {'B': 0,
          'kB': 7,
          'MB': 17,
          'GB': 27,
          'TB': 37,
          'KiB': 10,
          'MiB': 20,
          'GiB': 30,
          'TiB': 40}
_pos_re = re.compile((r'^(?P<pos_or_neg>-|\+)?\s*'
                      r'(?P<size>[0-9]+)\s*'
                      # empty means size in sectors
                      r'(?P<pct_unit_or_sct>%|[{0}]|)\s*$'.format(''.join(list(_units.keys())))),
                     re.IGNORECASE)


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
        size = int(pos.group('size'))
        amt_type = pos.group('pct_unit_or_sct').strip()
    else:
        raise ValueError('Invalid size specified: {0}'.format(orig_pos))
    return((from_beginning, size, amt_type))


class Partition(object):
    def __init__(self, part_xml, diskobj, start_sector, partnum, tbltype):
        if tbltype not in ('gpt', 'msdos'):
            raise ValueError('{0} must be one of gpt or msdos'.format(tbltype))
        self.xml = part_xml
        self.partnum = partnum
        self.fstype = self.xml.attrib['fsType'].lower()
        if self.fstype not in PARTED_FSTYPES:
            raise ValueError(('{0} is not a valid partition filesystem type; '
                              'must be one of: {1}').format(self.xml.attrib['fsType'],
                                                            ', '.join(sorted(PARTED_FSTYPES))))
        self.disk = diskobj
        self.device = self.disk.device
        self.dev = '{0}{1}'.format(self.device.path, partnum)
        sizes = {}
        for s in ('start', 'stop'):
            x = dict(zip(('from_bgn', 'size', 'type'),
                         convertSizeUnit(self.xml.attrib[s])))
            sectors = x['size']
            if x['type'] == '%':
                sectors = int(self.device.getLength() / x['size'])
            elif x['type'] in _units.keys():
                sectors = int(x['size'] << _units[x['type']] / self.device.sectorSize)
            sizes[s] = (sectors, x['from_bgn'])
        if sizes['start'][1] is not None:
            if sizes['start'][1]:
                self.begin = sizes['start'][0] + 0
            else:
                self.begin = self.device.getLength() - sizes['start'][0]
        else:
            self.begin = sizes['start'][0] + start_sector
        if sizes['stop'][1] is not None:
            if sizes['stop'][1]:
                self.end = sizes['stop'][0] + 0
            else:
                # This *technically* should be - 34, but the alignment optimizer fixes it for us.
                self.end = (self.device.getLength() - 1) - sizes['stop'][0]
        else:
            self.end = self.begin + sizes['stop'][0]
        # TECHNICALLY we could craft the Geometry object with "length = ...", but it doesn't let us be explicit
        # in configs. So we manually crunch the numbers and do it all at the end.
        self.geometry = parted.Geometry(device = self.device,
                                        start = self.begin,
                                        end = self.end)
        self.filesystem = parted.FileSystem(type = self.fstype,
                                            geometry = self.geometry)
        self.partition = parted.Partition(disk = diskobj,
                                          type = parted.PARTITION_NORMAL,
                                          geometry = self.geometry,
                                          fs = self.filesystem)
        if tbltype == 'gpt' and self.xml.attrib.get('name'):
            # The name attribute setting is b0rk3n, so we operate on the underlying PedPartition object.
            # https://github.com/dcantrell/pyparted/issues/49#issuecomment-540096687
            # https://github.com/dcantrell/pyparted/issues/65
            # self.partition.name = self.xml.attrib.get('name')
            _pedpart = self.partition.getPedPartition()
            _pedpart.set_name(self.xml.attrib.get('name'))


class Disk(object):
    def __init__(self, disk_xml):
        self.xml = disk_xml
        self.devpath = self.xml.attrib['device']
        self.partitions = []
        self._initDisk()

    def _initDisk(self):
        self.device = parted.getDevice(self.devpath)
        try:
            self.disk = parted.newDisk(self.device)
            self.is_new = False
            if xmlBool(self.xml.attrib.get('forceReformat')):
                self.is_lowformatted = False
                self.is_hiformatted = False
            else:
                self.is_lowformatted = True
                self.is_hiformatted = False
                for d in blkinfo.BlkDiskInfo().get_disks(filters = {'group': 'disk',
                                                                    'name': os.path.basename(self.devpath),
                                                                    'kname': os.path.basename(self.devpath)}):
                    if d.get('fstype', '').strip() != '':
                        self.is_hiformatted = True
                        break
        except parted._ped.DiskException:
            self.disk = None
            self.is_new = True
            self.is_lowformatted = False
            self.is_hiformatted = False
        self.is_partitioned = False
        return()

    def diskFormat(self):
        if self.is_lowformatted:
            return()
        # This is a safeguard. We do *not* want to low-format a disk that is mounted.
        for p in psutil.disk_partitions(all = True):
            if self.devpath in p:
                raise RuntimeError('{0} is mounted; we are cowardly refusing to low-format it'.format(self.devpath))
        if not self.is_new:
            self.disk.deleteAllPartitions()
        self.tabletype = self.xml.attrib.get('diskFormat', 'gpt').lower()
        if self.tabletype in ('bios', 'mbr', 'dos'):
            self.tabletype = 'msdos'
        validlabels = parted.getLabels()
        if self.tabletype not in validlabels:
            raise ValueError(('Disk format {0} is not valid for this architecture;'
                              'must be one of: {1}'.format(self.tabletype, ', '.join(list(validlabels)))))
        self.disk = parted.freshDisk(self.device, self.tabletype)
        self.is_lowformatted = True
        return()

    def fsFormat(self):
        if self.is_hiformatted:
            return()
        # This is a safeguard. We do *not* want to high-format a disk that is mounted.
        for p in psutil.disk_partitions(all = True):
            if self.devpath in p:
                raise RuntimeError('{0} is mounted; we are cowardly refusing to high-format it'.format(self.devpath))
        # TODO!
        pass
        return()

    def getPartitions(self):
        # For GPT, this *technically* should be 34 -- or, more precisely, 2048 (see FAQ in manual), but the alignment
        # optimizer fixes it for us automatically.
        start_sector = 0
        self.partitions = []
        for idx, part in enumerate(self.xml.findall('part')):
            p = Partition(part, self.disk, start_sector, idx + 1, self.tabletype)
            start_sector = p.end + 1
            self.partitions.append(p)
        return()

    def partFormat(self):
        if self.is_partitioned:
            return()
        if not self.is_lowformatted:
            self.diskFormat()
        # This is a safeguard. We do *not* want to partition a disk that is mounted.
        for p in psutil.disk_partitions(all = True):
            if self.devpath in p:
                raise RuntimeError('{0} is mounted; we are cowardly refusing to low-format it'.format(self.devpath))
        if not self.partitions:
            self.getPartitions()
        if not self.partitions:
            return()
        for p in self.partitions:
            self.disk.addPartition(partition = p, constraint = self.device.optimalAlignedConstraint)
        self.disk.commit()
        self.is_partitioned = True
        return()
