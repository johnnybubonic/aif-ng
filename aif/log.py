import logging
import logging.handlers
import os
##
try:
    # https://www.freedesktop.org/software/systemd/python-systemd/journal.html#journalhandler-class
    from systemd import journal
    _has_journald = True
except ImportError:
    _has_journald = False
##
from . import constants_fallback

_cfg_args = {'handlers': [],
             'level': logging.DEBUG}  # TEMPORARY FOR TESTING
if _has_journald:
    # There were some weird changes somewhere along the line.
    try:
        # But it's *probably* this one.
        h = journal.JournalHandler()
    except AttributeError:
        h = journal.JournaldLogHandler()
    # Systemd includes times, so we don't need to.
    h.setFormatter(logging.Formatter(style = '{',
                                     fmt = ('{name}:{levelname}:{name}:{filename}:'
                                            '{funcName}:{lineno}: {message}')))
    _cfg_args['handlers'].append(h)
# Logfile
# Set up the permissions beforehand.
os.makedirs(os.path.dirname(constants_fallback.DEFAULT_LOGFILE), exist_ok = True)
os.chmod(constants_fallback.DEFAULT_LOGFILE, 0o0600)
h = logging.handlers.RotatingFileHandler(constants_fallback.DEFAULT_LOGFILE,
                                         encoding = 'utf8',
                                         # Disable rotating for now.
                                         # maxBytes = 50000000000,
                                         # backupCount = 30
                                         )
h.setFormatter(logging.Formatter(style = '{',
                                 fmt = ('{asctime}:'
                                        '{levelname}:{name}:{filename}:'
                                        '{funcName}:{lineno}: {message}')))
_cfg_args['handlers'].append(h)

logging.basicConfig(**_cfg_args)
logger = logging.getLogger()

logger.info('Logging initialized.')
