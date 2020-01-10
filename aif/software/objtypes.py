import logging
import os
import re
##
from lxml import etree


_logger = logging.getLogger(__name__)


class Mirror(object):
    def __init__(self, mirror_xml, repo = None, arch = None):
        self.xml = mirror_xml
        _logger.debug('mirror_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.uri = self.xml.text
        self.real_uri = None
        self.aif_uri = None

    def parse(self, chroot_base, repo, arch):
        self.real_uri = self.uri.replace('$repo', repo).replace('$arch', arch)
        if self.uri.startswith('file://'):
            self.aif_uri = os.path.join(chroot_base, re.sub(r'^file:///?', ''))


class Package(object):
    def __init__(self, package_xml):
        self.xml = package_xml
        _logger.debug('package_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.name = self.xml.text
        self.repo = self.xml.attrib.get('repo')
        if self.repo:
            self.qualified_name = '{0}/{1}'.format(self.repo, self.name)
        else:
            self.qualified_name = self.name


class Repo(object):
    def __init__(self, chroot_base, repo_xml, arch = 'x86_64'):
        # TODO: support Usage? ("REPOSITORY SECTIONS", pacman.conf(5))
        self.xml = repo_xml
        _logger.debug('repo_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        # TODO: SigLevels?!
        self.name = self.xml.attrib['name']
        self.conflines = {}
        self.mirrors = []
        self.parsed_mirrors = []
        _mirrors = self.xml.xpath('mirror|include')  # "Server" and "Include" respectively in pyalpm lingo.
        if _mirrors:
            for m in _mirrors:
                k = m.tag.title()
                if k == 'Mirror':
                    k = 'Server'
                if k not in self.conflines.keys():
                    self.conflines[k] = []
                self.conflines[k].append(m.text)
                # TODO; better parsing here. handle in config.py?
                # if m.tag == 'include':
                #     # TODO: We only support one level of includes. Pacman supports unlimited nesting? of includes.
                #     file_uri = os.path.join(chroot_base, re.sub(r'^/?', '', m.text))
                #     if not os.path.isfile(file_uri):
                #         _logger.error('Include file ({0}) does not exist: {1}'.format(m.text, file_uri))
                #         raise FileNotFoundError('Include file does not exist')
                #     with open(file_uri, 'r') as fh:
                #         for line in fh.read().splitlines():
        else:
            # Default (mirrorlist)
            self.conflines['Include'] = ['file:///etc/pacman.d/mirrorlist']
        self.enabled = (True if self.xml.attrib.get('enabled', 'true') in ('1', 'true') else False)
        self.siglevel = self.xml.attrib.get('sigLevel')
        # self.real_uri = None
        # if self.uri:
        #     self.real_uri = self.uri.replace('$repo', self.name).replace('$arch', arch)
