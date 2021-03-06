#!/usr/bin/env python3

## REQUIRES: ##
# parted  #
# sgdisk  ### (yes, both)
# python 3 with standard library
# (OPTIONAL) lxml
# pacman in the host environment
# arch-install-scripts: https://www.archlinux.org/packages/extra/any/arch-install-scripts/
# a network connection
# the proper kernel arguments.

try:
    from lxml import etree
    lxml_avail = True
except ImportError:
    import xml.etree.ElementTree as etree  # https://docs.python.org/3/library/xml.etree.elementtree.html
    lxml_avail = False
import datetime
import shlex
import fileinput
import os
import shutil
import re
import socket
import subprocess
import ipaddress
import copy
import urllib.request as urlrequest
import urllib.parse as urlparse
import urllib.response as urlresponse
from ftplib import FTP_TLS
from io import StringIO

logfile = '/root/aif.log.{0}'.format(int(datetime.datetime.utcnow().timestamp()))

class aif(object):
    
    def __init__(self):
        pass
    
    def kernelargs(self):
        if 'DEBUG' in os.environ.keys():
            kernelparamsfile = '/tmp/cmdline'
        else:
            kernelparamsfile = '/proc/cmdline'
        args = {}
        args['aif'] = False
        # For FTP or HTTP auth
        args['aif_user'] = False
        args['aif_password'] = False
        args['aif_auth'] = False
        args['aif_realm'] = False
        args['aif_auth'] = 'basic'
        with open(kernelparamsfile, 'r') as f:
            cmdline = f.read()
            for p in shlex.split(cmdline):
                if p.startswith('aif'):
                    param = p.split('=')
                    if len(param) == 1:
                        param.append(True)
                    args[param[0]] = param[1]
        if not args['aif']:
            exit('You do not have AIF enabled. Exiting.')
        args['aif_auth'] = args['aif_auth'].lower()
        return(args)
    
    def getConfig(self, args = False):
        if not args:
            args = self.kernelargs()
        # Sanitize the user specification and find which protocol to use
        prefix = args['aif_url'].split(':')[0].lower()
        # Use the urllib module
        if prefix in ('http', 'https', 'file', 'ftp'):
            if args['aif_user'] and args['aif_password']:
                # Set up Basic or Digest auth.
                passman = urlrequest.HTTPPasswordMgrWithDefaultRealm()
                if not args['aif_realm']:
                    passman.add_password(None, args['aif_url'], args['aif_user'], args['aif_password'])
                else:
                    passman.add_password(args['aif_realm'], args['aif_url'], args['aif_user'], args['aif_password'])
                if args['aif_auth'] == 'digest':
                    httpauth = urlrequest.HTTPDigestAuthHandler(passman)
                else:
                    httpauth = urlrequest.HTTPBasicAuthHandler(passman)
                httpopener = urlrequest.build_opener(httpauth)
                urlrequest.install_opener(httpopener)
            with urlrequest.urlopen(args['aif_url']) as f:
                conf = f.read()
        elif prefix == 'ftps':
            if args['aif_user']:
                username = args['aif_user']
            else:
                username = 'anonymous'
            if args['aif_password']:
                password = args['aif_password']
            else:
                password = 'anonymous'
            filepath = '/'.join(args['aif_url'].split('/')[3:])
            server = args['aif_url'].split('/')[2]
            content = StringIO()
            ftps = FTP_TLS(server)
            ftps.login(username, password)
            ftps.prot_p()
            ftps.retrlines("RETR " + filepath, content.write)
            conf = content.getvalue()
        else:
            exit('{0} is not a recognised URI type specifier. Must be one of http, https, file, ftp, or ftps.'.format(prefix))
        return(conf)

    def webFetch(self, uri, auth = False):
        # Sanitize the user specification and find which protocol to use
        prefix = uri.split(':')[0].lower()
        # Use the urllib module
        if prefix in ('http', 'https', 'file', 'ftp'):
            if auth:
                if 'user' in auth.keys() and 'password' in auth.keys():
                    # Set up Basic or Digest auth.
                    passman = urlrequest.HTTPPasswordMgrWithDefaultRealm()
                    if not 'realm' in auth.keys():
                        passman.add_password(None, uri, auth['user'], auth['password'])
                    else:
                        passman.add_password(auth['realm'], uri, auth['user'], auth['password'])
                    if auth['type'] == 'digest':
                        httpauth = urlrequest.HTTPDigestAuthHandler(passman)
                    else:
                        httpauth = urlrequest.HTTPBasicAuthHandler(passman)
                    httpopener = urlrequest.build_opener(httpauth)
                    urlrequest.install_opener(httpopener)
            with urlrequest.urlopen(uri) as f:
                data = f.read()
        elif prefix == 'ftps':
            if auth:
                if 'user' in auth.keys():
                    username = auth['user']
                else:
                    username = 'anonymous'
                if 'password' in auth.keys():
                    password = auth['password']
                else:
                    password = 'anonymous'
            filepath = '/'.join(uri.split('/')[3:])
            server = uri.split('/')[2]
            content = StringIO()
            ftps = FTP_TLS(server)
            ftps.login(username, password)
            ftps.prot_p()
            ftps.retrlines("RETR " + filepath, content.write)
            data = content.getvalue()
        else:
            exit('{0} is not a recognised URI type specifier. Must be one of http, https, file, ftp, or ftps.'.format(prefix))
        return(data)

    def getXML(self, confobj = False):
        if not confobj:
            confobj = self.getConfig()
        xmlobj = etree.fromstring(confobj)
        return(xmlobj)
    
    def buildDict(self, xmlobj = False):
        if not xmlobj:
            xmlobj = self.getXML()
        # Set up the skeleton dicts
        aifdict = {}
        for i in ('disk', 'mount', 'network', 'system', 'users', 'software', 'scripts'):
            aifdict[i] = {}
        for i in ('network.ifaces', 'system.bootloader', 'system.services', 'users.root'):
            i = i.split('.')
            dictname = i[0]
            keyname = i[1]
            aifdict[dictname][keyname] = {}
        aifdict['scripts']['pre'] = False
        aifdict['scripts']['post'] = False
        aifdict['users']['root']['password'] = False
        for i in ('repos', 'mirrors', 'packages'):
            aifdict['software'][i] = {}
        # Set up the dict elements for disk partitioning
        for i in xmlobj.findall('storage/disk'):
            disk = i.attrib['device']
            fmt = i.attrib['diskfmt'].lower()
            if not fmt in ('gpt', 'bios'):
                exit('Device {0}\'s format "{1}" is not a valid type (one of gpt, bios).'.format(disk,
                                                                                                fmt))
            aifdict['disk'][disk] = {}
            aifdict['disk'][disk]['fmt'] = fmt
            aifdict['disk'][disk]['parts'] = {}
            for x in i:
                if x.tag == 'part':
                    partnum = x.attrib['num']
                    aifdict['disk'][disk]['parts'][partnum] = {}
                    for a in x.attrib:
                        aifdict['disk'][disk]['parts'][partnum][a] = x.attrib[a]
        # Set up mountpoint dicts
        for i in xmlobj.findall('storage/mount'):
            device = i.attrib['source']
            mntpt = i.attrib['target']
            order = int(i.attrib['order'])
            if 'fstype' in i.keys():
                fstype = i.attrib['fstype']
            else:
                fstype = None
            if 'opts' in i.keys():
                opts = i.attrib['opts']
            else:
                opts = None
            aifdict['mount'][order] = {}
            aifdict['mount'][order]['device'] = device
            aifdict['mount'][order]['mountpt'] = mntpt
            aifdict['mount'][order]['fstype'] = fstype
            aifdict['mount'][order]['opts'] = opts
        # Set up networking dicts
        aifdict['network']['hostname'] = xmlobj.find('network').attrib['hostname']
        for i in xmlobj.findall('network/iface'):
            # Create a dict for the iface name.
            iface = i.attrib['device']
            proto = i.attrib['netproto']
            address = i.attrib['address']
            if 'gateway' in i.attrib.keys():
                gateway = i.attrib['gateway']
            else:
                gateway = False
            if 'resolvers' in i.attrib.keys():
                resolvers = i.attrib['resolvers']
            else:
                resolvers = False
            if iface not in aifdict['network']['ifaces'].keys():
                aifdict['network']['ifaces'][iface] = {}
            if proto not in aifdict['network']['ifaces'][iface].keys():
                aifdict['network']['ifaces'][iface][proto] = {}
            if 'gw' not in aifdict['network']['ifaces'][iface][proto].keys():
                aifdict['network']['ifaces'][iface][proto]['gw'] = gateway
            aifdict['network']['ifaces'][iface][proto]['addresses'] = []
            aifdict['network']['ifaces'][iface][proto]['addresses'].append(address)
            aifdict['network']['ifaces'][iface]['resolvers'] = []
            if resolvers:
                for ip in filter(None, re.split('[,\s]+', resolvers)):
                    if ip not in aifdict['network']['ifaces'][iface]['resolvers']:
                        aifdict['network']['ifaces'][iface]['resolvers'].append(ip)
            else:
                aifdict['network']['ifaces'][iface][proto]['resolvers'] = False
        # Set up the users dicts
        aifdict['users']['root']['password'] = xmlobj.find('system/users').attrib['rootpass']
        for i in xmlobj.findall('system/users'):
            for x in i:
                username = x.attrib['name']
                aifdict['users'][username] = {} 
                for a in ('uid', 'group', 'gid', 'password', 'comment', 'sudo'):
                    if a in x.attrib.keys():
                        aifdict['users'][username][a] = x.attrib[a]
                    else:
                        aifdict['users'][username][a] = None
                sudo = (x.attrib['sudo']).lower() in ('true', '1')
                aifdict['users'][username]['sudo'] = sudo
                # And we also need to handle the homedir and xgroup situation
                for n in ('home', 'xgroup'):
                    aifdict['users'][username][n] = False
                for a in x:
                    if not aifdict['users'][username][a.tag]:
                        aifdict['users'][username][a.tag] = {}
                    for b in a.attrib:
                        if a.tag == 'xgroup':
                            if b == 'name':
                                groupname = a.attrib[b]
                                if groupname not in aifdict['users'][username]['xgroup'].keys():
                                    aifdict['users'][username]['xgroup'][a.attrib[b]] = {}
                            else:
                                aifdict['users'][username]['xgroup'][a.attrib['name']][b] = a.attrib[b]
                        else:
                            aifdict['users'][username][a.tag][b] = a.attrib[b]
                # And fill in any missing values. We could probably use the XSD and use of defaults to do this, but... oh well.
                if isinstance(aifdict['users'][username]['xgroup'], dict):
                    for g in aifdict['users'][username]['xgroup'].keys():
                        for k in ('create', 'gid'):
                            if k not in aifdict['users'][username]['xgroup'][g].keys():
                                aifdict['users'][username]['xgroup'][g][k] = False
                            elif k == 'create':
                                aifdict['users'][username]['xgroup'][g][k] = aifdict['users'][username]['xgroup'][g][k].lower() in ('true', '1')
                if isinstance(aifdict['users'][username]['home'], dict):
                    for k in ('path', 'create'):
                        if k not in aifdict['users'][username]['home'].keys():
                            aifdict['users'][username]['home'][k] = False
                        elif k == 'create':
                            aifdict['users'][username]['home'][k] = aifdict['users'][username]['home'][k].lower() in ('true', '1')
        # Set up the system settings, if applicable.
        aifdict['system']['timezone'] = False
        aifdict['system']['locale'] = False
        aifdict['system']['kbd'] = False
        aifdict['system']['chrootpath'] = False
        aifdict['system']['reboot'] = False
        for i in ('locale', 'timezone', 'kbd', 'chrootpath', 'reboot'):
            if i in xmlobj.find('system').attrib:
                aifdict['system'][i] = xmlobj.find('system').attrib[i]
        aifdict['system']['reboot'] = aifdict['system']['reboot'].lower() in ('true', '1')
        # And now services...
        if xmlobj.find('system/service') is None:
            aifdict['system']['services'] = False
        else:
            for x in xmlobj.findall('system/service'):
                svcname = x.attrib['name']
                state = x.attrib['status'].lower() in ('true', '1')
                aifdict['system']['services'][svcname] = {}
                aifdict['system']['services'][svcname]['status'] = state
        # And software. First the mirror list.
        if xmlobj.find('pacman/mirrorlist') is None:
            aifdict['software']['mirrors'] = False
        else:
            aifdict['software']['mirrors'] = []
            for x in xmlobj.findall('pacman/mirrorlist'):
                for i in x:
                    aifdict['software']['mirrors'].append(i.text)
        # Then the command
        if 'command' in xmlobj.find('pacman').attrib:
            aifdict['software']['command'] = xmlobj.find('pacman').attrib['command']
        else:
            aifdict['software']['command'] = False
        # And then the repo list.
        for x in xmlobj.findall('pacman/repos/repo'):
            repo = x.attrib['name']
            aifdict['software']['repos'][repo] = {}
            aifdict['software']['repos'][repo]['enabled'] = x.attrib['enabled'].lower() in ('true', '1')
            aifdict['software']['repos'][repo]['siglevel'] = x.attrib['siglevel']
            aifdict['software']['repos'][repo]['mirror'] = x.attrib['mirror']
        # And packages.
        if xmlobj.find('pacman/software') is None:
            aifdict['software']['packages'] = False
        else:
            aifdict['software']['packages'] = {}
            for x in xmlobj.findall('pacman/software/package'):
                aifdict['software']['packages'][x.attrib['name']] = {}
                if 'repo' in x.attrib:
                    aifdict['software']['packages'][x.attrib['name']]['repo'] = x.attrib['repo']
                else:
                    aifdict['software']['packages'][x.attrib['name']]['repo'] = None
        # The bootloader setup...
        for x in xmlobj.find('bootloader').attrib:
            aifdict['system']['bootloader'][x] = xmlobj.find('bootloader').attrib[x]
        # The script setup...
        if xmlobj.find('scripts') is not None:
            aifdict['scripts']['pre'] = []
            aifdict['scripts']['post'] = []
            aifdict['scripts']['pkg'] = []
            tempscriptdict = {'pre': {}, 'post': {}, 'pkg': {}}
            for x in xmlobj.find('scripts'):
                if all(keyname in list(x.attrib.keys()) for keyname in ('user', 'password')):
                    auth = {}
                    auth['user'] = x.attrib['user']
                    auth['password'] = x.attrib['password']
                    if 'realm' in x.attrib.keys():
                        auth['realm'] = x.attrib['realm']
                    if 'authtype' in x.attrib.keys():
                        auth['type'] = x.attrib['authtype']
                    scriptcontents = self.webFetch(x.attrib['uri'], auth).decode('utf-8')
                else:
                    scriptcontents = self.webFetch(x.attrib['uri']).decode('utf-8')
                tempscriptdict[x.attrib['execution']][x.attrib['order']] = scriptcontents
            for d in ('pre', 'post', 'pkg'):
                keylst = list(tempscriptdict[d].keys())
                keylst.sort()
                for s in keylst:
                    aifdict['scripts'][d].append(tempscriptdict[d][s])
        return(aifdict)

