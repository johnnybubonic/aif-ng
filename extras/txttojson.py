#!/usr/bin/env python3

import argparse
import json
import os
import pprint
#import re
try:
    import yaml
except:
    exit('You need pyYAML.')

def parseArgs():
    args = argparse.ArgumentParser()
    args.add_argument('-i',
                      '--in',
                      dest = 'infile',
                      required = True,
                      help = 'The plaintext representation of a python dict')
    args.add_argument('-o',
                      '--out',
                      dest = 'outfile',
                      required = True,
                      help = 'The JSON file to create')
    return(args)

def main():
    args = vars(parseArgs().parse_args())
    infile = os.path.abspath(os.path.normpath(args['infile']))
    outfile = os.path.abspath(os.path.normpath(args['outfile']))
    if not os.path.lexists(infile):
        exit('Input file doesn\'t exist.')
#try:
    with open(outfile, 'w') as outgoing:
        with open(infile, 'r') as incoming:
            #data = re.sub("'", '"', incoming.read())
            #outgoing.write(data)
            #d = json.dumps(data, ensure_ascii = False)
            #d = json.dumps(incoming.read().replace("'", '"'))
            d = yaml.load(incoming.read())
            pprint.pprint(d)
            j = json.dumps(d, indent = 4)
            outgoing.write(j)
#except:
    #exit('Error when trying to read/write file(s).')
    return()

if __name__ == '__main__':
    main()
