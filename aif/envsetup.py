# We use a temporary venv to ensure we have all the external libraries we need.
# This removes the necessity of extra libs at runtime. If you're in an environment that doesn't have access to PyPI/pip,
# you'll need to customize the install host (typically the live CD/live USB) to have them installed as system packages.
# Before you hoot and holler about this, Let's Encrypt's certbot-auto does the same thing.
# Except I segregate it out even further; I don't even install pip into the system python.

import ensurepip
import json
import os
import subprocess
import sys
import tempfile
import venv
##
import aif.constants_fallback

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
                                    stdout = subprocess.PIPE)
        self.modulesdir = json.loads(moddir_raw.stdout.decode('utf-8'))[0]
        # This is SO. DUMB. WHY DO I HAVE TO CALL PIP FROM A SHELL. IT'S WRITTEN IN PYTHON.
        # https://pip.pypa.io/en/stable/user_guide/#using-pip-from-your-program
        # TODO: logging
        for m in aif.constants_fallback.EXTERNAL_DEPS:
            pip_cmd = [os.path.join(self.vdir,
                                    'bin',
                                    'python3'),
                       '-m',
                       'pip',
                       'install',
                       '--disable-pip-version-check',
                       m]
            subprocess.run(pip_cmd)
        # And now make it available to other components.
        sys.path.insert(1, self.modulesdir)