class archInstall(object):
    def __init__(self, aifdict):
        for k, v in aifdict.items():
            setattr(self, k, v)

    def format(self):
        # NOTE: the following is a dict of fstype codes to their description.
        fstypes = {'0700': 'Microsoft basic data', '0c01': 'Microsoft reserved', '2700': 'Windows RE', '3000': 'ONIE config', '3900': 'Plan 9', '4100': 'PowerPC PReP boot', '4200': 'Windows LDM data', '4201': 'Windows LDM metadata', '4202': 'Windows Storage Spaces', '7501': 'IBM GPFS', '7f00': 'ChromeOS kernel', '7f01': 'ChromeOS root', '7f02': 'ChromeOS reserved', '8200': 'Linux swap', '8300': 'Linux filesystem', '8301': 'Linux reserved', '8302': 'Linux /home', '8303': 'Linux x86 root (/)', '8304': 'Linux x86-64 root (/', '8305': 'Linux ARM64 root (/)', '8306': 'Linux /srv', '8307': 'Linux ARM32 root (/)', '8400': 'Intel Rapid Start', '8e00': 'Linux LVM', 'a500': 'FreeBSD disklabel', 'a501': 'FreeBSD boot', 'a502': 'FreeBSD swap', 'a503': 'FreeBSD UFS', 'a504': 'FreeBSD ZFS', 'a505': 'FreeBSD Vinum/RAID', 'a580': 'Midnight BSD data', 'a581': 'Midnight BSD boot', 'a582': 'Midnight BSD swap', 'a583': 'Midnight BSD UFS', 'a584': 'Midnight BSD ZFS', 'a585': 'Midnight BSD Vinum', 'a600': 'OpenBSD disklabel', 'a800': 'Apple UFS', 'a901': 'NetBSD swap', 'a902': 'NetBSD FFS', 'a903': 'NetBSD LFS', 'a904': 'NetBSD concatenated', 'a905': 'NetBSD encrypted', 'a906': 'NetBSD RAID', 'ab00': 'Recovery HD', 'af00': 'Apple HFS/HFS+', 'af01': 'Apple RAID', 'af02': 'Apple RAID offline', 'af03': 'Apple label', 'af04': 'AppleTV recovery', 'af05': 'Apple Core Storage', 'bc00': 'Acronis Secure Zone', 'be00': 'Solaris boot', 'bf00': 'Solaris root', 'bf01': 'Solaris /usr & Mac ZFS', 'bf02': 'Solaris swap', 'bf03': 'Solaris backup', 'bf04': 'Solaris /var', 'bf05': 'Solaris /home', 'bf06': 'Solaris alternate sector', 'bf07': 'Solaris Reserved 1', 'bf08': 'Solaris Reserved 2', 'bf09': 'Solaris Reserved 3', 'bf0a': 'Solaris Reserved 4', 'bf0b': 'Solaris Reserved 5', 'c001': 'HP-UX data', 'c002': 'HP-UX service', 'ea00': 'Freedesktop $BOOT', 'eb00': 'Haiku BFS', 'ed00': 'Sony system partition', 'ed01': 'Lenovo system partition', 'ef00': 'EFI System', 'ef01': 'MBR partition scheme', 'ef02': 'BIOS boot partition', 'f800': 'Ceph OSD', 'f801': 'Ceph dm-crypt OSD', 'f802': 'Ceph journal', 'f803': 'Ceph dm-crypt journal', 'f804': 'Ceph disk in creation', 'f805': 'Ceph dm-crypt disk in creation', 'fb00': 'VMWare VMFS', 'fb01': 'VMWare reserved', 'fc00': 'VMWare kcore crash protection', 'fd00': 'Linux RAID'}
        # We want to build a mapping of commands to run after partitioning. This will be fleshed out in the future to hopefully include more.
        formatting = {}
        # TODO: we might want to provide a way to let users specify extra options here.
        # TODO: label support?
        formatting['ef00'] = ['mkfs.vfat', '-F', '32', '%PART%']
        formatting['ef01'] = formatting['ef00']
        formatting['ef02'] = formatting['ef00']
        formatting['8200'] = ['mkswap', '-c', '%PART%']
        formatting['8300'] = ['mkfs.ext4', '-c', '-q', '%PART%']  # some people are DEFINITELY not going to be happy about this. we need to figure out a better way to customize this.
        for fs in ('8301', '8302', '8303', '8304', '8305', '8306', '8307'):
            formatting[fs] = formatting['8300']
        #formatting['8e00'] = FOO  # TODO: LVM configuration
        #formatting['fd00'] = FOO  # TODO: MDADM configuration
        cmds = []
        for d in self.disk:
            partnums = [int(x) for x in self.disk[d]['parts'].keys()]
            partnums.sort()
            cmds.append(['sgdisk', '-Z', d])
            if self.disk[d]['fmt'] == 'gpt':
                diskfmt = 'gpt'
                if len(partnums) >= 129 or partnums[-1] >= 129:
                    exit('GPT only supports 128 partitions (and partition allocations).')
                cmds.append(['sgdisk', '-og', d])
            elif self.disk[d]['fmt'] == 'bios':
                diskfmt = 'msdos'
                cmds.append(['sgdisk', '-om', d])
            cmds.append(['parted', d, '--script', '-a', 'optimal'])
            with open(logfile, 'a') as log:
                for c in cmds:
                    subprocess.call(c, stdout = log, stderr = subprocess.STDOUT)
            cmds = []
            disksize = {}
            disksize['start'] = subprocess.check_output(['sgdisk', '-F', d])
            disksize['max'] = subprocess.check_output(['sgdisk', '-E', d])
            for p in partnums:
                # Need to do some mathz to get the actual sectors if we're using percentages.
                for s in ('start', 'stop'):
                    val = self.disk[d]['parts'][str(p)][s]
                    if '%' in val:
                        stripped = val.replace('%', '')
                        modifier = re.sub('[0-9]+%', '', val)
                        percent = re.sub('(-|\+)*', '', stripped)
                        decimal = float(percent) / float(100)
                        newval = int(float(disksize['max']) * decimal)
                        if s == 'start':
                            newval = newval + int(disksize['start'])
                        self.disk[d]['parts'][str(p)][s] = modifier + str(newval)
            if self.disk[d]['fmt'] == 'gpt':
                for p in partnums:
                    size = {}
                    size['start'] = self.disk[d]['parts'][str(p)]['start']
                    size['end'] = self.disk[d]['parts'][str(p)]['stop']
                    fstype = self.disk[d]['parts'][str(p)]['fstype'].lower()
                    if fstype not in fstypes.keys():
                        print('Filesystem type {0} is not valid. Must be a code from:\nCODE:FILESYSTEM'.format(fstype))
                        for k, v in fstypes.items():
                            print(k + ":" + v)
                        exit()
                    cmds.append(['sgdisk',
                                 '-n', '{0}:{1}:{2}'.format(str(p),
                                                            self.disk[d]['parts'][str(p)]['start'],
                                                            self.disk[d]['parts'][str(p)]['stop']),
                                 #'-c', '{0}:"{1}"'.format(str(p), self.disk[d]['parts'][str(p)]['label']),  # TODO: add support for partition labels
                                 '-t', '{0}:{1}'.format(str(p), fstype),
                                 d])
                    mkformat = formatting[fstype]
                    for x, y in enumerate(mkformat):
                        if y == '%PART%':
                            mkformat[x] = d + str(p)
                    cmds.append(mkformat)
                # TODO: add non-gpt stuff here?
        with open(logfile, 'a') as log:
            for p in cmds:
                subprocess.call(p, stdout = log, stderr = subprocess.STDOUT)
            usermntidx = list(self.mount.keys())
            usermntidx.sort()  # We want to make sure we do this in order.
            for k in usermntidx:
                if self.mount[k]['mountpt'] == 'swap':
                    subprocess.call(['swapon', self.mount[k]['device']], stdout = log, stderr = subprocess.STDOUT)
                else:
                    os.makedirs(self.mount[k]['mountpt'], exist_ok = True)
                    os.chown(self.mount[k]['mountpt'], 0, 0)
                    cmd = ['mount']
                    if self.mount[k]['fstype']:
                        cmd.extend(['-t', self.mount[k]['fstype']])
                    if self.mount[k]['opts']:
                        cmd.extend(['-o', self.mount[k]['opts']])
                    cmd.extend([self.mount[k]['device'], self.mount[k]['mountpt']])
                    subprocess.call(cmd, stdout = log, stderr = subprocess.STDOUT)
        return()

    def mounts(self):
        mntorder = list(self.mount.keys())
        mntorder.sort()
        for m in mntorder:
            mnt = self.mount[m]
            if mnt['mountpt'].lower() == 'swap':
                cmd = ['swapon', mnt['device']]
            else:
                cmd = ['mount', mnt['device'], mnt['mountpt']]
                if mnt['opts']:
                    cmd.insert(1, '-o {0}'.format(mnt['opts']))
                if mnt['fstype']:
                    cmd.insert(1, '-t {0}'.format(mnt['fstype']))
