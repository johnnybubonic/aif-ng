import logging
import os
import uuid
##
import blkinfo
# import psutil  # Do I need this if I can have libblockdev's mounts API? Is there a way to get current mounts?
from lxml import etree
##
import aif.constants
import aif.utils
from . import _common


_BlockDev = _common.BlockDev
_logger = logging.getLogger(__name__)


class Disk(object):
    def __init__(self, disk_xml):
        self.xml = disk_xml
        _logger.debug('disk_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.devpath = os.path.realpath(self.xml.attrib['device'])
        aif.disk._common.addBDPlugin('part')
        self.is_lowformatted = None
        self.is_hiformatted = None
        self.is_partitioned = None
        self.partitions = None
        self._initDisk()

    def _initDisk(self):
        if self.devpath == 'auto':
            self.devpath = '/dev/{0}'.format(blkinfo.BlkDiskInfo().get_disks()[0]['kname'])
        if not os.path.isfile(self.devpath):
            _logger.error('Disk {0} does not exist; please specify an explicit device path'.format(self.devpath))
            raise ValueError('Disk not found')
        self.table_type = self.xml.attrib.get('diskFormat', 'gpt').lower()
        if self.table_type in ('bios', 'mbr', 'dos', 'msdos'):
            _logger.debug('Disk format set to MSDOS.')
            self.table_type = _BlockDev.PartTableType.MSDOS
        elif self.table_type == 'gpt':
            self.table_type = _BlockDev.PartTableType.GPT
            _logger.debug('Disk format set to GPT.')
        else:
            _logger.error('Disk format {0} is invalid for this system\'s architecture; must be gpt or msdos')
            raise ValueError('Invalid disk format')
        self.device = self.disk = _BlockDev.part.get_disk_spec(self.devpath)
        self.is_lowformatted = False
        self.is_hiformatted = False
        self.is_partitioned = False
        self.partitions = []
        return(None)

    def diskFormat(self):
        if self.is_lowformatted:
            return(None)
        # This is a safeguard. We do *not* want to low-format a disk that is mounted.
        aif.utils.checkMounted(self.devpath)
        # TODO: BlockDev.part.set_disk_flag(<disk>,
        #                                   BlockDev.PartDiskFlag(1),
        #                                   True) ??
        #       https://lazka.github.io/pgi-docs/BlockDev-2.0/enums.html#BlockDev.PartDiskFlag
        #       https://unix.stackexchange.com/questions/325886/bios-gpt-do-we-need-a-boot-flag
        _BlockDev.part.create_table(self.devpath, self.table_type, True)
        self.is_lowformatted = True
        self.is_partitioned = False
        return(None)

    def getPartitions(self):
        # For GPT, this *technically* should be 34 -- or, more precisely, 2048 (see FAQ in manual), but the alignment
        # optimizer fixes it for us automatically.
        # But for DOS tables, it's required.
        _logger.info('Establishing partitions for {0}'.format(self.devpath))
        if self.table_type == 'msdos':
            start_sector = 2048
        else:
            start_sector = 0
        self.partitions = []
        xml_partitions = self.xml.findall('part')
        for idx, part in enumerate(xml_partitions):
            partnum = idx + 1
            if self.table_type == 'gpt':
                p = Partition(part, self.disk, start_sector, partnum, self.table_type)
            else:
                parttype = 'primary'
                if len(xml_partitions) > 4:
                    if partnum == 4:
                        parttype = 'extended'
                    elif partnum > 4:
                        parttype = 'logical'
                p = Partition(part, self.disk, start_sector, partnum, self.table_type, part_type = parttype)
            start_sector = p.end + 1
            self.partitions.append(p)
            _logger.debug('Added partition {0}'.format(p.id))
        return(None)

    def partFormat(self):
        if self.is_partitioned:
            return(None)
        if not self.is_lowformatted:
            self.diskFormat()
        # This is a safeguard. We do *not* want to partition a disk that is mounted.
        aif.utils.checkMounted(self.devpath)
        if not self.partitions:
            self.getPartitions()
        if not self.partitions:
            return(None)
        for p in self.partitions:
            p.format()
            p.is_hiformatted = True
        self.is_partitioned = True
        return(None)


class Partition(object):
    def __init__(self, part_xml, diskobj, start_sector, partnum, tbltype, part_type = None):
        # Belive it or not, dear reader, but this *entire method* is just to set attributes.
        if tbltype not in ('gpt', 'msdos'):
            _logger.error('Invalid tabletype specified: {0}. Must be one of: gpt,msdos.'.format(tbltype))
            raise ValueError('Invalid tbltype.')
        if tbltype == 'msdos' and part_type not in ('primary', 'extended', 'logical'):
            _logger.error(('Table type msdos requires the part_type to be specified and must be one of: primary,'
                           'extended,logical (instead of: {0}).').format(part_type))
            raise ValueError('The part_type must be specified for msdos tables')
        aif.disk._common.addBDPlugin('part')
        self.xml = part_xml
        _logger.debug('part_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        _logger.debug('Partition number: {0}'.format(partnum))
        self.id = self.xml.attrib['id']
        self.table_type = getattr(_BlockDev.PartTableType, tbltype.upper())
        _logger.debug('Partition table type: {0}.'.format(tbltype))
        if tbltype == 'msdos':
            # Could technically be _BlockDev.PartTypeReq.NEXT BUT that doesn't *quite* work
            # with this project's structure.
            if part_type == 'primary':
                self.part_type = _BlockDev.PartTypeReq.NORMAL
            elif part_type == 'extended':
                self.part_type = _BlockDev.PartTypeReq.EXTENDED
            elif part_type == 'logical':
                self.part_type = _BlockDev.PartTypeReq.LOGICAL
        elif tbltype == 'gpt':
            self.part_type = _BlockDev.PartTypeReq.NORMAL
        self.flags = []
        self.partnum = partnum
        self.fs_type = self.xml.attrib['fsType']
        self.disk = diskobj
        self.device = self.disk.path
        self.devpath = '{0}{1}'.format(self.device, self.partnum)
        _logger.debug('Assigned to disk: {0} ({1}) at path {2}'.format(self.disk.id, self.device, self.devpath))
        self.is_hiformatted = False
        sizes = {}
        for s in ('start', 'stop'):
            x = dict(zip(('from_bgn', 'size', 'type'),
                         aif.utils.convertSizeUnit(self.xml.attrib[s])))
            sectors = x['size']
            if x['type'] == '%':
                sectors = int(int(self.disk.size / self.disk.sector_size) * (0.01 * x['size']))
            else:
                sectors = int(aif.utils.size.convertStorage(x['size'],
                                                            x['type'],
                                                            target = 'B') / self.disk.sector_size)
            sizes[s] = (sectors, x['from_bgn'])
        if sizes['start'][1] is not None:
            if sizes['start'][1]:
                self.begin = sizes['start'][0] + 0
            else:
                self.begin = int(self.disk.size / self.disk.sector_size) - sizes['start'][0]
        else:
            self.begin = sizes['start'][0] + start_sector
        if sizes['stop'][1] is not None:
            if sizes['stop'][1]:
                self.end = sizes['stop'][0] + 0
            else:
                # This *technically* should be - 34, at least for gpt, but the alignment optimizer fixes it for us.
                self.end = (int(self.disk.size / self.disk.sector_size) - 1) - sizes['stop'][0]
        else:
            self.end = self.begin + sizes['stop'][0]
        self.size = (self.end - self.begin)
        _logger.debug('Size: {0} sectors (sector {1} to {2}).'.format(self.size, self.begin, self.end))
        self.part_name = self.xml.attrib.get('name')
        _logger.debug('Partition name: {0}'.format(self.part_name))
        self.partition = None
        self._initFlags()
        self._initFstype()

    def _initFlags(self):
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
        _logger.debug('Partition flags: {0}'.format(','.join(self.flags)))
        return(None)

    def _initFstype(self):
        if self.fs_type in aif.constants.PARTED_FSTYPES_GUIDS.keys():
            self.fs_type = aif.constants.PARTED_FSTYPES_GUIDS[self.fs_type]
            _logger.debug('Filesystem type (parted): {0}'.format(self.fs_type))
        else:
            try:
                self.fs_type = uuid.UUID(hex = self.fs_type)
                _logger.debug('Filesystem type (explicit GUID): {0}'.format(str(self.fs_type)))
            except ValueError:
                _logger.error('Partition type GUID {0} is not a valid UUID4 string'.format(self.fs_type))
                raise ValueError('Invalid partition type GUID')
            if self.fs_type not in aif.constants.GPT_GUID_IDX.keys():
                _logger.error('Partition type GUID {0} is not a valid partition type'.format(self.fs_type))
                raise ValueError('Invalid partition type value')
        return(None)

    def format(self):
        _logger.info('Formatting partion {0}.'.format(self.id))
        # This is a safeguard. We do *not* want to partition a disk that is mounted.
        aif.utils.checkMounted(self.devpath)
        _logger.info('Creating partition object.')
        self.partition = _BlockDev.part.create_part(self.device,
                                                    self.part_type,
                                                    self.begin,
                                                    self.size,
                                                    _BlockDev.PartAlign.OPTIMAL)
        _logger.debug('Partition object created.')
        self.devpath = self.partition.path
        _logger.debug('Partition path updated: {0}'.format(self.devpath))
        _BlockDev.part.set_part_type(self.device, self.devpath, str(self.fs_type).upper())
        if self.part_name:
            _BlockDev.part.set_part_name(self.device, self.devpath, self.part_name)
        if self.flags:
            for f in self.flags:
                _BlockDev.part.set_part_flag(self.device, self.devpath, f, True)
        _logger.info('Partition {0} formatted.'.format(self.devpath))
        return(None)

    #
    # def detect(self):
    #     pass  # TODO; blkinfo?
