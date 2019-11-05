import parted  # https://www.gnu.org/software/parted/api/index.html


ARCH_RELENG_KEY = '4AA4767BBC9C4B1D18AE28B77F2D434B9741E8AC'
VERSION = '0.2.0'
EXTERNAL_DEPS = ['blkinfo',
                 'gpg',
                 'lxml',
                 'mdstat',
                 'passlib',
                 'psutil',
                 'pyparted',
                 'pyroute2',
                 'pytz',
                 'requests',
                 'validators']
# PARTED FLAG INDEXING
PARTED_FSTYPES = sorted(list(dict(vars(parted.filesystem))['fileSystemType'].keys()))
PARTED_FLAGS = sorted(list(parted.partition.partitionFlag.values()))
PARTED_IDX_FLAG = dict(parted.partition.partitionFlag)
PARTED_FLAG_IDX = {v: k for k, v in PARTED_IDX_FLAG.items()}
