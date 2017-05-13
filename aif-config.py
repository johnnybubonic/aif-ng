#!/usr/bin/env python3

try:
    from lxml import etree
    lxml_avail = True
except ImportError:
    import xml.etree.ElementTree as etree  # https://docs.python.org/3/library/xml.etree.elementtree.html
    lxml_avail = False
import argparse
import crypt
import datetime
import errno
import ipaddress
import getpass
import os
import pydoc  # a dirty hack we use for pagination
import re
import readline
import sys
import urllib.request as urlrequest
import urllib.parse as urlparse
import urllib.response as urlresponse
from ftplib import FTP_TLS

xsd = 'https://aif.square-r00t.net/aif.xsd'

# Ugh. You kids and your colors and bolds and crap.
class color(object):
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    DARKCYAN = '\033[36m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class aifgen(object):
    def __init__(self, args):
        self.args = args

    def getXSD(self):
        pass
    
    def getXML(self):
        pass
        
    def getOpts(self):
        # This whole thing is ugly. Really, really ugly. Patches 100% welcome.
        def chkPrompt(prompt, urls):
            txtin = None
            txtin = input(prompt)
            if txtin == 'wikihelp':
                print('\n  Articles/pages that you may find helpful for this option are:')
                for h in urls:
                    print('  * {0}'.format(h))
                print()
                txtin = input(prompt)
            else:
                return(txtin)
        def sizeChk(startsize):
            try:
                startn = int(re.sub('[%\-+KMGTP]', '', startsize))
                modifier = re.sub('^(\+|-)?.*$', '\g<1>', startsize)
                if re.match('^(\+|-)?[0-9]+%$', startsize):
                    sizetype = 'percentage'
                elif re.match('^(\+|-)?[0-9]+[KMGTP]$', n):
                    sizetype = 'fixed'
                else:
                    exit(' !! ERROR: The input you provided does not match a valid pattern.')
                if sizetype == 'percentage':
                    if not (0 <= startn <= 100):
                        exit(' !! ERROR: You must provide a percentage or a size.')
            except:
                exit(' !! ERROR: You did not provide a valid size specifier!')
            return(startsize)
        def ifacePrompt(nethelp):
            ifaces = {}
            moreIfaces = True
            print('\nPlease enter the name of the interface you would like to use.\n' +
                  'Can instead be \'auto\' for automatic configuration of the first found interface\n' +
                  'with an active link. (You can only specify one auto device per system, and all subsequent\n'
                  'interface entries will be ignored.)\n')
            while moreIfaces:
                ifacein = chkPrompt('Interface device: ', nethelp)
                addrin = chkPrompt(('* Address for {0} in CIDR format (can be an IPv4 or IPv6 address; ' +
                                    'use \'auto\' for DHCP/DHCPv6): ').format(ifacein), nethelp)
                if addrin == 'auto':
                    addrtype = 'auto'
                    ipver = (chkPrompt('* Would you like \'ipv4\', \'ipv6\', or \'both\' to be auto-configured? ', nethelp)).lower()
                    if ipver not in ('ipv4', 'ipv6', 'both'):
                        exit(' !! ERROR: Must be one of ipv4, ipv6, or both.')
                else:
                    addrtype = 'static'
                    try:
                        ipaddress.ip_network(addrin, strict = False)
                        try:
                            ipaddress.IPv4Address(addrin.split('/')[0])
                            ipver = 'ipv4'
                        except ipaddress.AddressValueError:
                            ipver = 'ipv6'
                    except ValueError:
                        exit(' !! ERROR: You did not enter a valid IPv4/IPv6 address.')
                if addrtype == 'static':
                    gwin = chkPrompt('* What is the gateway address for {0}? '.format(addrin), nethelp)
                    try:
                        ipaddress.ip_address(gwin)
                    except:
                        exit(' !! ERROR: You did not enter a valid IPv4/IPv6 address.')
                    ifaces[ifacein] = {'address': addrin, 'proto': ipver, 'gw': gwin, 'resolvers': []}
                    resolversin = chkPrompt('* What DNS resolvers should we use? Can accept a comma-separated list: ', nethelp)
                    for rslv in resolversin.split(','):
                        rslvaddr = rslv.strip()
                        ifaces[ifacein]['resolvers'].append(rslvaddr)
                        try:
                            ipaddress.ip_address(rslvaddr)
                        except:
                            exit(' !! ERROR: {0} is not a valid resolver address.'.format(rslvaddr))
                else:
                    ifaces[ifacein] = {'address': 'auto', 'proto': ipver, 'gw': False, 'resolvers': False}
                moreIfacesin = input('Would you like to add more interfaces? (y/{0}n{1}) '.format(color.BOLD, color.END))
                if not re.match('^y(es)?$', moreIfacesin.lower()):
                    moreIfaces = False
            return(ifaces)
        def genPassHash(user):
            passin = getpass.getpass('* Please enter the password you want to use for {0} (will not echo back): '.format(user))
            if passin not in ('', '!'):
                salt = crypt.mksalt(crypt.METHOD_SHA512)
                salthash = crypt.crypt(passin, salt)
            else:
                salthash = passin
            return(salthash)
        def userPrompt(syshelp):
            users = {}
            moreUsers = True
            while moreUsers:
                user = chkPrompt('What username would you like to add? ', syshelp)
                if len(user) > 32:
                    exit(' !! ERROR: Usernames must be less than 32 characters.')
                if not re.match('^[a-z_][a-z0-9_-]*[$]?$', user):
                    exit(' !! ERROR: Your username does not match a valid pattern. See the man page for useradd (\'CAVEATS\').')
                users[user] = {}
                sudoin = chkPrompt('* Should {0} have (full!) sudo access? (y/{0}n{1}) '.format(user, color.BOLD, color.END), syshelp)
                if re.match('^y(es)?$', sudoin.lower()):
                    users[user]['sudo'] = True
                else:
                    users[user]['sudo'] = False
                users[user]['password'] = genPassHash(user)
                users[user]['comment'] = chkPrompt(('* What comment should {0} have? ' +
                                                    '(Typically this is the user\'s full name) ').format(user), syshelp)
                uidin = chkPrompt(('* What UID should {0} have? Leave this blank if you don\'t care ' +
                                   '(should be fine for most cases): ').format(user), syshelp)
                if uidin != '':
                    try:
                        users[user]['uid'] = int(uidin)
                    except:
                        exit(' !! ERROR: The UID must be an integer.')
                else:
                    users[user]['uid'] = False
                grpin = chkPrompt(('* What group name would you like to use for {0}\'s primary group? ' +
                                   '(You\'ll be able to add additional groups in a moment.)\n' +
                                   '\tThe default, if left blank, is to simply create a group named {0} ' +
                                   '(which is what you probably want): ').format(user), syshelp)
                if len(grpin) > 32:
                    exit(' !! ERROR: Group names must be less than 32 characters.')
                if not re.match('^[a-z_][a-z0-9_-]*[$]?$', grpin):
                    exit(' !! ERROR: Your group name does not match a valid pattern. See the man page for groupadd (\'CAVEATS\').')
                users[user]['group'] = grpin
                gidin = chkPrompt(('* What GID should {0} have? Leave this blank if you don\'t care ' +
                                   '(should be fine for most cases): ').format(grpin), syshelp)
                if gidin != '':
                    try:
                        users[user]['gid'] = int(gidin)
                    except:
                        exit(' !! ERROR: The GID must be an integer.')
                else:
                    users[user]['gid'] = False
                syshelp.append('https://aif.square-r00t.net/#code_home_code')
                homein = chkPrompt(('* What directory should {0} use for its home? Leave blank if you don\'t care ' +
                                    '(should be fine for most cases): ').format(user), syshelp)
                if homein != '':
                    if not re.match('^/([^/\x00\s]+(/)?)+)$', homein):
                        exit('!! ERROR: Path {0} does not seem to be valid.'.format(homein))
                    users[user]['home'] = homein
                else:
                    users[user]['home'] = False
                homecrt = chkPrompt('* Do we need to create {0}? (y/{1}n{2}) '.format(homein, color.BOLD, color.END), syshelp)
                if re.match('^y(es)?$', homecrt):
                    users[user]['homecreate'] = True
                else:
                    users[user]['homecreate'] = False
                del(syshelp[-1])
                xgrouphelp = 'https://aif.square-r00t.net/#code_xgroup_code'
                if xgrouphelp not in syshelp:
                    syshelp.append(xgrouphelp)
                xgroupin = chkPrompt('* Would you like to add extra groups for {0}? (y/{1}n{2}) '.format(user, color.BOLD, color.END), syshelp)
                if re.match('^y(es)?$', xgroupin.lower()):
                    morexgroups = True
                    users[user]['xgroups'] = {}
                else:
                    morexgroups = False
                    users[user]['xgroups'] = False
                while morexgroups:
                    xgrp = chkPrompt('** What is the name of the group you would like to add? ', syshelp)
                    if len(xgrp) > 32:
                        exit(' !! ERROR: Group names must be less than 32 characters.')
                    if not re.match('^[a-z_][a-z0-9_-]*[$]?$', xgrp):
                        exit(' !! ERROR: Your group name does not match a valid pattern. See the man page for groupadd (\'CAVEATS\').')
                    users[user]['xgroups'][xgrp] = {}
                    xgrpcrt = chkPrompt('** Does {0} need to be created? (y/{1}n{2} '.format(xgrp, color.BOLD, color.END), syshelp)
                    if re.match('^y(es)?$', xgrpcrt.lower()):
                        users[user]['xgroups'][xgrp]['create'] = True
                    else:
                        users[user]['xgroups'][xgrp]['create'] = False
                    xgrpgid = chkPrompt(('** What GID should {0} be? If the group will already exist on the new system or ' +
                                        'don\'t care,\nleave this blank (should be fine for most cases): ').format(xgrp), syshelp)
                    if xrpgid != '':
                        try:
                            users[user]['xgroups'][xgrp]['gid'] = int(xgrpid)
                        except:
                            exit(' !! ERROR: The GID must be an integer.')
                    else:
                        users[user]['xgroups'][xgrp]['gid'] = False
                    moreusersin = input('\nWould you like to add more groups for {0}? (y/{1}n{2}) '.format(user, color.BOLD, color.END))
                    if not re.match('^y(es)?$', moreusersin.lower()):
                        morexgroups = False
            return(users)
        conf = {}
        print('[{0}] Beginning configuration...'.format(datetime.datetime.now()))
        print('You may reply with \'wikihelp\' on the first prompt of a question for the relevant link(s) in the Arch wiki ' +
              '(and other resources).\n')
        # https://aif.square-r00t.net/#code_disk_code
        diskhelp = ['https://wiki.archlinux.org/index.php/installation_guide#Partition_the_disks']
        diskin = chkPrompt('\nWhat disk(s) would you like to be configured on the target system?\n' +
                       '\tIf you have multiple disks, separate with a comma (e.g. \'/dev/sda,/dev/sdb\'): ', diskhelp)
        # NOTE: the following is a dict of fstype codes to their description.
        fstypes = {'0700': 'Microsoft basic data', '0c01': 'Microsoft reserved', '2700': 'Windows RE', '3000': 'ONIE config', '3900': 'Plan 9', '4100': 'PowerPC PReP boot', '4200': 'Windows LDM data', '4201': 'Windows LDM metadata', '4202': 'Windows Storage Spaces', '7501': 'IBM GPFS', '7f00': 'ChromeOS kernel', '7f01': 'ChromeOS root', '7f02': 'ChromeOS reserved', '8200': 'Linux swap', '8300': 'Linux filesystem', '8301': 'Linux reserved', '8302': 'Linux /home', '8303': 'Linux x86 root (/)', '8304': 'Linux x86-64 root (/', '8305': 'Linux ARM64 root (/)', '8306': 'Linux /srv', '8307': 'Linux ARM32 root (/)', '8400': 'Intel Rapid Start', '8e00': 'Linux LVM', 'a500': 'FreeBSD disklabel', 'a501': 'FreeBSD boot', 'a502': 'FreeBSD swap', 'a503': 'FreeBSD UFS', 'a504': 'FreeBSD ZFS', 'a505': 'FreeBSD Vinum/RAID', 'a580': 'Midnight BSD data', 'a581': 'Midnight BSD boot', 'a582': 'Midnight BSD swap', 'a583': 'Midnight BSD UFS', 'a584': 'Midnight BSD ZFS', 'a585': 'Midnight BSD Vinum', 'a600': 'OpenBSD disklabel', 'a800': 'Apple UFS', 'a901': 'NetBSD swap', 'a902': 'NetBSD FFS', 'a903': 'NetBSD LFS', 'a904': 'NetBSD concatenated', 'a905': 'NetBSD encrypted', 'a906': 'NetBSD RAID', 'ab00': 'Recovery HD', 'af00': 'Apple HFS/HFS+', 'af01': 'Apple RAID', 'af02': 'Apple RAID offline', 'af03': 'Apple label', 'af04': 'AppleTV recovery', 'af05': 'Apple Core Storage', 'bc00': 'Acronis Secure Zone', 'be00': 'Solaris boot', 'bf00': 'Solaris root', 'bf01': 'Solaris /usr & Mac ZFS', 'bf02': 'Solaris swap', 'bf03': 'Solaris backup', 'bf04': 'Solaris /var', 'bf05': 'Solaris /home', 'bf06': 'Solaris alternate sector', 'bf07': 'Solaris Reserved 1', 'bf08': 'Solaris Reserved 2', 'bf09': 'Solaris Reserved 3', 'bf0a': 'Solaris Reserved 4', 'bf0b': 'Solaris Reserved 5', 'c001': 'HP-UX data', 'c002': 'HP-UX service', 'ea00': 'Freedesktop $BOOT', 'eb00': 'Haiku BFS', 'ed00': 'Sony system partition', 'ed01': 'Lenovo system partition', 'ef00': 'EFI System', 'ef01': 'MBR partition scheme', 'ef02': 'BIOS boot partition', 'f800': 'Ceph OSD', 'f801': 'Ceph dm-crypt OSD', 'f802': 'Ceph journal', 'f803': 'Ceph dm-crypt journal', 'f804': 'Ceph disk in creation', 'f805': 'Ceph dm-crypt disk in creation', 'fb00': 'VMWare VMFS', 'fb01': 'VMWare reserved', 'fc00': 'VMWare kcore crash protection', 'fd00': 'Linux RAID'}
        conf['disks'] = {}
        for d in diskin.split(','):
            disk = d.strip()
            if not re.match('^/dev/[A-Za-z0]+', disk):
                exit('!! ERROR: Disk {0} does not seem to be a valid device path.'.format(disk))
            conf['disks'][disk] = {}
            print('\nConfiguring disk {0} ...'.format(disk))
            fmtin = chkPrompt('* What format should this disk use (gpt/bios)? ', diskhelp)
            fmt = fmtin.lower()
            if fmt not in ('gpt', 'bios'):
                exit('  !! ERROR: Must be one of \'gpt\' or \'bios\'.')
            conf['disks'][disk]['fmt'] = fmt
            conf['disks'][disk]['parts'] = {}
            if fmt == 'gpt':
                maxpart = '256'
            else:
                maxpart = '4'  # yeah, extended volumes can do more, but that's not supported in AIF-NG. yet?
            partnumsin = chkPrompt('* How many partitions should this disk have? (Maximum: {0}) '.format(maxpart), diskhelp)
            try:
                int(partnumsin)
            except:
                exit(' !! ERROR: Must be an integer.')
            if int(partnumsin) < 1:
                exit(' !! ERROR: Must be a positive integer.')
            if int(partnumsin) > int(maxpart):
                exit(' !! ERROR: Must be less than {0}'.format(maxpart))
            parthelp = diskhelp + ['https://wiki.archlinux.org/index.php/installation_guide#Format_the_partitions',
                                 'https://aif.square-r00t.net/#code_part_code']
            for partn in range(1, int(partnumsin) + 1):
                # https://aif.square-r00t.net/#code_part_code
                conf['disks'][disk]['parts'][partn] = {}
                for s in ('start', 'stop'):
                    conf['disks'][disk]['parts'][partn][s] = None
                    sizein = chkPrompt(('** Where should partition {0} {1}? Can be percentage [n%] ' +
                                        'or size [(+/-)n(K/M/G/T/P)]: ').format(partn, s), parthelp)
                    conf['disks'][disk]['parts'][partn][s] = sizeChk(sizein)
                newhelp = 'https://aif.square-r00t.net/#fstypes'
                if newhelp not in parthelp:
                    parthelp.append(newhelp)
                fstypein = chkPrompt(('** What filesystem type should partition {0} be? ' +
                                      'See wikihelp for valid fstypes: ').format(partn), parthelp)
                if fstypein not in fstypes.keys():
                    exit(' !! ERROR: {0} is not a valid filesystem type.'.format(fstypein))
                else:
                    print('\tSelected {0}'.format(fstypes[fstypein]))
        mnthelp = ['https://wiki.archlinux.org/index.php/installation_guide#Mount_the_file_systems',
                   'https://aif.square-r00t.net/#code_mount_code']
        mntin = chkPrompt('\nWhat mountpoint(s) would you like to be configured on the target system?\n' +
                       '\tIf you have multiple mountpoints, separate with a comma (e.g. \'/mnt/aif,/mnt/aif/boot\').\n' +
                       '\t(NOTE: Can be \'swap\' for swapspace.): ', mnthelp)
        conf['mounts'] = {}
        for m in mntin.split(','):
            mount = m.strip()
            if not re.match('^(/([^/\x00\s]+(/)?)+|swap)$', mount):
                exit('!! ERROR: Mountpoint {0} does not seem to be a valid path/specifier.'.format(mount))
            print('\nConfiguring mountpoint {0} ...'.format(mount))
            dvcin = chkPrompt('* What device/partition should be mounted here? ', mnthelp)
            if not re.match('^/dev/[A-Za-z0]+', dvcin):
                exit('  !! ERROR: Must be a full path to a device/partition.')
            ordrin = chkPrompt('* What order should this mount occur in relation to others?\n\t'+
                               'Must be a unique integer (lower numbers mount before higher numbers): ', mnthelp)
            try:
                order = int(ordrin)
            except:
                exit(' !! ERROR: Must be an integer')
            if order in conf['mounts'].keys():
                exit(' !! ERROR: You already have a mountpoint at that order number.')
            conf['mounts'][order] = {}
            conf['mounts'][order]['target'] = mount
            conf['mounts'][order]['device'] = dvcin
            fstypein = chkPrompt('* What filesystem type should this be mounted as (i.e. mount\'s -t option)? This is optional,\n\t' +
                               'but may be required for more exotic filesystem types. If you don\'t have to specify one,\n\t' +
                               'just leave this blank: ', mnthelp)
            if fstypein == '':
                conf['mounts'][order]['fstype'] = False
            elif not re.match('^[a-z]+([0-9]+)?$', fstypein):  # Not 100%, but should catch most faulty entries
                exit(' !! ERROR: {0} does not seem to be a valid filesystem type.'.format(fstypein))
            else:
                conf['mounts'][order]['fstype'] = fstypein
            mntoptsin = chkPrompt('* What, if any, mount option(s) (mount\'s -o option) do you require? (Multiple options should be separated\n' +
                                  '\twith a comma). If none, leave this blank: ', mnthelp)
            if mntoptsin == '':
                conf['mounts'][order]['opts'] = False
            elif not re.match('^[A-Za-z0-9_\.\-=]+(,[A-Za-z0-9_\.\-=]+)*', re.sub('\s', '', mntoptsin)):  # TODO: shlex split this instead?
                exit(' !! ERROR: You seem to have not specified valid mount options.')
            else:
                # TODO: slex this instead? is it possible for mount opts to contain whitespace?
                conf['mounts'][order]['opts'] = re.sub('\s', '', mntoptsin)
        print('\nNow, let\'s configure the network. Note that at this time, wireless/more exotic networking is not supported by AIF-NG.\n')
        conf['network'] = {}
        nethelp = ['https://wiki.archlinux.org/index.php/installation_guide#Network_configuration',
                  'https://aif.square-r00t.net/#code_network_code']
        hostnamein = chkPrompt('What should the newly-installed system\'s hostname be?\n\t' +
                               'It must be in FQDN format, but can be a non-existent domain: ', nethelp)
        hostname = hostnamein.lower()
        if len(hostname) > 253:
            exit(' !! ERROR: A FQDN cannot be more than 253 characters (RFC 1035, 2.3.4)')
        hostnamelst = hostname.split('.')
        for c in hostnamelst:
            if len(c) > 63:
                exit(' !! ERROR: No component of an FQDN can be more than 63 characters (RFC 1035, 2.3.4)')
        if not re.match('^[a-zA-Z\d-]{,63}(\.[a-zA-Z\d-]{,63})*', hostname):
            exit(' !! ERROR: That does not seem to be a valid FQDN.')
        else:
            conf['network']['hostname'] = hostname
        conf['network']['ifaces'] = {}
        nethelp.append('https://aif.square-r00t.net/#code_iface_code')
        conf['network']['ifaces'] = ifacePrompt(nethelp)
        print('\nNow let\'s configure some basic system settings.')
        syshelp = ['https://aif.square-r00t.net/#code_system_code']
        syshelp.append('https://wiki.archlinux.org/index.php/installation_guide#Time_zone')
        tzin = chkPrompt('* What timezone should the newly installed system use? (Default is UTC): ', syshelp)
        if tzin == '':
            tzin = 'UTC'
        syshelp[1] = 'https://wiki.archlinux.org/index.php/installation_guide#Locale'
        localein = chkPrompt('* What locale should the new system use? (Default is en_US.UTF-8): ', syshelp)
        if localein == '':
            localein = 'en_US.UTF-8'
        syshelp[1] = 'https://aif.square-r00t.net/#code_mount_code'
        chrootpathin = chkPrompt('* What chroot path should the host use? This should be one of the mounts you specified above: ', syshelp)
        if not re.match('^/([^/\x00\s]+(/)?)+$', chrootpathin):
            exit('!! ERROR: Your chroot path does not seem to be a valid path/specifier.')
        syshelp[1] = 'https://wiki.archlinux.org/index.php/installation_guide#Set_the_keyboard_layout'
        kbdin = chkPrompt('* What keyboard layout should the newly installed system use? (Default is US): ', syshelp)
        if kbdin == '':
            kbdin = 'US'
        del(syshelp[1])
        rbtin = chkPrompt('* Would you like to reboot the host system after installation completes? ({0}y{1}/n): '.format(color.BOLD, color.END), syshelp)
        if not re.match('^no?$', rbtin.lower()):
            rebootme = True
        else:
            rebootme = False
        conf['system'] = {'timezone': tzin, 'locale': localein, 'chrootpath': chrootpathin, 'kbd': kbdin, 'reboot': rebootme}
        syshelp[1] = 'https://aif.square-r00t.net/#code_users_code'
        print('\nNow let\'s handle some user accounts. For passwords, you can either enter the password you want to use,\n' +
              'a \'!\' (in which case TTY login will be disabled but e.g. SSH will still work), or just hit enter to leave it blank\n' +
              '(which is HIGHLY not recommended - it means anyone can login by just pressing enter at the login!)\n')
        print('Let\'s configure the root user.')
        conf['system']['rootpass'] = genPassHash(root)
        moreusers = input('Would you like to add one or more regular user(s)? (y/{0}n{1}) '.format(color.BOLD, color.END)
        if re.match('^y(es)?$', moreusers.lower()):
            syshelp.append('https://aif.square-r00t.net/#code_user_code')
            conf['system']['users'] = userPrompt(syshelp)
        else:
            conf['system']['users'] = False
        if self.args['verbose']:
            import pprint
            pprint.pprint(conf)
        return(conf)
    
    def convertJSON(self):
        with open(args['inputfile'], 'r') as f:
            try:
                conf = json.loads(f.read())
            except:
                exit(' !! ERROR: {0} does not seem to be a strict JSON file.'.format(args['inputfile']))
        return(conf)

    def validateXML(self):
        pass
    
    def main(self):
        if self.args['oper'] == 'create':
            conf = self.getOpts()
        elif self.args['oper'] == 'convert':
            conf = self.convertJSON()
        if self.args['oper'] in ('create', 'view', 'convert'):
            self.validateXML()

def parseArgs():
    args = argparse.ArgumentParser(description = 'AIF-NG Configuration Generator',
                                   epilog = 'TIP: this program has context-specific help. e.g. try:\n\t%(prog)s create --help',
                                   formatter_class = argparse.RawTextHelpFormatter)
    commonargs = argparse.ArgumentParser(add_help = False)
    commonargs.add_argument('-f',
                            '--file',
                            dest = 'cfgfile',
                            help = 'The file to create/validate/view. If not specified, defaults to ./aif.xml',
                            default = '{0}/aif.xml'.format(os.getcwd()))
    subparsers = args.add_subparsers(help = 'Operation to perform',
                                     dest = 'oper')
    createargs = subparsers.add_parser('create',
                                       help = 'Create an AIF-NG XML configuration file.',
                                       parents = [commonargs])
    validateargs = subparsers.add_parser('validate',
                                         help = 'Validate an AIF-NG XML configuration file.',
                                         parents = [commonargs])
    viewargs = subparsers.add_parser('view',
                                     help = 'View an AIF-NG XML configuration file.',
                                     parents = [commonargs])
    convertargs = subparsers.add_parser('convert',
                                        help = 'Convert a "more" human-readable JSON configuration file to AIF-NG-compatible XML.',
                                        parents = [commonargs])
    createargs.add_argument('-v',
                            '--verbose',
                            dest = 'verbose',
                            action = 'store_true',
                            help = 'Print the dict of raw values used to create the XML. Mostly/only useful for debugging.')
    convertargs.add_argument('-i',
                             '--input',
                             dest = 'inputfile',
                             required = True,
                             help = 'The JSON file to import and convert into XML.')
    return(args)
    
def verifyArgs(args):
    args['cfgfile'] = os.path.normpath(os.path.abspath(os.path.expanduser(args['cfgfile'])))
    args['cfgfile'] = re.sub('^/+', '/', args['cfgfile'])
    # Path/file handling - make sure we can create the parent dir if it doesn't exist,
    # check that we can write to the file, etc.
    if args['oper'] in ('create', 'convert'):
        args['cfgbak'] = '{0}.bak.{1}'.format(args['cfgfile'], int(datetime.datetime.utcnow().timestamp()))
        try:
            temp = True
            if os.path.lexists(args['cfgfile']):
                temp = False
            os.makedirs(os.path.dirname(args['cfgfile']), exist_ok = True)
            with open(args['cfgfile'], 'a') as f:
                f.write('')
            if temp:
                os.remove(args['cfgfile'])
        except OSError as e:
            print('\nERROR: {0}: {1}'.format(e.strerror, e.filename))
            exit(('\nWe encountered an error when trying to use path {0}.\n' + 
                  'Please review the output and address any issues present.').format(args['cfgfile']))
    elif args['oper'] == 'view':
        try:
            with open(args['cfgfile'], 'r') as f:
                f.read()
        except OSError as e:
            print('\nERROR: {0}: {1}'.format(e.strerror, e.filename))
            exit(('\nWe encountered an error when trying to use path {0}.\n' + 
                  'Please review the output and address any issues present.').format(args['cfgfile']))
    if args['oper'] == 'convert':
        # And we need to make sure we have read perms to the JSON input file.
        try:
            with open(args['inputfile'], 'r') as f:
                f.read()
        except OSError as e:
            print('\nERROR: {0}: {1}'.format(e.strerror, e.filename))
            exit(('\nWe encountered an error when trying to read path {0}.\n' + 
                  'Please review the output and address any issues present.').format(args['inputfile']))
    return(args)

def main():
    args = vars(parseArgs().parse_args())
    if not args['oper']:
        parseArgs().print_help()
    else:
        # Once aifgen.main() is complete, we only need to call that.
        # That should handle all the below logic.
        aif = aifgen(verifyArgs(args))
        if args['oper'] == 'create':
            aif.getOpts()
        elif args['oper'] == 'convert':
            aif.convertJSON()

if __name__ == '__main__':
    main()
