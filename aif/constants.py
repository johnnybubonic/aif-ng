from .constants_fallback import *
##
# This creates a conflict of imports, unfortunately.
# So we end up doing the same thing in aif/disk/(__init__.py => _common.py)... C'est la vie.
# Patches welcome.
# import aif.disk._common
# _BlockDev = aif.disk._common.BlockDev
# aif.disk._common.addBDPlugin('part')
import gi
gi.require_version('BlockDev', '2.0')
from gi.repository import BlockDev as _BlockDev
from gi.repository import GLib
_BlockDev.ensure_init(_BlockDev.plugin_specs_from_names(('part', )))


# LIBBLOCKDEV FLAG INDEXING / PARTED <=> LIBBLOCKDEV FLAG CONVERSION
BD_PART_FLAGS = _BlockDev.PartFlag(-1)
BD_PART_FLAGS_FRIENDLY = dict(zip(BD_PART_FLAGS.value_nicks, BD_PART_FLAGS.value_names))
PARTED_BD_MAP = {v: k for k, v in BD_PARTED_MAP.items() if v is not None}
BD_PART_FLAGS_IDX_FLAG = {k: v.value_nicks[0] for k, v in BD_PART_FLAGS.__flags_values__.items()}
BD_PART_FLAGS_FLAG_IDX = {v: k for k, v in BD_PART_FLAGS_IDX_FLAG.items()}
