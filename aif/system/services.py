import os
import pathlib
import re
##
import aif.utils


_svc_suffixes = ('service', 'socket', 'device', 'mount', 'automount', 'swap', 'target',
                 'path', 'timer', 'slice', 'scope')
_svc_re = re.compile(r'\.({0})$'.format('|'.join(_svc_suffixes)))


class Service(object):
    def __init__(self, service_xml):
        self.xml = service_xml
        self.slice = None
        self.unit_file = None
        self.dest_file = None
        self.name = service_xml.text.strip()
        self.enabled = aif.utils.xmlBool(self.xml.attrib.get('status', 'true'))
        p = pathlib.Path(self.name)
        suffix = p.suffix.lstrip('.')
        if suffix in _svc_suffixes:
            self.type = suffix
            self.name = _svc_re.sub('', self.name)
        else:
            self.type = 'service'
        s = self.name.split('@', 1)
        if len(s) > 1:
            self.name = s[0]
            self.slice = s[1]
            self.unit_file = '{0}@.{1}'.format(self.name, self.type)
            self.dest_file = '{0}@{1}.{2}'.format(self.name, self.slice, self.type)
        else:
            self.unit_file = '{0}.{1}'.format(self.name, self.type)
            self.dest_file = self.unit_file


class ServiceDB(object):
    def __init__(self, services_xml, chroot_base):
        self.xml = services_xml
        self.chroot_base = chroot_base
        self.systemd_sys = os.path.join(self.chroot_base, 'usr', 'lib', 'systemd', 'system')
        self.systemd_host = os.path.join(self.chroot_base, 'etc', 'systemd', 'system')
        self.services = []
        for service_xml in self.xml.findall('service'):
            svc = Service(service_xml)
            self.services.append(svc)

    def apply(self):
        for svc in self.services:
            dest_path = os.path.join(self.systemd_host, svc.dest_file)
            src_path = os.path.join(self.systemd_sys, svc.unit_file)
            if svc.enabled:
                if not os.path.isfile(dest_path):
                    os.symlink(src_path, dest_path)
            else:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
        return()
