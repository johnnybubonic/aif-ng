try:
    from . import _common
except ImportError:
    pass  # GI isn't supported, so we don't even use a fallback.

try:
    from . import block
except ImportError:
    from . import block_fallback as block

try:
    from . import filesystem
except ImportError:
    from . import filesystem_fallback as filesystem

try:
    from . import luks
except ImportError:
    from . import luks_fallback as luks

try:
    from . import lvm
except ImportError:
    from . import lvm_fallback as lvm

try:
    from . import mdadm
except ImportError:
    from . import mdadm_fallback as mdadm

from . import main