#        with open(os.devnull, 'w') as DEVNULL:
#            for p in cmd:
#                subprocess.call(p, stdout = DEVNULL, stderr = subprocess.STDOUT)
        # And we need to add some extra mounts to support a chroot. We also need to know what was mounted before.
        with open('/proc/mounts', 'r') as f:
            procmounts = f.read()
        mountlist = {}
        for i in procmounts.splitlines():
            mountlist[i.split()[1]] = i
        cmounts = {}
        for m in ('chroot', 'resolv', 'proc', 'sys', 'efi', 'dev', 'pts', 'shm', 'run', 'tmp'):
            cmounts[m] = None
        chrootdir = self.system['chrootpath']
        # chroot (bind mount... onto itself. it's so stupid, i know. see https://bugs.archlinux.org/task/46169)
        if chrootdir not in mountlist.keys():
            cmounts['chroot'] = ['mount', '--bind', chrootdir, chrootdir]
        # resolv.conf (for DNS resolution in the chroot) 
        if (chrootdir + '/etc/resolv.conf') not in mountlist.keys():
            cmounts['resolv'] = ['/bin/mount', '--bind', '-o', 'ro', '/etc/resolv.conf', chrootdir + '/etc/resolv.conf']
        # proc
        if (chrootdir + '/proc') not in mountlist.keys():
            cmounts['proc'] = ['/bin/mount', '-t', 'proc', '-o', 'nosuid,noexec,nodev', 'proc', chrootdir + '/proc']
        # sys
        if (chrootdir + '/sys') not in mountlist.keys():
            cmounts['sys'] = ['/bin/mount', '-t', 'sysfs', '-o', 'nosuid,noexec,nodev,ro', 'sys', chrootdir + '/sys']
        # efi (if it exists on the host)
        if '/sys/firmware/efi/efivars' in mountlist.keys():
            if (chrootdir + '/sys/firmware/efi/efivars') not in mountlist.keys():
                cmounts['efi'] = ['/bin/mount', '-t', 'efivarfs', '-o', 'nosuid,noexec,nodev', 'efivarfs', chrootdir + '/sys/firmware/efi/efivars']
        # dev
        if (chrootdir + '/dev') not in mountlist.keys():
            cmounts['dev'] = ['/bin/mount', '-t', 'devtmpfs', '-o', 'mode=0755,nosuid', 'udev', chrootdir + '/dev']
        # pts
        if (chrootdir + '/dev/pts') not in mountlist.keys():
            cmounts['pts'] = ['/bin/mount', '-t', 'devpts', '-o', 'mode=0620,gid=5,nosuid,noexec', 'devpts', chrootdir + '/dev/pts']
        # shm (if it exists on the host)
        if '/dev/shm' in mountlist.keys():
            if (chrootdir + '/dev/shm') not in mountlist.keys():
                cmounts['shm'] = ['/bin/mount', '-t', 'tmpfs', '-o', 'mode=1777,nosuid,nodev', 'shm', chrootdir + '/dev/shm']
        # run (if it exists on the host)
        if '/run' in mountlist.keys():
            if (chrootdir + '/run') not in mountlist.keys():
                cmounts['run'] = ['/bin/mount', '-t', 'tmpfs', '-o', 'nosuid,nodev,mode=0755', 'run', chrootdir + '/run']
        # tmp (if it exists on the host)
        if '/tmp' in mountlist.keys():
            if (chrootdir + '/tmp') not in mountlist.keys():
                cmounts['tmp'] = ['/bin/mount', '-t', 'tmpfs', '-o', 'mode=1777,strictatime,nodev,nosuid', 'tmp', chrootdir + '/tmp']
        # Because the order of these mountpoints is so ridiculously important, we hardcode it.
        # Yeah, python 3.6 has ordered dicts, but do we really want to risk it?
        # Okay. So we finally have all the mounts bound. Whew.
        return(cmounts)
    
    def setup(self, mounts = False):
        # TODO: could we leverage https://github.com/hartwork/image-bootstrap somehow? I want to keep this close
        # to standard Python libs, though, to reduce dependency requirements.
        hostscript = []
        chrootcmds = []
        locales = []
        locale = []
        if not mounts:
            mounts = self.mounts()
        # Get the necessary fstab additions for the guest
        chrootfstab = subprocess.check_output(['genfstab', '-U', self.system['chrootpath']])
        # Set up the time, and then kickstart the guest install.
        hostscript.append(['timedatectl', 'set-ntp', 'true'])
        # Also start haveged if we have it.
        try:
            with open(os.devnull, 'w') as devnull:
                subprocess.call(['haveged'], stderr = devnull)
        except:
            pass
        # Make sure we get the keys, in case we're running from a minimal live env.
        hostscript.append(['pacman-key', '--init'])
        hostscript.append(['pacman-key', '--populate'])
        hostscript.append(['pacstrap', self.system['chrootpath'], 'base'])
        # Run the basic host prep
        #with open(os.devnull, 'w') as DEVNULL:
        with open(logfile, 'a') as log:
            for c in hostscript:
                subprocess.call(c, stdout = log, stderr = subprocess.STDOUT)
        with open('{0}/etc/fstab'.format(self.system['chrootpath']), 'a') as f:
            f.write('# Generated by AIF-NG.\n')
            f.write(chrootfstab.decode('utf-8'))
        with open(logfile, 'a') as log:
            for m in ('resolv', 'proc', 'sys', 'efi', 'dev', 'pts', 'shm', 'run', 'tmp'):
                if mounts[m]:
                    subprocess.call(mounts[m], stdout = log, stderr = subprocess.STDOUT)

        # Validating this would be better with pytz, but it's not stdlib. dateutil would also work, but same problem.
        # https://stackoverflow.com/questions/15453917/get-all-available-timezones
        tzlist = subprocess.check_output(['timedatectl', 'list-timezones']).decode('utf-8').splitlines()
        if self.system['timezone'] not in tzlist:
            print('WARNING (non-fatal): {0} does not seem to be a valid timezone, but we\'re continuing anyways.'.format(self.system['timezone']))
        tzfile = '{0}/etc/localtime'.format(self.system['chrootpath'])
        if os.path.lexists(tzfile):
            os.remove(tzfile)
        os.symlink('/usr/share/zoneinfo/{0}'.format(self.system['timezone']), tzfile)
        # This is an ugly hack. TODO: find a better way of determining if the host is set to UTC in the RTC. maybe the datetime module can do it.
        utccheck = subprocess.check_output(['timedatectl', 'status']).decode('utf-8').splitlines()
        utccheck = [x.strip(' ') for x in utccheck]
        for i, v in enumerate(utccheck):
            if v.startswith('RTC in local'):
                utcstatus = (v.split(': ')[1]).lower() in ('yes')
                break
        if utcstatus:
            chrootcmds.append(['hwclock', '--systohc'])
        # We need to check the locale, and set up locale.gen.
        with open('{0}/etc/locale.gen'.format(self.system['chrootpath']), 'r') as f:
            localeraw = f.readlines()
        for line in localeraw:
            if not line.startswith('# '):  # Comments, thankfully, have a space between the leading octothorpe and the comment. Locales have no space.
                i = line.strip().strip('#')
                if i != '':  # We also don't want blank entries. Keep it clean, folks.
                    locales.append(i)
        for i in locales:
            localelst = i.split()
            if localelst[0].lower().startswith(self.system['locale'].lower()):
                locale.append(' '.join(localelst).strip())
        for i, v in enumerate(localeraw):
            for x in locale:
                if v.startswith('#{0}'.format(x)):
                    localeraw[i] = x + '\n'
        with open('{0}/etc/locale.gen'.format(self.system['chrootpath']), 'w') as f:
            f.write('# Modified by AIF-NG.\n')
            f.write(''.join(localeraw))
        with open('{0}/etc/locale.conf'.format(self.system['chrootpath']), 'a') as f:
            f.write('# Added by AIF-NG.\n')
            f.write('LANG={0}\n'.format(locale[0].split()[0]))
        chrootcmds.append(['locale-gen'])
        # Set up the kbd layout.
        # Currently there is NO validation on this. TODO.
        if self.system['kbd']:
            with open('{0}/etc/vconsole.conf'.format(self.system['chrootpath']), 'a') as f:
                f.write('# Generated by AIF-NG.\nKEYMAP={0}\n'.format(self.system['kbd']))
        # Set up the hostname.
        with open('{0}/etc/hostname'.format(self.system['chrootpath']), 'w') as f:
            f.write('# Generated by AIF-NG.\n')
            f.write(self.network['hostname'] + '\n')
        with open('{0}/etc/hosts'.format(self.system['chrootpath']), 'a') as f:
            f.write('# Added by AIF-NG.\n127.0.0.1\t{0}\t{1}\n'.format(self.network['hostname'],
                                                                       (self.network['hostname']).split('.')[0]))
        # Set up networking.
        ifaces = []
        # Ideally we'd find a better way to do... all of this. Patches welcome. TODO.
        if 'auto' in self.network['ifaces'].keys():
            # Get the default route interface.
            for line in subprocess.check_output(['ip', '-oneline', 'route', 'show']).decode('utf-8').splitlines():
                line = line.split()
                if line[0] == 'default':
                    autoiface = line[4]
                    break
        ifaces = list(self.network['ifaces'].keys())
        ifaces.sort()
        if autoiface in ifaces:
            ifaces.remove(autoiface)
        for iface in ifaces:
            resolvers = False
            if 'resolvers' in self.network['ifaces'][iface].keys():
                resolvers = self.network['ifaces'][iface]['resolvers']
            if iface == 'auto':
                ifacedev = autoiface
                iftype = 'dhcp'
            else:
                ifacedev = iface
                iftype = 'static'
            netprofile = 'Description=\'A basic {0} ethernet connection ({1})\'\nInterface={1}\nConnection=ethernet\n'.format(iftype, ifacedev)
            if 'ipv4' in self.network['ifaces'][iface].keys():
                if self.network['ifaces'][iface]['ipv4']:
                    netprofile += 'IP={0}\n'.format(iftype)
            if 'ipv6' in self.network['ifaces'][iface].keys():
                if self.network['ifaces'][iface]['ipv6']:
                    netprofile += 'IP6={0}\n'.format(iftype)  # TODO: change this to stateless if iftype='dhcp' instead?
            for proto in ('ipv4', 'ipv6'):
                addrs = []
                if proto in self.network['ifaces'][iface].keys():
                    if proto == 'ipv4':
                        addr = 'Address'
                        gwstring = 'Gateway'
                    elif proto == 'ipv6':
                        addr = 'Address6'
                        gwstring = 'Gateway6'
                    gw = self.network['ifaces'][iface][proto]['gw']
                    for ip in self.network['ifaces'][iface][proto]['addresses']:
                        if ip == 'auto':
                            continue
                        else:
                            try:
                                ipver = ipaddress.ip_network(ip, strict = False)
                                addrs.append(ip)
                            except ValueError:
                                exit('{0} was specified but is NOT a valid IPv4/IPv6 address!'.format(ip))
                    if iftype == 'static':
                        # Static addresses
                        netprofile += '{0}=(\'{1}\')\n'.format(addr, ('\' \'').join(addrs))
                        # Gateway
                        if gw:
                            netprofile += '{0}={1}\n'.format(gwstring, gw)
            # DNS resolvers
            if resolvers:
                netprofile += 'DNS=(\'{0}\')\n'.format('\' \''.join(resolvers))
            filename = '{0}/etc/netctl/{1}'.format(self.system['chrootpath'], ifacedev)
            sysdfile = '{0}/etc/systemd/system/netctl@{1}.service'.format(self.system['chrootpath'], ifacedev)
            # The good news is since it's a clean install, we only have to account for our own data, not pre-existing.
            with open(filename, 'w') as f:
                f.write('# Generated by AIF-NG.\n')
                f.write(netprofile)
            with open(sysdfile, 'w') as f:
                f.write('# Generated by AIF-NG.\n')
                f.write(('.include /usr/lib/systemd/system/netctl@.service\n\n[Unit]\n' +
                         'Description=A basic {0} ethernet connection\n' +
                         'BindsTo=sys-subsystem-net-devices-{1}.device\n' +
                         'After=sys-subsystem-net-devices-{1}.device\n').format(iftype, ifacedev))
            os.symlink('/etc/systemd/system/netctl@{0}.service'.format(ifacedev),
                       '{0}/etc/systemd/system/multi-user.target.wants/netctl@{1}.service'.format(self.system['chrootpath'], ifacedev))
        os.symlink('/usr/lib/systemd/system/netctl.service',
                   '{0}/etc/systemd/system/multi-user.target.wants/netctl.service'.format(self.system['chrootpath']))
        # Root password
        if self.users['root']['password']:
            roothash = self.users['root']['password']
        else:
            roothash = '!'
        with fileinput.input('{0}/etc/shadow'.format(self.system['chrootpath']), inplace = True) as f:
            for line in f:
                linelst = line.split(':')
                if linelst[0] == 'root':
                    linelst[1] = roothash
                print(':'.join(linelst), end = '')
        # Add users
        for user in self.users.keys():
            # We already handled root user
            if user != 'root':
                cmd = ['useradd']
                if self.users[user]['home']['create']:
                    cmd.append('-m')
                if self.users[user]['home']['path']:
                    cmd.append('-d {0}'.format(self.users[user]['home']['path']))
                if self.users[user]['comment']:
                    cmd.append('-c "{0}"'.format(self.users[user]['comment']))
                if self.users[user]['gid']:
                    cmd.append('-g {0}'.format(self.users[user]['gid']))
                if self.users[user]['uid']:
                    cmd.append('-u {0}'.format(self.users[user]['uid']))
                if self.users[user]['password']:
                    cmd.append('-p "{0}"'.format(self.users[user]['password']))
                cmd.append(user)
                chrootcmds.append(cmd)
                # Add groups
                if self.users[user]['xgroup']:
                    for group in self.users[user]['xgroup'].keys():
                        gcmd = False
                        if self.users[user]['xgroup'][group]['create']:
                            gcmd = ['groupadd']
                            if self.users[user]['xgroup'][group]['gid']:
                                gcmd.append('-g {0}'.format(self.users[user]['xgroup'][group]['gid']))
                            gcmd.append(group)
                            chrootcmds.append(gcmd)
                    chrootcmds.append(['usermod', '-aG', '{0}'.format(','.join(self.users[user]['xgroup'].keys())), user])
                # Handle sudo
                if self.users[user]['sudo']:
                    os.makedirs('{0}/etc/sudoers.d'.format(self.system['chrootpath']), exist_ok = True)
                    os.chmod('{0}/etc/sudoers.d'.format(self.system['chrootpath']), 0o750)
                    with open('{0}/etc/sudoers.d/{1}'.format(self.system['chrootpath'], user), 'w') as f:
                        f.write('# Generated by AIF-NG.\nDefaults:{0} !lecture\n{0} ALL=(ALL) ALL\n'.format(user))
        # Base configuration- initcpio, etc.
        chrootcmds.append(['mkinitcpio', '-p', 'linux'])
        return(chrootcmds)
    
    def bootloader(self):
        # Bootloader configuration
        btldr = self.system['bootloader']['type']
        bootcmds = []
        chrootpath = self.system['chrootpath']
        bttarget = self.system['bootloader']['target']
        if btldr == 'grub':
            bootcmds.append(['pacman', '--needed', '--noconfirm', '-S', 'grub', 'efibootmgr'])
            bootcmds.append(['grub-install'])
            if self.system['bootloader']['efi']:
                bootcmds[1].extend(['--target=x86_64-efi', '--efi-directory={0}'.format(bttarget), '--bootloader-id=Arch'])
            else:
                bootcmds[1].extend(['--target=i386-pc', bttarget])
            bootcmds.append(['grub-mkconfig', '-o', '{0}/grub/grub.cfg'.format(bttarget)])
        elif btldr == 'systemd':
            if self.system['bootloader']['target'] != '/boot':
                shutil.copy2('{0}/boot/vmlinuz-linux'.format(chrootpath),
                             '{0}/{1}/vmlinuz-linux'.format(chrootpath, bttarget))
                shutil.copy2('{0}/boot/initramfs-linux.img'.format(chrootpath),
                             '{0}/{1}/initramfs-linux.img'.format(chrootpath, bttarget))
                with open('{0}/{1}/loader/loader.conf'.format(chrootpath, bttarget), 'w') as f:
                    f.write('# Generated by AIF-NG.\ndefault arch\ntimeout 4\neditor 0\n')
                # Gorram, I wish there was a better way to get the partition UUID in stdlib.
                majmindev = os.lstat('{0}/{1}'.format(chrootpath, bttarget)).st_dev
                majdev = os.major(majmindev)
                mindev = os.minor(majmindev)
                btdev = os.path.basename(os.readlink('/sys/dev/block/{0}:{1}'.format(majdev, mindev)))
                partuuid = False
                for d in os.listdir('/dev/disk/by-uuid'):
                    linktarget = os.path.basename(os.readlink(d))
                    if linktarget == btdev:
                        partuuid = linktarget
                        break
                if not partuuid:
                    exit('ERROR: Cannot determine PARTUUID for /dev/{0}.'.format(btdev))
                with open('{0}/{1}/loader/entries/arch.conf'.format(chrootpath, bttarget)) as f:
                    f.write(('# Generated by AIF-NG.\ntitle\t\tArch Linux\nlinux /vmlinuz-linux\n') +
                            ('initrd /initramfs-linux.img\noptions root=PARTUUID={0} rw\n').format(partuuid))
            bootcmds.append(['bootctl', '--path={0}', 'install'])
        # TODO: Add a bit here to alter EFI boot order so we boot right to the newly-installed env.
        # should probably be optional.
        return(bootcmds)

    def scriptcmds(self, scripttype):
        t = scripttype
        if t in self.scripts.keys():
            for i, s in enumerate(self.scripts[t]):
                dirpath = '/root/scripts/{0}'.format(t)
                os.makedirs(dirpath, exist_ok = True)
                filepath = '{0}/{1}'.format(dirpath, i)
                with open(filepath, 'w') as f:
                    f.write(s)
                os.chmod(filepath, 0o700)
                os.chown(filepath, 0, 0)  # shouldn't be necessary, but just in case the umask's messed up or something.
        if t in ('pre', 'pkg'):
            # We want to run these right away.
            with open(logfile, 'a') as log:
                for i, s in enumerate(self.scripts[t]):
                    subprocess.call('/root/scripts/{0}/{1}'.format(t, i),
                                    stdout = log,
                                    stderr = subprocess.STDOUT)
        return()

    def pacmanSetup(self):
        # This should be run outside the chroot.
        conf = '{0}/etc/pacman.conf'.format(self.system['chrootpath'])
        with open(conf, 'r') as f:
            confdata = f.readlines()
        # This... is not 100% sane, and we need to change it if the pacman.conf upstream changes order of the default repos.
        # Here be dragons; you have been warned. TODO.
        idx = confdata.index('#[testing]\n')
        shutil.copy2(conf, '{0}.arch'.format(conf))
        newconf = confdata[:idx]
        newconf.append('# Modified by AIF-NG.\n')
        for r in self.software['repos']:
            if self.software['repos'][r]['mirror'].startswith('file://'):
                mirror = 'Include = {0}'.format(re.sub('^file://', '', self.software['repos'][r]['mirror']))
            else:
                mirror = 'Server = {0}'.format(self.software['repos'][r]['mirror'])
            newentry = ['[{0}]\n'.format(r), '{0}\n'.format(mirror)]
            if self.software['repos'][r]['siglevel'] != 'default':
                newentry.append('Siglevel = {0}\n'.format(self.software['repos'][r]['siglevel']))
            if self.software['repos'][r]['enabled']:
                pass  # I know, shame on me. We want this because we explicitly want it to be set as True
            else:
                newentry = ["#" + i for i in newentry]
            newentry.append('\n')
            newconf.extend(newentry)
        with open(conf, 'w') as f:
            f.write(''.join(newconf))
        if self.software['mirrors']:
            mirrorlst = '{0}/etc/pacman.d/mirrorlist'.format(self.system['chrootpath'])
            shutil.copy2(mirrorlst, '{0}.arch'.format(mirrorlst))
            # TODO: file vs. server?
            with open(mirrorlst, 'w') as f:
                for m in self.software['mirrors']:
                    if m.startswith('file://'):
                        mirror = 'Include = {0}'.format(re.sub('^file://', '', m))
                    else:
                        mirror = 'Server = {0}'.format(m)
                    f.write('{0}\n'.format(mirror))
        return()

    def packagecmds(self):
        pkgcmds = []
        # This should be run in the chroot, unless we find a way to pacstrap
        # packages separate from chrooting
        if self.software['command']:
            pkgr = shlex.split(self.software['command'])
        else:
            pkgr = ['pacman', '--needed', '--noconfirm', '-S']
        if self.software['packages']:
            for p in self.software['packages'].keys():
                if self.software['packages'][p]['repo']:
                    pkgname = '{0}/{1}'.format(self.software['packages'][p]['repo'], p)
                else:
                    pkgname = p
                pkgr.append(pkgname)
                pkgcmds.append(pkgr)
        return(pkgcmds)

    def serviceSetup(self):
        # this runs inside the chroot
        for s in self.system['services'].keys():
            if not re.match('\.(service|socket|target|timer)$', s):  # i don't bother with .path, .busname, etc.- i might in the future? TODO.
                svcname = '{0}.service'.format(s)
            service = '/usr/lib/systemd/system/{0}'.format(svcname)
            sysdunit = '/etc/systemd/system/multi-user.target.wants/{0}'.format(svcname)
            if self.system['services'][s]:
                if not os.path.lexists(sysdunit):
                    os.symlink(service, sysdunit)
            else:
                if os.path.lexists(sysdunit):
                    os.remove(sysdunit)
        return()

    def chroot(self, chrootcmds = False, bootcmds = False, scriptcmds = False, pkgcmds = False):
        if not chrootcmds:
            chrootcmds = self.setup()
        if not bootcmds:
            bootcmds = self.bootloader()
        if not scriptcmds:
            scripts = self.scripts
        if not pkgcmds:
            pkgcmds = self.packagecmds()
        # Switch in the log, and link.
        os.rename(logfile, '{0}/{1}'.format(self.system['chrootpath'], logfile))
        os.symlink('{0}/{1}'.format(self.system['chrootpath'], logfile), logfile)
        self.pacmanSetup()  # This needs to be done before the chroot
        # We don't need this currently, but we might down the road.
        #chrootscript = '#!/bin/bash\n# https://aif.square-r00t.net/\n\n'
        #with open('{0}/root/aif.sh'.format(self.system['chrootpath']), 'w') as f:
        #    f.write(chrootscript)
        #os.chmod('{0}/root/aif.sh'.format(self.system['chrootpath']), 0o700)
        real_root = os.open("/", os.O_RDONLY)
        os.chroot(self.system['chrootpath'])
        # Does this even work with an os.chroot()? Let's hope so!
        with open(logfile, 'a') as log:
            for c in chrootcmds:
                subprocess.call(c, stdout = log, stderr = subprocess.STDOUT)
            if scripts['pkg']:
                self.scriptcmds('pkg')
                for i, s in enumerate(scripts['pkg']):
                    subprocess.call('/root/scripts/pkg/{0}'.format(i),
                                    stdout = log,
                                    stderr = subprocess.STDOUT)
            for p in pkgcmds:
                subprocess.call(p, stdout = log, stderr = subprocess.STDOUT)
            for b in bootcmds:
                subprocess.call(b, stdout = log, stderr = subprocess.STDOUT)
            if scripts['post']:
                self.scriptcmds('post')
                for i, s in enumerate(scripts['post']):
                    subprocess.call('/root/scripts/post/{0}'.format(i),
                                    stdout = log,
                                    stderr = subprocess.STDOUT)
            self.serviceSetup()
        #os.system('{0}/root/aif-pre.sh'.format(self.system['chrootpath']))
        #os.system('{0}/root/aif-post.sh'.format(self.system['chrootpath']))
        os.fchdir(real_root)
        os.chroot('.')
        os.close(real_root)
        if not os.path.isfile('{0}/sbin/init'.format(self.system['chrootpath'])):
            os.symlink('../lib/systemd/systemd', '{0}/sbin/init'.format(self.system['chrootpath']))
        return()
    
    def unmount(self):
        with open(logfile, 'a') as log:
            subprocess.call(['umount', '-lR', self.system['chrootpath']], stdout = log, stderr = subprocess.STDOUT)
        # We should also remove the (now dead) log symlink.
        #Note that this does NOT delete the logfile on the installed system.
        os.remove(logfile)
        return()
                
def runInstall(confdict):
    install = archInstall(confdict)
    install.scriptcmds('pre')
    install.format()
    install.chroot()
    install.unmount()
    return()

def main():
    if os.getuid() != 0:
        exit('This must be run as root.')
    conf = aif()
    instconf = conf.buildDict()
    if 'DEBUG' in os.environ.keys():
        import pprint
        with open(logfile, 'a') as log:
            pprint.pprint(instconf, stream = log)
    runInstall(instconf)
    if instconf['system']['reboot']:
        subprocess.run(['reboot'])

if __name__ == "__main__":
    main()
