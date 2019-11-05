try:
    from . import constants
except ImportError:
    from . import constants_fallback as constants

from . import utils
from . import disk
from . import system
from . import config
from . import envsetup
from . import log
from . import network
from . import pacman


class AIF(object):
    def __init__(self):
        pass
