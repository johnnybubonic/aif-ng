#!/usr/bin/env python3


import re
import os
import io
from lxml import etree
from urllib.request import urlopen

cwd = os.path.dirname(os.path.realpath(__file__))

# Validate in the form of file:XSD/namespace.
xmlfiles = {}
#xmlfiles['aif.xml'] = 'https://aif.square-r00t.net/aif.xsd'
xmlfiles['aif.xml'] = 'aif.xsd'

def validXSD(xsdfile):
    print("Checking XSD: ", xsdfile)
    webres = False
    if re.match('^(https?|ftp)', xsdfile, re.IGNORECASE):
        webres = True
    if not webres:
        with open('{0}/{1}'.format(cwd, xsdfile), 'rb') as f:
            xsd_in = f.read()
    else:
        with urlopen(xsdfile) as f:
            xsd_in = f.read()
    xsd = False
    try:
        xsd_in = io.BytesIO(xsd_in)
        xmlschema_doc = etree.parse(xsd_in)
        xsd = etree.XMLSchema(xmlschema_doc)
    except:
        print('XSD: {0} failed.'.format(xsdfile))
    return(xsd)

def validXML(xml, xsd):
    print("Checking XML: ", xml)
    xmlfile = xml
    with open('{0}/{1}'.format(cwd, xml), 'rb') as f:
        xml_in = f.read()
    valid = False
    try:
        xml_in = io.BytesIO(xml_in)
        xml = etree.parse(xml_in)
        valid = xsd.validate(xml)
    except:
        print('XML: {0} failed.'.format(xmlfile))
    return(valid)

def allValidXML(xmlfiles):
    for key,value in xmlfiles.items():
        xmlfile = key
        xsdfile = xmlfiles[xmlfile]
        xml = False
        xsdobj = validXSD(xsdfile)
        xml = validXML(xmlfile, xsdobj)
    return(xml)


if __name__ == '__main__':
    allValidXML(xmlfiles)
