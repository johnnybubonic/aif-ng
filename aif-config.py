#!/usr/bin/env python3

try:
    from lxml import etree
    lxml_avail = True
except ImportError:
    import xml.etree.ElementTree as etree  # https://docs.python.org/3/library/xml.etree.elementtree.html
    lxml_avail = False
import argparse
import datetime
import errno
import ipaddress
import os
import pydoc  # a dirty hack we use for pagination
import re
import shlex
import socket
import sys
import urllib.request as urlrequest
import urllib.parse as urlparse
import urllib.response as urlresponse
from ftplib import FTP_TLS

xsd = 'https://aif.square-r00t.net/aif.xsd'

class aifgen(object):
    def __init__(self, args):
        self.args = args

    def getXSD(self):
        pass
    
    def getXML(self):
        pass
        
    def getOpts(self):
        def chkPrompt(prompt, urls):
            txtin = None
            txtin = input(prompt)
            if txtin in ('wikihelp', ''):
                print('\n  Articles/pages that you may find helpful for this option are:')
                for h in urls:
                    print('  * {0}'.format(h))
                print()
                txtin = input(prompt)
            else:
                return(txtin)
        
        conf = {}
        print('[{0}] Beginning configuration...'.format(datetime.datetime.now()))
        print('You may reply with \'wikihelp\' for the relevant link(s) in the Arch wiki ' +
              '(and other resources).\n')
        # https://aif.square-r00t.net/#code_disk_code
        diskhelp = ['https://wiki.archlinux.org/index.php/installation_guide#Partition_the_disks']
        diskin = chkPrompt('\nWhat disk(s) would you like to be configured on the target system?\n' +
                       'If you have multiple disks, separate with a comma (e.g. \'/dev/sda,/dev/sdb\').\n', diskhelp)
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
            if fmt == 'gpt':
                maxpart = '256'
            else:
                maxpart = '4'
            partnumsin = chkPrompt('* How many partitions should this disk have? (Maximum: {0}) '.format(maxpart), diskhelp)
            if not isinstance(partnumsin, int):
                exit(' !! ERROR: Must be an integer.')
            if partnumsin < 1:
                exit(' !! ERROR: Must be a positive integer.')
            if partnumsin > int(maxpart):
                exit(' !! ERROR: Must be less than {0}'.format(maxpart))
            parthelp = diskhelp + ['https://wiki.archlinux.org/index.php/installation_guide#Format_the_partitions',
                                 'https://aif.square-r00t.net/#code_part_code',
                                 'https://aif.square-r00t.net/#fstypes']
            for partn in range(1, partnumsin + 1):
                startsize = chkPrompt(('** Where should partition {0} start? Can be percentage [n%] ' +
                                       'or size [(+/-)n(K/M/G/T/P)]: ').format(partn), parthelp)
                startn = re.sub('[%\-+KMGTP])', '', startsize)
                if int(startn) not in range(0, 100):
                    exit()
            # https://aif.square-r00t.net/#code_part_code
            parthelp.append('https://aif.square-r00t.net/#code_part_code')

    def validateXML(self):
        pass
    
    def main(self):
        if self.args['oper'] == 'create':
            self.getOpts()
        if self.args['oper'] in ('create', 'view'):
            self.validateXML()

def parseArgs():
    args = argparse.ArgumentParser(description = 'AIF-NG Configuration Generator',
                                   epilog = 'TIP: this program has context-specific help. e.g. try "%(prog)s create --help"')
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
    
    return(args)
    
def verifyArgs(args):
    args['cfgfile'] = os.path.normpath(os.path.abspath(os.path.expanduser(args['cfgfile'])))
    args['cfgfile'] = re.sub('^/+', '/', args['cfgfile'])
    # Path/file handling - make sure we can create the parent dir if it doesn't exist,
    # check that we can write to the file, etc.
    if args['oper'] == 'create':
        args['cfgbak'] = '{0}.bak.{1}'.format(args['cfgfile'], int(datetime.datetime.utcnow().timestamp()))
        try:
            temp = True
            #mtime = None
            #atime = None
            if os.path.lexists(args['cfgfile']):
                temp = False
                #mtime = os.stat(args['cfgfile']).st_mtime
                #atime = os.stat(args['cfgfile']).st_atime
            os.makedirs(os.path.dirname(args['cfgfile']), exist_ok = True)
            with open(args['cfgfile'], 'a') as f:
                f.write('')
            if temp:
                os.remove(args['cfgfile'])
            #else:
                # WE WERE NEVER HERE.
                # I lied; ctime will still be modified, but I think this is playing it safely enough.
                # Turns out, though, f.write('') does no modifications but WILL throw the perm error we want.
                # Good.
                #os.utime(args['cfgfile'], times = (atime, mtime))
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
    return(args)

def main():
    args = vars(parseArgs().parse_args())
    if not args['oper']:
        parseArgs().print_help()
    else:
    #    verifyArgs(args)
        aif = aifgen(verifyArgs(args))
        if args['oper'] == 'create':
            aif.getOpts()
    import pprint  # DEBUGGING
    print(args)    # DEBUGGING

if __name__ == '__main__':
    main()