#!/usr/bin/env python3

import argparse
import binascii
import getpass
import sys
##
# from passlib.utils import pbkdf2  # deprecated
from passlib.crypto.digest import pbkdf2_hmac


def pskGen(ssid, passphrase):
    # raw_psk = pbkdf2.pbkdf2(str(passphrase), str(ssid), 4096, 32)  # deprecated
    raw_psk = pbkdf2_hmac('sha1', str(passphrase), str(ssid), 4096, 32)
    hex_psk = binascii.hexlify(raw_psk)
    str_psk = hex_psk.decode('utf-8')
    return(str_psk)


def parseArgs():
    def essidchk(essid):
        essid = str(essid)
        if len(essid) > 32:
            raise argparse.ArgumentTypeError('The maximum length of an ESSID is 32 characters')
        return(essid)

    def passphrasechk(passphrase):
        if passphrase:
            is_piped = False
            passphrase = str(passphrase)
            if passphrase == '-':
                if sys.stdin.isatty():
                    raise argparse.ArgumentTypeError(('[STDIN] You specified a passphrase to be entered but did not '
                                                      'provide one via a pipe.'))
                else:
                    is_piped = True
                    try:
                        # WPA-PSK only accepts ASCII for passphrase.
                        raw_pass = sys.stdin.read().encode('utf-8').decode('ascii').strip('\r').strip('\n')
                    except UnicodeDecodeError:
                        raise argparse.ArgumentTypeError('[STDIN] WPA-PSK passphrases must be an ASCII string')
            if not 7 < len(passphrase) < 64:
                raise argparse.ArgumentTypeError(('{0}WPA-PSK passphrases must be no shorter than 8 characters'
                                                  ' and no longer than 63 characters. '
                                                  'Please ensure you have provided the '
                                                  'correct passphrase.').format(('[STDIN] ' if is_piped else '')))
        return(passphrase)

    args = argparse.ArgumentParser(description = 'Generate a PSK from a passphrase')
    args.add_argument('-p', '--passphrase',
                      dest = 'passphrase',
                      default = None,
                      type = passphrasechk,
                      help = ('If specified, use this passphrase (otherwise securely interactively prompt for it). '
                              'If "-" (without quotes), read from stdin (via a pipe). '
                              'WARNING: THIS OPTION IS INSECURE AND MAY EXPOSE THE PASSPHRASE GIVEN '
                              'TO OTHER PROCESSES ON THIS SYSTEM'))
    args.add_argument('ssid',
                      metavar = 'ESSID',
                      type = essidchk,
                      help = ('The ESSID (network name) to use for this passphrase. '
                              '(This is required because WPA-PSK uses it to salt the key derivation)'))
    return(args)


def main():
    args = parseArgs().parse_args()
    if not args.passphrase:
        args.passphrase = getpass.getpass(('Please enter the passphrase for '
                                           'network "{0}" (will NOT echo back): ').format(args.ssid))
        args.passphrase = args.passphrase.encode('utf-8').decode('ascii').strip('\r').strip('\n')
    if not 7 < len(args.passphrase) < 64:
        raise ValueError(('WPA-PSK passphrases must be no shorter than 8 characters'
                          ' and no longer than 63 characters. '
                          'Please ensure you have provided the correct passphrase.'))
    psk = pskGen(args.ssid, args.passphrase)
    print('PSK for network "{0}": {1}'.format(args.ssid, psk))
    return()


if __name__ == '__main__':
    main()
