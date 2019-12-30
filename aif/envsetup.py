# This can set up an environment at runtime.
# This removes the necessity of extra libs to be installed persistently.
# However, it is recommended that you install all dependencies in the system itself, because some aren't available
# through pip/PyPi.
# Before you hoot and holler about this, Let's Encrypt's certbot-auto does the same thing.
# Except I segregate it out even further; I don't even install pip into the system python.

import ensurepip
import json
import logging
import os
import subprocess
import sys
import tempfile
import venv
##
import aif.constants_fallback


_logger = logging.getLogger(__name__)


class EnvBuilder(object):
    def __init__(self):
        self.vdir = tempfile.mkdtemp(prefix = '.aif_', suffix = '_VENV')
        self.venv = venv.create(self.vdir, system_site_packages = True, clear = True, with_pip = True)
        ensurepip.bootstrap(root = self.vdir)
        # pip does some dumb env var things and doesn't clean up after itself.
        for v in ('PIP_CONFIG_FILE', 'ENSUREPIP_OPTIONS', 'PIP_REQ_TRACKER', 'PLAT'):
            if os.environ.get(v):
                del(os.environ[v])
        moddir_raw = subprocess.run([os.path.join(self.vdir,
                                                  'bin',
                                                  'python3'),
                                     '-c',
                                     ('import site; '
                                      'import json; '
                                      'print(json.dumps(site.getsitepackages(), indent = 4))')],
                                    stdout = subprocess.PIPE,
                                    stderr = subprocess.PIPE)
        _logger.info('Executed: {0}'.format(' '.join(moddir_raw.args)))
        if moddir_raw.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(moddir_raw.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(moddir_raw, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to establish environment successfully')
        self.modulesdir = json.loads(moddir_raw.stdout.decode('utf-8'))[0]
        # This is SO. DUMB. WHY DO I HAVE TO CALL PIP FROM A SHELL. IT'S WRITTEN IN PYTHON.
        # https://pip.pypa.io/en/stable/user_guide/#using-pip-from-your-program
        for m in aif.constants_fallback.EXTERNAL_DEPS:
            pip_cmd = [os.path.join(self.vdir,
                                    'bin',
                                    'python3'),
                       '-m',
                       'pip',
                       'install',
                       '--disable-pip-version-check',
                       m]
            cmd = subprocess.run(pip_cmd, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
            _logger.info('Executed: {0}'.format(' '.join(cmd.args)))
            if cmd.returncode != 0:
                _logger.warning('Command returned non-zero status')
                _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
                for a in ('stdout', 'stderr'):
                    x = getattr(cmd, a)
                    if x:
                        _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
                raise RuntimeError('Failed to install module successfully')
        # And now make it available to other components.
        sys.path.insert(1, self.modulesdir)
