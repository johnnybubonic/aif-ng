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
    def __init__(self, disk_xml, diskobj, start_sector):
        self.xml = disk_xml
        device = diskobj.device
        sizes = {}
        for s in ('start', 'stop'):
            x = dict(zip(('from_bgn', 'size', 'type'),
                         convertSizeUnit(self.xml.attrib[s])))
            sectors = x['size']
            if x['type'] == '%':
                sectors = int(device.getLength() / x['size'])
            elif x['type'] in _units.keys():
                sectors = int(x['size'] << _units[x['type']] / device.sectorSize)
            sizes[s] = (sectors, x['from_bgn'])
        if sizes['start'][1] is not None:
            if sizes['start'][1]:
                self.begin = sizes['start'][0] + 0
            else:
                self.begin = device.getLength() - sizes['start'][0]
        else:
            self.begin = sizes['start'][0] + start_sector
        if sizes['stop'][1] is not None:
            if sizes['stop'][1]:
                self.end = sizes['stop'][0] + 0
            else:
                self.end = device.getLength() - sizes['stop'][0]
        else:
            self.end = self.begin + sizes['stop'][0]
        # TECHNICALLY we could craft the Geometry object with "length = ...", but it doesn't let us be explicit
        # in configs. So we manually crunch the numbers and do it all at the end.
        self.geometry = parted.Geometry(device = device,
                                        start = self.begin,
                                        end = self.end)
        self.filesystem = parted.FileSystem(type = self.xml.attrib['fsType'],
                                            )
        self.partition = parted.Partition(disk = diskobj,
                                          type = parted.PARTITION_NORMAL,
                                          geometry = self.geometry,
                                          fs = )

class Disk(object):
    def __init__(self, disk_xml):
        self.xml = disk_xml
        self.devpath = self.xml.attrib['device']
        self._initDisk()

    def _initDisk(self):
        self.device = parted.getDevice(self.devpath)
        try:
            self.disk = parted.newDisk(self.device)
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
            self.is_partitioned = True
        except parted._ped.DiskException:
            self.disk = None
            self.is_lowformatted = False
            self.is_hiformatted = False
            self.is_partitioned = False
        return()

    def diskformat(self):
        if self.is_lowformatted:
            return()
        # This is a safeguard. We do *not* want to low-format a disk that is mounted.
        for p in psutil.disk_partitions(all = True):
            if self.devpath in p:
                raise RuntimeError('{0} is mounted; we are cowardly refusing to low-format it'.format(self.devpath))
        self.disk.deleteAllPartitions()
        tabletype = self.xml.attrib.get('diskFormat', 'gpt').lower()
        if tabletype in ('bios', 'mbr'):
            tabletype = 'msdos'
        validlabels = parted.getLabels()
        if tabletype not in validlabels:
            raise ValueError(('Disk format {0} is not valid for this architecture;'
                              'must be one of: {1}'.format(tabletype, ', '.join(list(validlabels)))))
        self.disk = parted.freshDisk(self.device, tabletype)

        pass
        self.is_lowformatted = True
        self.is_partitioned = True
        return()

    def fsformat(self):
        if self.is_hiformatted:
            return()
        # This is a safeguard. We do *not* want to high-format a disk that is mounted.
        for p in psutil.disk_partitions(all = True):
            if self.devpath in p:
                raise RuntimeError('{0} is mounted; we are cowardly refusing to high-format it'.format(self.devpath))

        pass
        return()
