import configparser
import io
import logging
import os
import pathlib
import re


_logger = logging.getLogger(__name__)


_font_re = re.compile(r'(\.(psfu?|fnt))?(\.gz)?$', re.IGNORECASE)
_kbd_re = re.compile(r'(\.map)?(\.gz)?$')


class Console(object):
    def __init__(self, chroot_base, console_xml):
        self.xml = console_xml
        self.chroot_base = chroot_base
        self._cfg = configparser.ConfigParser(allow_no_value = True, interpolation = None)
        self._cfg.optionxform = str
        self.keyboard = Keyboard(self.xml.find('keyboard'))
        self.font = Font(self.xml.find('text'))
        self._cfg['BASE'] = {}
        for i in (self.keyboard, self.font):
            self._cfg['BASE'].update(i.settings)

    def writeConf(self):
        for x in (self.font, self.keyboard):
            x.verify()
        cfg = os.path.join(self.chroot_base, 'etc', 'vconsole.conf')
        # We have to strip out the section from the ini.
        cfgbuf = io.StringIO()
        self._cfg.write(cfgbuf, space_around_delimiters = False)
        cfgbuf.seek(0, 0)
        with open(cfg, 'w') as fh:
            for line in cfgbuf.readlines():
                if line.startswith('[BASE]') or line.strip() == '':
                    continue
                fh.write(line)
        os.chmod(cfg, 0o0644)
        os.chown(cfg, 0, 0)
        _logger.info('Wrote: {0}'.format(cfg))
        return(None)


class Font(object):
    def __init__(self, font_xml):
        self.xml = font_xml
        self.settings = {}
        if self.xml:
            chk = {'FONT': self.xml.find('font'),
                   'FONT_MAP': self.xml.find('map'),
                   'FONT_UNIMAP': self.xml.find('unicodeMap')}
            for setting, xml in chk.items():
                if xml:
                    self.settings[setting] = xml.text.strip()
        _logger.debug('Rendered settings: {0}'.format(self.settings))

    def verify(self, chroot_base = '/'):
        if 'FONT' not in self.settings.keys():
            _logger.warning('Attempted to verify settings with no chosen font.')
            return(None)
        fontdir = pathlib.Path(chroot_base).joinpath('usr', 'share', 'kbd', 'consolefonts')
        fontnames = [_font_re.sub('', p.stem) for p in fontdir.iterdir() if not p.stem.startswith(('README.',
                                                                                                   'partialfonts',
                                                                                                   'ERRORS'))]
        _logger.debug('Rendered list of supported console fonts on target system: {0}'.format(','.join(fontnames)))
        if self.settings['FONT'] not in fontnames:
            _logger.error('Console font {0} not installed on target system.'.format(self.settings['FONT']))
            raise ValueError('Specified console font not available on target system')
        return(True)


class Keyboard(object):
    def __init__(self, chroot_base, keyboard_xml):
        self.xml = keyboard_xml
        self.chroot_base = chroot_base
        self.settings = {}
        if self.xml:
            chk = {'KEYMAP': self.xml.find('map'),
                   'KEYMAP_TOGGLE': self.xml.find('toggle')}
            for setting, xml in chk.items():
                if xml:
                    self.settings[setting] = xml.text.strip()
        _logger.debug('Rendered settings: {0}'.format(self.settings))

    def verify(self):
        kbdnames = []
        for i in ('KEYMAP', 'KEYMAP_TOGGLE'):
            if i in self.settings.keys():
                kbdnames.append(self.settings[i])
        if not kbdnames:
            _logger.warning('Attempted to verify settings with no chosen keyboard map(s).')
            return(None)
        keymapdir = os.path.join(self.chroot_base, 'usr', 'share', 'kbd', 'keymaps')
        kbdmaps = []
        for root, dirs, files in os.walk(keymapdir, topdown = True):
            if root.endswith('/include'):
                dirs[:] = []
                files[:] = []
                continue
            for f in files:
                if f.endswith('.inc'):
                    continue
                kbdmaps.append(_kbd_re.sub('', f))
        _logger.debug('Rendered list of supported keyboard maps on target system: {0}'.format(','.join(kbdmaps)))
        for k in kbdnames:
            if k not in kbdmaps:
                _logger.error('Keyboard map {0} not installed on target system.'.format(k))
                raise ValueError('Specified keyboard map not available on target system')
        return(True)
