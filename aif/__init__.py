try:
    from . import constants
except ImportError:
    from . import constants_fallback as constants
from . import constants_fallback
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
        # Process:
        # 0.) get config (already initialized at this point)
        # 1.) run pre scripts*
        # 2.) initialize all objects' classes
        # 3.) disk ops = partition, mount*
        # 3.) b.) "pivot" logging here. create <chroot>/root/aif/ and copy log to <chroot>/root/aif/aif.log, use that
        #         as new log file. copy over scripts.
        # 4.) install base system*
        # 4.) b.) other system.* tasks. locale(s), etc.*
        # 5.) run pkg scripts*
        # 6.) install kernel(?), pkg items*
        # 6.) b.) remember to install the .packages items for each object
        # 7.) write out confs and other object application methods*
        # * = log but don't do anything for dryrun
        pass
