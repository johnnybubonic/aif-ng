import logging
##
from lxml import etree
##
from . import locales
from . import console
from . import users
from . import services


_logger = logging.getLogger(__name__)


class Sys(object):
    def __init__(self, chroot_base, system_xml):
        self.xml = system_xml
        _logger.debug('system_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.chroot_base = chroot_base
        self.locale = locales.Locale(self.chroot_base, self.xml.find('locales'))
        self.console = console.Console(self.chroot_base, self.xml.find('console'))
        self.tz = locales.Timezone(self.chroot_base, self.xml.attrib.get('timezone', 'UTC'))
        self.user = users.UserDB(self.chroot_base, self.xml.find('rootPassword'), self.xml.find('users'))
        self.services = services.ServiceDB(self.chroot_base, self.xml.find('services'))

    def apply(self):
        self.locale.writeConf()
        self.console.writeConf()
        self.tz.apply()
        self.user.writeConf()
        self.services.apply()
        return(None)
