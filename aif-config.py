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

    def webFetch(self, uri, auth = False):  # TODO: add commandline args support for extra auth?
        # Sanitize the user specification and find which protocol to use
        prefix = uri.split(':')[0].lower()
        if uri.startswith('/'):
            uri = 'file://{0}'.format(uri)
            prefix = 'file'
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

    def getXSD(self):
        xsdobj = etree.fromstring(self.webFetch(xsd))
        return(xsdobj)
    
    def getXML(self):
        xmlobj = etree.fromstring(self.webFetch(self.args['cfgfile']))
        return(xmlobj)
        
    def getOpts(self):
        # Before anything else... a disclaimer.
        print('\nWARNING: This tool is not guaranteed to generate a working configuration file,\n' +
              '\t but for most basic cases it should work. I strongly encourage you to generate your own\n' +
              '\t configuration file instead by reading the documentation: https://aif.square-r00t.net/#writing_an_xml_configuration_file\n\n')
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
                    moreusersin = input('* Would you like to add additional extra groups for {0}? (y/{1}n{2}) '.format(user, color.BOLD, color.END))
                    if not re.match('^y(es)?$', moreusersin.lower()):
                        morexgroups = False
            return(users)
        def svcsPrompt(svchelp):
            svcs = {}
            moresvcs = True
            while moresvcs:
                svc = chkPrompt('** What is the name of the service? If it\'s a .service unit, you can leave the .service off: ', svchelp)
                if not re.match('^[A-Za-z0-9\-@]+(\.(service|timer|target|socket|mount|slice))?$', svc):
                    exit(' !! ERROR: You seem to have specified an invalid service name.')
                svcstatusin = chkPrompt('** Should {0} be enabled? ({1}y{2}/n) '.format(svc, color.BOLD, color.END), svchelp)
                if re.match('^no?$', svcstatusin.lower()):
                    svcs[svc] = False
                else:
                    svcs[svc] - True
                moreservices = input('* Would you like to manage another service? (y/{0}n{1}) '.format(color.BOLD, color.END))
                if not re.match('^y(es)?$', moreservices.lower()):
                    moresvcs = False
            return(svcs)
        def repoPrompt(repohelp):
            # The default pacman.conf's repo setup
            repos = {'core': {'mirror': 'file:///etc/pacman.d/mirrorlist',
                              'siglevel': 'default',
                              'enabled': True},
                     'extra': {'mirror': 'file:///etc/pacman.d/mirrorlist',
                               'siglevel': 'default',
                               'enabled': True},
                     'community-testing': {'mirror': 'file:///etc/pacman.d/mirrorlist',
                                           'siglevel': 'default',
                                           'enabled': False},
                     'community': {'mirror': 'file:///etc/pacman.d/mirrorlist',
                                   'siglevel': 'default',
                                   'enabled': True},
                     'multilib-testing': {'mirror': 'file:///etc/pacman.d/mirrorlist',
                                          'siglevel': 'default',
                                          'enabled': False},
                     'multilib': {'mirror': 'file:///etc/pacman.d/mirrorlist',
                                  'siglevel': 'default',
                                  'enabled': False}}
            chkdefs = chkPrompt(('Would you like to review the default repository configuration ' +
                                 '(and possibly edit it)? ({0}y{1}/n) ').format(color.BOLD, color.END), repohelp)
            fmtstr = '{0} {1:<20} {2:^10} {3:^10} {4}'  # ('#', 'REPO', 'ENABLED', 'SIGLEVEL', 'URI')
            if not re.match('^no?$', chkdefs.lower()):
                print('{0}{1}{2}'.format(color.BOLD, fmtstr.format('#', 'REPO', 'ENABLED', 'SIGLEVEL', 'URI'), color.END))
                rcnt = 1
                for r in repos.keys():
                    print(fmtstr.format(rcnt, r, str(repos[r]['enabled']), repos[r]['siglevel'], repos[r]['mirror']))
                    rcnt += 1
                editdefs = chkPrompt('Would you like to edit any of this? (y/{0}n{1}) '.format(color.BOLD, color.END), repohelp)
                if re.match('^y(es)?$', editdefs.lower()):
                    repokeys = list(repos.keys())
                    moreedits = True
                    while moreedits:
                        rnum = input('* What repository # would you like to edit? ')
                        try:
                            rnum = int(rnum)
                            rname = repokeys[rnum - 1]
                        except:
                            exit(' !! ERROR: You did not specify a valid repository #.')
                        enableedit = chkPrompt('** Should {0} be enabled? (y/n/{1}nochange{2}) '.format(rname, color.BOLD, color.END), repohelp)
                        if re.match('^y(es)?$', enableedit.lower()):
                            repos[rname]['enabled'] = True
                        elif re.match('^no?$', enableedit.lower()):
                            repos[rname]['enabled'] = False
                        siglvledit = chkPrompt('** What siglevel should {0} use? Leave blank for no change: ', repohelp)
                        if siglvledit != '':
                            grp1 = re.compile('^((Package|Database)?(Never|Optional|Required)|default)$')
                            grp2 = re.compile('^(Package|Database)?Trust(edOnly|All)$')
                            siglst = siglvledit.split()
                            if len(siglist) > 2:
                                exit(' !! ERROR: That is not a valid SigLevel string. See the manpage for pacman.conf ' +
                                     '(\'PACKAGE AND DATABASE SIGNATURE CHECKING\').')
                            if not grp1.match(siglist[0]):
                                exit((' !! ERROR: {0} is not valid. See the manpage for pacman.conf ' +
                                      '(\'PACKAGE AND DATABASE SIGNATURE CHECKING\').').format(siglist[0]))
                            if len(siglist) == 1:
                                if not grp2.match(siglist[1]):
                                    exit((' !! ERROR: {0} is not valid. See the manpage for pacman.conf ' +
                                          '(\'PACKAGE AND DATABASE SIGNATURE CHECKING\').').format(siglist[1]))
                            repos[rname]['siglevel'] = siglvledit
                        uriedit = chkPrompt('** What should the URI be?\n' +
                                            '\tUse a file:///absolute/path/to/file to use an Include, or leave blank for no change: ', repohelp)
                        if uriedit != '':
                            repos[rname]['mirror'] = uriedit
                        moreeditsin = chkPrompt(('** Would you like to edit another ' +
                                                 'repository? (y/{0}n{1}) ').format(color.BOLD, color.END), repohelp)
                        if not re.match('^y(es)?$', moreeditsin.lower()):
                            moreedits = False
            addreposin = chkPrompt('* Would you like to add any additional repositories? (y/{0}n{1}) '.format(color.BOLD, color.END), repohelp)
            if re.match('^y(es)?$', addreposin.lower()):
                addrepos = True
                while addrepos:
                    reponamein = chkPrompt('** What should this repository be named? (Must match the repository name on the mirror): ', repohelp)
                    reponame = re.sub('(^\[|]$)', '', reponamein)
                    if not re.match('^[a-z0-9]', reponame.lower()):
                        exit(' !! ERROR: That is not a valid repository name.')
                    repos[reponame] = {}
                    enablein = chkPrompt('** Should {0} be enabled? ({1}y{2}/n) '.format(reponame, color.BOLD, color.END), repohelp)
                    if not re.match('^no?$', enablein.lower()):
                        repos[reponame]['enabled'] = True
                    else:
                        repos[reponame]['enabled'] = False
                    siglvlin = chkPrompt('** What SigLevel string should we use for {0}? Leave blank for default: '.format(reponame), repohelp)
                    if siglvlin != '':
                        grp1 = re.compile('^((Package|Database)?(Never|Optional|Required)|default)$')
                        grp2 = re.compile('^(Package|Database)?Trust(edOnly|All)$')
                        siglst = siglvlin.split()
                        if len(siglist) > 2:
                            exit(' !! ERROR: That is not a valid SigLevel string. See the manpage for pacman.conf ' +
                                 '(\'PACKAGE AND DATABASE SIGNATURE CHECKING\').')
                        if not grp1.match(siglist[0]):
                            exit((' !! ERROR: {0} is not valid. See the manpage for pacman.conf ' +
                                  '(\'PACKAGE AND DATABASE SIGNATURE CHECKING\').').format(siglist[0]))
                        if len(siglist) == 1:
                            if not grp2.match(siglist[1]):
                                exit((' !! ERROR: {0} is not valid. See the manpage for pacman.conf ' +
                                      '(\'PACKAGE AND DATABASE SIGNATURE CHECKING\').').format(siglist[1]))
                        repos[reponame]['siglevel'] = siglvlin
                    else:
                        repos[reponame]['siglevel'] = 'default'
                    uriin = chkPrompt(('** What URI should be used for {0}?\n' +
                                       '\tUse a file:///absolute/path/to/file to use an Include: ').format(reponame), repohelp)
                    if uriin == '':
                        exit(' !! ERROR: You cannot specify a blank repository URI.')
                    else:
                        repos[reponame]['mirror'] = uriin
                    morereposin = chkPrompt('* Would you like to add another repository? (y/{0}n{1}) '.format(color.BOLD, color.END), repohelp)
                    if not re.match('^y(es)?$', morereposin.lower()):
                        addrepos = False
            return(repos)
        def pkgsPrompt(repohelp):
            pkgs = {}
            morepkgs = True
            while morepkgs:
                pkgname = chkPrompt('** What is the name of the package? ', repohelp)
                if pkgname == '':
                    exit(' !! ERROR: You must specify a package name.')
                reponame = chkPrompt(('** What repository should we install {0} from? ' +
                                      '({1}optional{2}, leave blank to skip) ').format(pkgname, color.BOLD, color.END), repohelp)
                if reponame == '':
                    pkgs[pkgname] = None
                else:
                    pkgs[pkgname] = reponame
                morepkgsin = chkPrompt('** Would you like to add another package? (y/{0}n{1}) '.format(color.BOLD, color.END), repohelp)
                if not re.match('^y(es)?$', morepkgsin.lower()):
                    morepkgs = False
            return(pkgs)
        def scrptPrompt(scrpthlp):
            scrpts = {'pre': False, 'pkg': False, 'post': False}
            morescrpts = True
            while morescrpts:
                hookin = chkPrompt('** What type of script is this? (pre/pkg/post) ', scrpthlp)
                if not re.match('^p(re|kg|ost)$', hookin.lower()):
                    exit(' !! ERROR: The hook must be one of pre, pkg, or post.')
                else:
                    hook = hookin.lower()
                if not scrpts[hook]:
                    scrpts[hook] = {}
                scrptin = chkPrompt('** What is the URI for this script? Can be an http://, https://, ftp://, ftps://, or file:// URI: ', scrpthlp)
                if not re.match('^(https?|ftps?|file)://', scrptin.lower()):
                    exit(' !! ERROR: That is not a valid URI.')
                orderin = chkPrompt(('** What order should this script be executed in during the {0} hook?\n' +
                                     '\tMust be a unique integer ' +
                                     '(lower numbers execute before higher numbers): ').format(hook), scrpthlp)
                try:
                    order = int(ordrin)
                except:
                    exit(' !! ERROR: Must be an integer')
                if order in scrpts[hook].keys():
                    exit(' !! ERROR: You already have a {0} script at that order number.'.format(order))
                scrpts[hook][order] = {'uri': scrptin}
                if re.match('^(https?|ftps?)://', scriptin.lower()):
                    authin = chkPrompt('** Does this script URI require auth? (y/{0}n{1}) '.format(color.BOLD, color.END), scrpthlp)
                    if re.match('^y(es)?$', authin.lower()):
                        if re.match('^https?://', scriptin.lower()):
                            authtype = chkPrompt(('*** What type of auth does this URI require? ' +
                                                  '({0}basic{1}/digest) ').format(color.BOLD, color.END), scrpthlp)
                            if authtype == '':
                                scrpts[hook][order]['auth'] = 'basic'
                            elif not re.match('^(basic|digest)$', authtype.lower()):
                                scrpts[hook][order]['auth'] = authtype.lower()
                            else:
                                exit(' !! ERROR: That is not a valid auth type.')
                            if authtype.lower() == 'digest':
                                realmin = chkPrompt('*** Do you know the realm needed for authentication?\n' +
                                                    '\tIf not, just leave this blank and AIF-NG will try to guess: ', scrpthlp)
                                if realmin != '':
                                    scrpts[hook][order]['realm'] = realmin
                        scrpts[hook][order]['user'] = chkPrompt('*** What user should we use for auth? ', scrpthlp)
                        scrpts[hook][order]['password'] = chkPrompt('*** What password should we use for auth? ', scrpthlp)
                    else:
                        scrpts[hook][order][auth] = False
                morescrptsin = chkPrompt('* Would you like to add another hook script? (y/{0}n{1}) '.format(color.BOLD, color.END), scrpthlp)
                if not re.match('^y(es)?$', morescrptsin.lower()):
                    morescrpts = False
            return(scrpts)
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
        moreusers = input('Would you like to add one or more regular user(s)? (y/{0}n{1}) '.format(color.BOLD, color.END))
        if re.match('^y(es)?$', moreusers.lower()):
            syshelp.append('https://aif.square-r00t.net/#code_user_code')
            conf['system']['users'] = userPrompt(syshelp)
        else:
            conf['system']['users'] = False
        svchelp = ['https://wiki.archlinux.org/index.php/Systemd',
                   'https://aif.square-r00t.net/#code_service_code']
        svcin = chkPrompt('Would you like to configure (enable/disable) services? (y/{0}n{1}) '.format(color.BOLD, color.END), svchelp)
        if re.match('^y(es)?$', svcin.lower()):
            conf['system']['services'] = svcsPrompt(svchelp)
        else:
            conf['system']['services'] = False
        print('\nNow let\'s configure the package management.')
        conf['software'] = {}
        pkgrhelp = ['https://wiki.archlinux.org/index.php/Pacman',
                    'https://wiki.archlinux.org/index.php/AUR_helpers',
                    'https://aif.square-r00t.net/#code_pacman_code']
        pkgrcmd = chkPrompt('If you won\'t be using pacman for a package manager, what command should be used to install packages?\n' +
                            '\t(Remember that you would need to install/configure it in a \'pkg\' hook script.)\n' +
                            '\tLeave blank if you\'ll only be using pacman: ', pkgrhelp)
        if pkgrcmd == '':
            conf['software']['pkgr'] = False
        else:
            conf['software']['pkgr'] = pkgrcmd
        print('\nWe need to configure the repositories for pacman and other software options.')
        repohelp = ['https://aif.square-r00t.net/#code_repos_code']
        conf['software']['repos'] = repoPrompt(repohelp)
        pkgsin = chkPrompt(('* Would you like to have extra packages installed?\n' +
                            '\t(Note that they must be available in your configured repositories or\n' +
                            '\tinstallable via "{0} <package name>".) (y/{0}n{1}) ').format(conf['software']['pkgr'],
                                                                                              color.BOLD,
                                                                                              color.END), repohelp)
        if re.match('^y(es)?$', pkgsin.lower()):
            repohelp.append('https://aif.square-r00t.net/#code_package_code')
            conf['software']['packages'] = pkgsPrompt(repohelp)
        else:
            conf['software']['packages'] = False
        btldrhelp = ['https://wiki.archlinux.org/index.php/installation_guide#Boot_loader',
                     'https://aif.square-r00t.net/#code_bootloader_code']
        conf['boot'] = {}
        btldrin = chkPrompt('* Almost done! Please choose a bootloader. ({0}grub{1}/systemd) '.format(color.BOLD, color.END), btldrhelp)
        if not re.match('^(grub|systemd)$', btldrin.lower()):
            exit(' !! ERROR: You must choose a bootloader between grub or systemd.')
        else:
            conf['boot']['bootloader'] = btldrin.lower()
        bttgtstr = 'boot partition/disk'
        btrgx = re.compile('^/dev/[A-Za-z0]+')
        if btldrin.lower() == 'grub':
            efienable = chkPrompt('** Is this system (U)EFI-capable? ({0}y{1}/n) '.format(color.BOLD, color.END), btldrhelp)
            if re.match('^no?$', efienable.lower()):
                conf['boot']['efi'] = False
            else:
                conf['boot']['efi'] = True
                bttgtstr = 'ESP (EFI System Partition)'
                btrgx = re.compile('^/([^/\x00\s]+(/)?)+$')
        bttgtin = chkPrompt('** What is the target for {0}? That is, the path to the {1}: '.format(btldrin.lower(), bttgtstr), btldrhelp)
        if not btrgx.match(bttgtin):
            exit(' !! ERROR: That doesn\'t seem to be a valid {0}.'.format(bttgtstr))
        else:
            conf['boot']['target'] = bttgtin
        scrpthlp = ['https://aif.square-r00t.net/#code_script_code']
        scrptsin = chkPrompt('* Last one! Do you have any hook scripts you\'d like to add? (y/{0}n{1}) '.format(color.BOLD, color.END), scrpthlp)
        if re.match('^y(es)?$', scrptsin.lower()):
            conf['scripts'] = scrptPrompt(scrpthlp)
        print('\n\n{0}ALL DONE!{1} Whew. You can find your configuration file at: {2}{3}{1}\n'.format(color.BOLD,
                                                                                                      color.END,
                                                                                                      color.BLUE,
                                                                                                      self.args['cfgfile']))
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
        # First we validate the XSD.
        if not lxml_avail:
            exit('\nXML validation is only supported by LXML.\nIf you want to validate the XML, install the lxml python module (python-lxml) and try again.\n')
        try:
            xsd = etree.XMLSchema(self.getXSD())
            print('\nXSD: {0}PASSED{1}'.format(color.BOLD, color.END))
        except Exception as e:
            exit('\nXSD: {0}FAILED{1}: {2}'.format(color.BOLD, color.END, e))
        # Then we can validate the XML.
        try:
            xml = xsd.validate(self.getXML())
            print('XML: {0}PASSED{1}\n'.format(color.BOLD, color.END))
        except Exception as e:
            print('XML: {0}FAILED{1}: {2}\n'.format(color.BOLD, color.END, e))
    
    def main(self):
        if self.args['oper'] == 'create':
            conf = self.getOpts()
        elif self.args['oper'] == 'convert':
            conf = self.convertJSON()
        if self.args['oper'] in ('create', 'convert'):
            self.validateXML()

def parseArgs():
    args = argparse.ArgumentParser(description = 'AIF-NG Configuration Generator',
                                   epilog = 'TIP: this program has context-specific help. e.g. try:\n\t%(prog)s create --help',
                                   formatter_class = argparse.RawTextHelpFormatter)
    commonargs = argparse.ArgumentParser(add_help = False)
    commonargs.add_argument('-f',
                            '--file',
                            dest = 'cfgfile',
                            help = 'The file to create/validate. If not specified, defaults to ./aif.xml',
                            default = '{0}/aif.xml'.format(os.getcwd()))
    subparsers = args.add_subparsers(help = 'Operation to perform',
                                     dest = 'oper')
    createargs = subparsers.add_parser('create',
                                       help = 'Create an AIF-NG XML configuration file.',
                                       parents = [commonargs])
    validateargs = subparsers.add_parser('validate',
                                         help = 'Validate an AIF-NG XML configuration file.',
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
        if args['oper'] == 'validate':
            aif.validateXML()
        elif args['oper'] == 'convert':
            aif.convertJSON()

if __name__ == '__main__':
    main()
