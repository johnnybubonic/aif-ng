#!/usr/bin/env python3

import os
import re
import subprocess
import uuid
##
import requests
from bs4 import BeautifulSoup

# You, the average user, will probably have absolutely no use for this.

types = {'gpt': {'local': [],
                 'wiki': {}},
         'msdos': {'local': [],
                   'src': []}}

# GPT
cmd = ['/usr/bin/sfdisk', '--list-types', '--label=gpt']
url = 'https://en.wikipedia.org/wiki/GUID_Partition_Table'
# First get the local list.
with open(os.devnull, 'wb') as devnull:
    cmd_out = subprocess.run(cmd, stdout = subprocess.PIPE, stderr = devnull)
stdout = [i for i in cmd_out.stdout.decode('utf-8').splitlines() if i not in ('Id  Name', '')]
for idx, line in enumerate(stdout):
    i = idx + 1
    l = line.split()
    u = l.pop(0)
    desc = ' '.join(l)
    types['gpt']['local'].append((i, desc, uuid.UUID(hex = u)))
# Then wikipedia.
req = requests.get(url)
if not req.ok:
    raise RuntimeError('Could not access {0}'.format(url))
soup = BeautifulSoup(req.content, 'lxml')
tbl = soup.find('span', attrs = {'id': 'Partition_type_GUIDs', 'class': 'mw-headline'}).findNext('table').find('tbody')
c = None
t = None
idx = 1
strip_ref = re.compile(r'(?P<name>[A-Za-z\s()/0-9,.+-]+)\[?.*')
for row in tbl.find_all('tr'):
    cols = [e.text.strip() for e in row.find_all('td')]
    if not cols:
        continue
    if len(cols) == 3:
        temp_c = strip_ref.search(cols[0].strip())
        if not temp_c:
            raise RuntimeError('Error when parsing/regexing: {0}'.format(cols[0].strip()))
        c = temp_c.group('name')
        cols.pop(0).strip()
        if c not in types['gpt']['wiki']:
            types['gpt']['wiki'][c] = []
    if len(cols) == 2:
        temp_t = strip_ref.search(cols[0].strip())
        if not temp_t:
            raise RuntimeError('Error when parsing/regexing: {0}'.format(cols[0].strip()))
        t = temp_t.group('name')
        cols.pop(0)
    u = cols[0]
    types['gpt']['wiki'][c].append((idx, t, uuid.UUID(hex = u)))
    idx += 1

# MSDOS
cmd = ['/usr/bin/sfdisk', '--list-types', '--label=dos']
url = 'https://git.kernel.org/pub/scm/utils/util-linux/util-linux.git/plain/include/pt-mbr-partnames.h'
with open(os.devnull, 'wb') as devnull:
    cmd_out = subprocess.run(cmd, stdout = subprocess.PIPE, stderr = devnull)
stdout = [i for i in cmd_out.stdout.decode('utf-8').splitlines() if i not in ('Id  Name', '')]
for idx, line in enumerate(stdout):
    i = idx + 1
    l = line.split()
    b = '{0:0>2}'.format(l.pop(0).upper())
    desc = ' '.join(l)
    types['msdos']['local'].append((i, desc, bytes.fromhex(b)))
# Then the source (master branch's HEAD). It gets messy but whatever. This is actually something unique to fdisk.
req = requests.get(url)
if not req.ok:
    raise RuntimeError('Could not access {0}'.format(url))
line_re = re.compile(r'^\s+{0x')
str_re = re.compile(r'^\s+{0x(?P<b>[A-Fa-f0-9]+),\s*N_\("(?P<desc>[^"]+)"\).*')
idx = 1
for line in req.content.decode('utf-8').splitlines():
    if not line_re.search(line):
        continue
    s = str_re.search(line)
    if not s:
        raise RuntimeError('Error when parsing/regexing: {0}'.format(line.strip()))
    b = s.group('b').upper()
    desc = s.group('desc')
    types['msdos']['src'].append((idx, desc, bytes.fromhex(b)))
    idx += 1

print(types)
