#!/usr/bin/env python3

## REQUIRES: ##
# parted
# sgdisk (yes, both)
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
import shlex
import os
import re
import subprocess
import pprint
import urllib.request as urlrequest
import urllib.parse as urlparse
import urllib.response as urlresponse
from ftplib import FTP_TLS
from io import StringIO

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
        for i in ('network.ifaces', 'system.bootloader', 'system.services', 'users.root', 'scripts.pre', 'scripts.post'):
            i = i.split('.')
            dictname = i[0]
            keyname = i[1]
            aifdict[dictname][keyname] = {}
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
            order = i.attrib['order']
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
            if iface not in aifdict['network']['ifaces'].keys():
                aifdict['network']['ifaces'][iface] = {}
            if proto not in aifdict['network']['ifaces'][iface].keys():
                aifdict['network']['ifaces'][iface][proto] = []
            aifdict['network']['ifaces'][iface][proto].append(address)
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
        for i in ('locale', 'timezone', 'kbd', 'chrootpath'):
            if i in xmlobj.find('system').attrib:
                aifdict['system'][i] = xmlobj.find('system').attrib[i]
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
        # And then the repo list.
        for x in xmlobj.find('pacman/repos'):
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
                if len(partnums) >= 129 or partnums[-1:] >= 129:
                    exit('GPT only supports 128 partitions (and partition allocations).')
                cmds.append(['sgdisk', '-og', d])
            elif self.disk[d]['fmt'] == 'bios':
                diskfmt = 'msdos'
                cmds.append(['sgdisk', '-om', d])
            cmds.append(['parted', d, '--script', '-a', 'optimal'])
            with open(os.devnull, 'w') as DEVNULL:
                for c in cmds:
                    subprocess.call(c, stdout = DEVNULL, stderr = subprocess.STDOUT)
            cmds = []
            disksize = {}
            disksize['start'] = subprocess.check_output(['sgdisk', '-F', d])
            disksize['max'] = subprocess.check_output(['sgdisk', '-E', d])
            for p in partnums:
                # Need to do some mathz to get the actual sectors if we're using percentages.
                for s in ('start', 'size'):
                    val = self.disk[d]['parts'][str(p)][s]
                    if '%' in val:
                        stripped = val.replace('%', '')
                        modifier = re.sub('[0-9]+%', '', val)
                        percent = re.sub('(-|\+)*', '', stripped)
                        decimal = float(percent) / 100
                        newval = int(int(disksize['max']) * decimal)
                        if s == 'start':
                            newval = newval + int(disksize['start'])
                        self.disk[d]['parts'][str(p)][s] = modifier + str(newval)
            if self.disk[d]['fmt'] == 'gpt':
                for p in partnums:
                    size = {}
                    size['start'] = self.disk[d]['parts'][str(p)]['start']
                    size['end'] = self.disk[d]['parts'][str(p)]['size']
                    fstype = self.disk[d]['parts'][str(p)]['fstype'].lower()
                    if fstype not in fstypes.keys():
                        print('Filesystem type {0} is not valid. Must be a code from:\nCODE:FILESYSTEM'.format(fstype))
                        for k, v in fstypes.items():
                            print(k + ":" + v)
                        exit()
                    cmds.append(['sgdisk',
                                 '-n', '{0}:{1}:{2}'.format(str(p),
                                                            self.disk[d]['parts'][str(p)]['start'],
                                                            self.disk[d]['parts'][str(p)]['size']),
                                 #'-c', '{0}:"{1}"'.format(str(p), self.disk[d]['parts'][str(p)]['label']),  # TODO: add support for partition labels
                                 '-t', '{0}:{1}'.format(str(p), fstype),
                                 d])
                    mkformat = formatting[fstype]
                    for x, y in enumerate(mkformat):
                        if y == '%PART%':
                            mkformat[x] = d + str(p)
                    cmds.append(mkformat)
        import pprint
        pprint.pprint(cmds)
        with open(os.devnull, 'w') as DEVNULL:
            for p in cmds:
                subprocess.call(p, stdout = DEVNULL, stderr = subprocess.STDOUT)

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
        # Because the order of these mountpoints is so ridiculously important, we hardcode it. Yeah, python 3.6 has ordered dicts, but do we really want to risk it?
        with open(os.devnull, 'w') as DEVNULL:
            for m in ('chroot', 'resolv', 'proc', 'sys', 'efi', 'dev', 'pts', 'shm', 'run', 'tmp'):
                if cmounts[m]:
                    subprocess.call(cmounts[m], stdout = DEVNULL, stderr = subprocess.STDOUT)
        # Okay. So we finally have all the mounts bound. Whew.
    
    def setup(self):
        # TODO: could we leverage https://github.com/hartwork/image-bootstrap somehow? I want to keep this close
        # to standard Python libs, though, to reduce dependency requirements.
        hostscript = []
        chrootcmds = []
        locales = []
        locale = []
        # Get the necessary fstab additions for the guest
        chrootfstab = subprocess.check_output(['genfstab', '-U', self.system['chrootpath']])
        # Set up the time, and then kickstart the guest install.
        hostscript.append(['timedatectl', 'set-ntp', 'true'])
        hostscript.append(['pacstrap', self.system['chrootpath'], 'base'])
        with open('{0}/etc/fstab'.format(self.system['chrootpath']), 'a') as f:
            f.write(chrootfstab.decode('utf-8'))
        # Validating this would be better with pytz, but it's not stdlib. dateutil would also work, but same problem.
        # https://stackoverflow.com/questions/15453917/get-all-available-timezones
        tzlist = subprocess.check_output(['timedatectl', 'list-timezones']).decode('utf-8').splitlines()
        if self.system['timezone'] not in tzlist:
            print('WARNING (non-fatal): {0} does not seem to be a valid timezone, but we\'re continuing anyways.'.format(self.system['timezone']))
        os.symlink('/usr/share/zoneinfo/{0}'.format(self.system['timezone']),
                   '{0}/etc/localtime'.format(self.system['chrootpath']))
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
            f.write(''.join(localeraw))
        with open('{0}/etc/locale.conf', 'a') as f:
            f.write('LANG={0}\n'.format(locale[0].split()[0]))
        chrootcmds.append(['locale-gen'])
        # Set up the kbd layout.
        # Currently there is NO validation on this. TODO.
        if self.system['kbd']:
            with open('{0}/etc/vconsole.conf'.format(self.system['chrootpath']), 'a') as f:
                f.write('KEYMAP={0}\n'.format(self.system['kbd']))
        # Set up the hostname.
        with open('{0}/etc/hostname'.format(self.system['chrootpath']), 'w') as f:
            f.write(self.network['hostname'] + '\n')
        with open('{0}/etc/hosts'.format(self.system['chrootpath']), 'a') as f:
            f.write('127.0.0.1\t{0}\t{1}\n'.format(self.network['hostname'], (self.network['hostname']).split('.')[0]))
        # SET UP NETWORKING HERE
        ########################
        chrootcmds.append(['mkinitcpio', '-p', 'linux'])
        with open(os.devnull, 'w') as DEVNULL:
            for c in hostscript:
                subprocess.call(c, stdout = DEVNULL, stderr = subprocess.STDOUT)
        return(chrootcmds)
    
    def chroot(self, chrootcmds = False):
        if not chrootcmds:
            chrootcmds = self.setup()
        chrootscript = """#!/bin/bash
# https://aif.square-r00t.net/

"""
        with open('{0}/root/aif.sh'.format(self.system['chrootpath']), 'w') as f:
            f.write(chrootscript)
        os.chmod('{0}/root/aif.sh'.format(self.system['chrootpath']), 0o700)
        real_root = os.open("/", os.O_RDONLY)
        os.chroot(self.system['chrootpath'])
        # Does this even work with an os.chroot()? Let's hope so!
        with open(os.devnull, 'w') as DEVNULL:
            for c in chrootcmds:
                subprocess.call(c, stdout = DEVNULL, stderr = subprocess.STDOUT)
        os.system('{0}/root/aif.sh'.format(self.system['chrootpath']))
        os.system('{0}/root/aif-post.sh'.format(self.system['chrootpath']))
        os.fchdir(real_root)
        os.chroot('.')
        os.close(real_root)
        if not os.path.isfile('{0}/sbin/init'.format(chrootdir)):
            os.symlink('../lib/systemd/systemd', '{0}/sbin/init'.format(chrootdir))
    
    def unmount(self):
        with open(os.devnull, 'w') as DEVNULL:
            subprocess.call(['unmount', '-lR', self.system['chrootpath']], stdout = DEVNULL, stderr = subprocess.STDOUT)
                
def runInstall(confdict):
    install = archInstall(confdict)
    #install.format()
    #install.mounts()
    ##chrootcmds = install.setup()
    ##install.chroot(chrootcmds)
    #install.chroot()
    #install.unmount()

def main():
    if os.getuid() != 0:
        exit('This must be run as root.')
    conf = aif()
    import pprint
    instconf = conf.buildDict()
    pprint.pprint(instconf)
    runInstall(instconf)

if __name__ == "__main__":
    main()
