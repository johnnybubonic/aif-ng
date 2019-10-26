import os
import re
##
import parted


PARTED_FSTYPES = list(dict(vars(parted.filesystem))['fileSystemType'].keys())

