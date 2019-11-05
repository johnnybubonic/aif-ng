from .constants_fallback import *
##
import aif.disk._common
_BlockDev = aif.disk._common.BlockDev
aif.disk._common.addBDPlugin('part')


# LIBBLOCKDEV FLAG INDEXING / PARTED <=> LIBBLOCKDEV FLAG CONVERSION
BD_PART_FLAGS = _BlockDev.PartFlag(-1)
BD_PART_FLAGS_FRIENDLY = dict(zip(BD_PART_FLAGS.value_nicks, BD_PART_FLAGS.value_names))
BD_PARTED_MAP = {'apple_tv_recovery': 'atvrecv',
                 'cpalo': 'palo',
                 'gpt_hidden': None,  # ???
                 'gpt_no_automount': None,  # ???
                 'gpt_read_only': None,  # ???
                 'gpt_system_part': None,  # ???
                 'hpservice': 'hp-service',
                 'msft_data': 'msftdata',
                 'msft_reserved': 'msftres'}
PARTED_BD_MAP = {v: k for k, v in BD_PARTED_MAP.items() if v is not None}
BD_PART_FLAGS_IDX_FLAG = {k: v.value_nicks[0] for k, v in BD_PART_FLAGS.__flags_values__.items()}
BD_PART_FLAGS_FLAG_IDX = {v: k for k, v in BD_PART_FLAGS_IDX_FLAG.items()}
