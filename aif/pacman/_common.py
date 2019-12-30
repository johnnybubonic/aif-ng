import configparser
import logging
from collections import OrderedDict


_logger = logging.getLogger('pacman:_common')


class MultiOrderedDict(OrderedDict):
    # Thanks, dude: https://stackoverflow.com/a/38286559/733214
    def __setitem__(self, key, value):
        if key in self:
            if isinstance(value, list):
                self[key].extend(value)
                return(None)
            elif isinstance(value, str):
                if len(self[key]) > 1:
                    return(None)
        super(MultiOrderedDict, self).__setitem__(key, value)
