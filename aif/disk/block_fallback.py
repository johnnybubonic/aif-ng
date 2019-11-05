# To reproduce sgdisk behaviour in v1 of AIF-NG:
# https://gist.github.com/herry13/5931cac426da99820de843477e41e89e
# https://github.com/dcantrell/pyparted/blob/master/examples/query_device_capacity.py
# TODO: Remember to replicate genfstab behaviour.

import re
try:
    # https://stackoverflow.com/a/34812552/733214
    # https://github.com/karelzak/util-linux/blob/master/libmount/python/test_mount_context.py#L6
    import libmount as mount
except ImportError:
    # We should never get here. util-linux is part of core (base) in Arch and uses "libmount".
    import pylibmount as mount
##
import parted  # https://www.gnu.org/software/parted/api/index.html
import psutil
##
import aif.constants
import aif.utils

# TODO: https://serverfault.com/questions/356534/ssd-erase-block-size-lvm-pv-on-raw-device-alignment


class Partition(object):
    def __init__(self, part_xml, diskobj, start_sector, partnum, tbltype, part_type = None):
        if tbltype not in ('gpt', 'msdos'):
            raise ValueError('{0} must be one of gpt or msdos'.format(tbltype))
        if tbltype == 'msdos' and part_type not in ('primary', 'extended', 'logical'):
            raise ValueError(('You must specify if this is a '
                              'primary, extended, or logical partition for msdos partition tables'))
        self.xml = part_xml
        self.id = self.xml.attrib['id']
        self.flags = set()
        for f in self.xml.findall('partitionFlag'):
            if f.text in aif.constants.PARTED_FLAGS:
                self.flags.add(f.text)
        self.flags = sorted(list(self.flags))
        self.partnum = partnum
        if tbltype == 'msdos':
            if partnum > 4:
                self.part_type = parted.PARTITION_LOGICAL
            else:
                if part_type == 'extended':
                    self.part_type = parted.PARTITION_EXTENDED
                elif part_type == 'logical':
                    self.part_type = parted.PARTITION_LOGICAL
        else:
            self.part_type = parted.PARTITION_NORMAL
        self.fstype = self.xml.attrib['fsType'].lower()
        if self.fstype not in aif.constants.PARTED_FSTYPES:
            raise ValueError(('{0} is not a valid partition filesystem type; '
                              'must be one of: {1}').format(self.xml.attrib['fsType'],
                                                            ', '.join(sorted(aif.constants.PARTED_FSTYPES))))
        self.disk = diskobj
        self.device = self.disk.device
        self.devpath = '{0}{1}'.format(self.device.path, partnum)
        self.is_hiformatted = False
        sizes = {}
        for s in ('start', 'stop'):
            x = dict(zip(('from_bgn', 'size', 'type'),
                         aif.utils.convertSizeUnit(self.xml.attrib[s])))
            sectors = x['size']
            if x['type'] == '%':
                sectors = int(self.device.getLength() / x['size'])
            else:
                sectors = int(aif.utils.size.convertStorage(x['size'],
                                                            x['type'],
                                                            target = 'B') / self.device.sectorSize)
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
                # This *technically* should be - 34, at least for gpt, but the alignment optimizer fixes it for us.
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
                                          type = self.part_type,
                                          geometry = self.geometry,
                                          fs = self.filesystem)
        for f in self.flags[:]:
            flag_id = aif.constants.PARTED_FLAG_IDX[f]
            if self.partition.isFlagAvailable(flag_id):
                self.partition.setFlag(flag_id)
            else:
                self.flags.remove(f)
        if tbltype == 'gpt' and self.xml.attrib.get('name'):
            # The name attribute setting is b0rk3n, so we operate on the underlying PedPartition object.
            # https://github.com/dcantrell/pyparted/issues/49#issuecomment-540096687
            # https://github.com/dcantrell/pyparted/issues/65
            # self.partition.name = self.xml.attrib.get('name')
            _pedpart = self.partition.getPedPartition()
            _pedpart.set_name(self.xml.attrib['name'])
    #
    # def detect(self):
    #     pass  # TODO; blkinfo?


class Disk(object):
    def __init__(self, disk_xml):
        self.xml = disk_xml
        self.devpath = self.xml.attrib['device']
        self.is_lowformatted = None
        self.is_hiformatted = None
        self.is_partitioned = None
        self.partitions = None
        self._initDisk()

    def _initDisk(self):
        self.tabletype = self.xml.attrib.get('diskFormat', 'gpt').lower()
        if self.tabletype in ('bios', 'mbr', 'dos'):
            self.tabletype = 'msdos'
        validlabels = parted.getLabels()
        if self.tabletype not in validlabels:
            raise ValueError(('Disk format {0} is not valid for this architecture;'
                              'must be one of: {1}'.format(self.tabletype, ', '.join(list(validlabels)))))
        self.device = parted.getDevice(self.devpath)
        self.disk = parted.freshDisk(self.device, self.tabletype)
        self.is_lowformatted = False
        self.is_hiformatted = False
        self.is_partitioned = False
        self.partitions = []
        return()

    def diskFormat(self):
        if self.is_lowformatted:
            return()
        # This is a safeguard. We do *not* want to low-format a disk that is mounted.
        for p in psutil.disk_partitions(all = True):
            if self.devpath in p:
                raise RuntimeError('{0} is mounted; we are cowardly refusing to low-format it'.format(self.devpath))
        self.disk.deleteAllPartitions()
        self.disk.commit()
        self.is_lowformatted = True
        self.is_partitioned = False
        return()

    def getPartitions(self):
        # For GPT, this *technically* should be 34 -- or, more precisely, 2048 (see FAQ in manual), but the alignment
        # optimizer fixes it for us automatically.
        # But for DOS tables, it's required.
        if self.tabletype == 'msdos':
            start_sector = 2048
        else:
            start_sector = 0
        self.partitions = []
        xml_partitions = self.xml.findall('part')
        for idx, part in enumerate(xml_partitions):
            partnum = idx + 1
            if self.tabletype == 'gpt':
                p = Partition(part, self.disk, start_sector, partnum, self.tabletype)
            else:
                parttype = 'primary'
                if len(xml_partitions) > 4:
                    if partnum == 4:
                        parttype = 'extended'
                    elif partnum > 4:
                        parttype = 'logical'
                p = Partition(part, self.disk, start_sector, partnum, self.tabletype, part_type = parttype)
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
            p.devpath = p.partition.path
            p.is_hiformatted = True
        self.is_partitioned = True
        return()


class Mount(object):
    def __init__(self, mount_xml, partobj):
        self.xml = mount_xml
        pass