import re
##
import parted
import psutil  # Do I need this if I can have libblockdev's mounts API? Is there a way to get current mounts?
##
import aif.constants
import aif.utils
from . import _common


_BlockDev = _common.BlockDev


class Partition(object):
    def __init__(self, part_xml, diskobj, start_sector, partnum, tbltype, part_type = None):
        # Belive it or not, dear reader, but this *entire method* is just to set attributes.
        if tbltype not in ('gpt', 'msdos'):
            raise ValueError('{0} must be one of gpt or msdos'.format(tbltype))
        if tbltype == 'msdos' and part_type not in ('primary', 'extended', 'logical'):
            raise ValueError(('You must specify if this is a '
                              'primary, extended, or logical partition for msdos partition tables'))
        aif.disk._common.addBDPlugin('part')
        self.xml = part_xml
        self.id = part_xml.attrib['id']
        self.table_type = getattr(_BlockDev.PartTableType, tbltype.upper())
        if tbltype == 'msdos':
            # Could technically be _BlockDev.PartTypeReq.NEXT BUT that doesn't *quite* work
            # with this project's structure.
            if part_type == 'primary':
                self.part_type = _BlockDev.PartTypeReq.NORMAL
            elif part_type == 'extended':
                self.part_type = _BlockDev.PartTypeReq.EXTENDED
            elif part_type == 'logical':
                self.part_type = _BlockDev.PartTypeReq.LOGICAL
        self.flags = []
        for f in self.xml.findall('partitionFlag'):
            # *Technically* we could use e.g. getattr(_BlockDev.PartFlag, f.text.upper()), *but* we lose compat
            # with parted's flags if we do that. :| So we do some funky logic both here and in the constants.
            if f.text in aif.constants.PARTED_BD_MAP:
                flag_id = aif.constants.BD_PART_FLAGS_FLAG_IDX[aif.constants.PARTED_BD_MAP[f.text]]
            elif f.text in aif.constants.BD_PART_FLAGS_FRIENDLY:
                flag_id = aif.constants.BD_PART_FLAGS_FLAG_IDX[aif.constants.BD_PART_FLAGS_FRIENDLY[f.text]]
            else:
                continue
            self.flags.append(_BlockDev.PartFlag(flag_id))
        self.partnum = partnum
        self.fstype = self.xml.attrib['fsType'].lower()
        if self.fstype not in aif.constants.PARTED_FSTYPES:  # There isn't a way to do this with BlockDev? :|
            raise ValueError(('{0} is not a valid partition filesystem type; '
                              'must be one of: {1}').format(self.xml.attrib['fsType'],
                                                            ', '.join(sorted(aif.constants.PARTED_FSTYPES))))
        self.disk = diskobj
        self.device = self.disk.path
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
                self.begin = self.device.getLength() - sizes['start'][0]  # TODO: is there a way to get this in BD?
        else:
            self.begin = sizes['start'][0] + start_sector
        if sizes['stop'][1] is not None:
            if sizes['stop'][1]:
                self.end = sizes['stop'][0] + 0
            else:
                # This *technically* should be - 34, at least for gpt, but the alignment optimizer fixes it for us.
                self.end = (self.device.getLength() - 1) - sizes['stop'][0]  # TODO: is there a way to get this in BD?
        else:
            self.end = self.begin + sizes['stop'][0]
        # TECHNICALLY we could craft the Geometry object with "length = ...", but it doesn't let us be explicit
        # in configs. So we manually crunch the numbers and do it all at the end.
        # TODO: switch parted objects to BlockDev
        # self.geometry = parted.Geometry(device = self.device,
        #                                 start = self.begin,
        #                                 end = self.end)
        # self.filesystem = parted.FileSystem(type = self.fstype,
        #                                     geometry = self.geometry)
        # self.partition = parted.Partition(disk = diskobj,
        #                                   type = self.part_type,
        #                                   geometry = self.geometry,
        #                                   fs = self.filesystem)
        self.part_name = self.xml.attrib.get('name')

    #
    # def detect(self):
    #     pass  # TODO; blkinfo?


class Disk(object):
    def __init__(self, disk_xml):
        # TODO: BlockDev.part.set_disk_flag(<disk>,
        #                                   BlockDev.PartDiskFlag(1),
        #                                   True) ??
        #   https://lazka.github.io/pgi-docs/BlockDev-2.0/enums.html#BlockDev.PartDiskFlag
        #   https://unix.stackexchange.com/questions/325886/bios-gpt-do-we-need-a-boot-flag
        self.xml = disk_xml
        self.devpath = self.xml.attrib['device']
        self.is_lowformatted = None
        self.is_hiformatted = None
        self.is_partitioned = None
        self.partitions = None
        self._initDisk()
        aif.disk._common.addBDPlugin('part')

    def _initDisk(self):
        pass

    def diskFormat(self):
        pass

    def getPartitions(self):
        pass

    def partFormat(self):
        pass


class Mount(object):
    def __init__(self, mount_xml, partobj):
        pass
        _common.addBDPlugin('fs')
