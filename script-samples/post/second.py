#!/usr/bin/env python

import os
from urllib.request import urlopen

# You'll probably definitely want to change this. Unless you want to give me SSH access.
keyfile = 'https://square-r00t.net/ssh/all'

keydir = '/root/.ssh'

os.makedirs(keydir, exist_ok = True)
os.chown(keydir, 0, 0)
os.chmod(keydir, 0o700)

with open('{0}/authorized_keys'.format(keydir), 'w') as f:
    with urlopen(keyfile) as url:
        f.write(url.read().decode('utf-8'))

os.chown('{0}/authorized_keys'.format(keydir), 0, 0)
os.chmod('{0}/authorized_keys'.format(keydir), 0o600)
