try:
    from . import constants
except ImportError:
    from . import constants_fallback as constants

from . import disk
from . import system
from . import config
from . import envsetup
from . import log
from . import network
from . import pacman
from . import utils




class AIF(object):
    def __init__(self):
        pass
