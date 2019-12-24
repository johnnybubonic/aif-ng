import logging
import os
import secrets
import uuid
##
from lxml import etree
##
from . import _common
import aif.disk.block as block
import aif.disk.lvm as lvm
import aif.disk.mdadm as mdadm


_logger = logging.getLogger(__name__)


_BlockDev = _common.BlockDev


class LuksSecret(object):
    def __init__(self, *args, **kwargs):
        _common.addBDPlugin('crypto')
        self.passphrase = None
        self.size = 4096
        self.path = None
        _logger.info('Instantiated {0}.'.format(type(self).__name__))


class LuksSecretPassphrase(LuksSecret):
    def __init__(self, passphrase):
        super().__init__()
        self.passphrase = passphrase


class LuksSecretFile(LuksSecret):
    # TODO: might do a little tweaking in a later release to support *reading from* bytes.
    def __init__(self, path, passphrase = None, bytesize = 4096):
        super().__init__()
        self.path = os.path.abspath(os.path.expanduser(path))
        _logger.debug('Path canonized: {0} => {1}'.format(path, self.path))
        self.passphrase = passphrase
        self.size = bytesize  # only used if passphrase == None
        self._genSecret()

    def _genSecret(self):
        if not self.passphrase:
            # TODO: is secrets.token_bytes safe for *persistent* random data?
            self.passphrase = secrets.token_bytes(self.size)
        if not isinstance(self.passphrase, bytes):
            self.passphrase = self.passphrase.encode('utf-8')
        _logger.debug('Secret generated.')
        return(None)


class LUKS(object):
    def __init__(self, luks_xml, partobj):
        self.xml = luks_xml
        _logger.debug('luks_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        self.id = self.xml.attrib['id']
        self.name = self.xml.attrib['name']
        self.device = partobj
        self.source = self.device.devpath
        self.secrets = []
        self.created = False
        self.locked = True
        if not isinstance(self.device, (block.Disk,
                                        block.Partition,
                                        lvm.LV,
                                        mdadm.Array)):
            _logger.error(('partobj must be of type '
                           'aif.disk.block.Disk, '
                           'aif.disk.block.Partition, '
                           'aif.disk.lvm.LV, or'
                           'aif.disk.mdadm.Array.'))
            raise TypeError('Invalid partobj type')
        _common.addBDPlugin('crypto')
        self.devpath = '/dev/mapper/{0}'.format(self.name)
        self.info = None

    def addSecret(self, secretobj):
        if not isinstance(secretobj, LuksSecret):
            _logger.error('secretobj must be of type '
                          'aif.disk.luks.LuksSecret '
                          '(aif.disk.luks.LuksSecretPassphrase or '
                          'aif.disk.luks.LuksSecretFile).')
            raise TypeError('Invalid secretobj type')
        self.secrets.append(secretobj)
        return(None)

    def createSecret(self, secrets_xml = None):
        _logger.info('Compiling secrets.')
        if not secrets_xml:  # Find all of them from self
            _logger.debug('No secrets_xml specified; fetching from configuration block.')
            for secret_xml in self.xml.findall('secrets'):
                _logger.debug('secret_xml: {0}'.format(etree.tostring(secret_xml, with_tail = False).decode('utf-8')))
                secretobj = None
                secrettypes = set()
                for s in secret_xml.iterchildren():
                    _logger.debug('secret_xml child: {0}'.format(etree.tostring(s, with_tail = False).decode('utf-8')))
                    secrettypes.add(s.tag)
                if all((('passphrase' in secrettypes),
                        ('keyFile' in secrettypes))):
                    # This is safe, because a valid config only has at most one of both types.
                    kf = secret_xml.find('keyFile')
                    secretobj = LuksSecretFile(kf.text,  # path
                                               passphrase = secret_xml.find('passphrase').text,
                                               bytesize = kf.attrib.get('size', 4096))  # TECHNICALLY should be a no-op.
                elif 'passphrase' in secrettypes:
                    secretobj = LuksSecretPassphrase(secret_xml.find('passphrase').text)
                elif 'keyFile' in secrettypes:
                    kf = secret_xml.find('keyFile')
                    secretobj = LuksSecretFile(kf.text,
                                               passphrase = None,
                                               bytesize = kf.attrib.get('size', 4096))
                self.secrets.append(secretobj)
        else:
            _logger.debug('A secrets_xml was specified.')
            secretobj = None
            secrettypes = set()
            for s in secrets_xml.iterchildren():
                _logger.debug('secrets_xml child: {0}'.format(etree.tostring(s, with_tail = False).decode('utf-8')))
                secrettypes.add(s.tag)
            if all((('passphrase' in secrettypes),
                    ('keyFile' in secrettypes))):
                # This is safe because a valid config only has at most one of both types.
                kf = secrets_xml.find('keyFile')
                secretobj = LuksSecretFile(kf.text,  # path
                                           passphrase = secrets_xml.find('passphrase').text,
                                           bytesize = kf.attrib.get('size', 4096))  # TECHNICALLY should be a no-op.
            elif 'passphrase' in secrettypes:
                secretobj = LuksSecretPassphrase(secrets_xml.find('passphrase').text)
            elif 'keyFile' in secrettypes:
                kf = secrets_xml.find('keyFile')
                secretobj = LuksSecretFile(kf.text,
                                           passphrase = None,
                                           bytesize = kf.attrib.get('size', 4096))
            self.secrets.append(secretobj)
        _logger.debug('Secrets compiled.')
        return(None)

    def create(self):
        if self.created:
            return(None)
        _logger.info('Creating LUKS volume on {0}'.format(self.source))
        if not self.secrets:
            _logger.error('Cannot create a LUKS volume with no secrets added.')
            raise RuntimeError('Cannot create a LUKS volume with no secrets')
        for idx, secret in enumerate(self.secrets):
            if idx == 0:
                # TODO: add support for custom parameters for below?
                _BlockDev.crypto.luks_format_luks2_blob(self.source,
                                                        None,  # cipher (use default)
                                                        0,  # keysize (use default)
                                                        secret.passphrase,  # passphrase
                                                        0,  # minimum entropy (use default)
                                                        _BlockDev.CryptoLUKSVersion.LUKS2,  # LUKS version
                                                        None)  # extra args
            else:
                _BlockDev.crypto.luks_add_key_blob(self.source,
                                                   self.secrets[0].passphrase,
                                                   secret.passphrase)
        self.created = True
        _logger.debug('Created LUKS volume.')
        return(None)

    def lock(self):
        _logger.info('Locking: {0}'.format(self.source))
        if not self.created:
            _logger.error('Cannot lock a LUKS volume that does not exist yet.')
            raise RuntimeError('Cannot lock non-existent volume')
        if self.locked:
            return(None)
        _BlockDev.crypto.luks_close(self.name)
        self.locked = True
        _logger.debug('Locked.')
        return(None)

    def unlock(self, passphrase = None):
        _logger.info('Unlocking: {0}'.format(self.source))
        if not self.created:
            _logger.error('Cannot unlock a LUKS volume that does not exist yet.')
            raise RuntimeError('Cannot unlock non-existent volume')
        if not self.locked:
            return(None)
        _BlockDev.crypto.luks_open_blob(self.source,
                                        self.name,
                                        self.secrets[0].passphrase,
                                        False)  # read-only
        self.locked = False
        _logger.debug('Unlocked.')
        return(None)

    def updateInfo(self):
        _logger.info('Updating info.')
        if self.locked:
            _logger.error('Tried to fetch metadata about a locked volume. A volume must be unlocked first.')
            raise RuntimeError('Must be unlocked to gather info')
        info = {}
        _info = _BlockDev.crypto.luks_info(self.devpath)
        for k in dir(_info):
            if k.startswith('_'):
                continue
            elif k in ('copy', ):
                continue
            v = getattr(_info, k)
            if k == 'uuid':
                v = uuid.UUID(hex = v)
            info[k] = v
        info['_cipher'] = '{cipher}-{mode}'.format(**info)
        self.info = info
        _logger.debug('Rendered updated info: {0}'.format(info))
        return(None)

    def writeConf(self, chroot_base, init_hook = True):
        _logger.info('Generating crypttab.')
        if not self.secrets:
            _logger.error('Secrets must be added before the configuration can be written.')
            raise RuntimeError('Missing secrets')
        conf = os.path.join(chroot_base, 'etc', 'crypttab')
        with open(conf, 'r') as fh:
            conflines = fh.read().splitlines()
        # Get UUID
        disk_uuid = None
        uuid_dir = '/dev/disk/by-uuid'
        for u in os.listdir(uuid_dir):
            d = os.path.join(uuid_dir, u)
            if os.path.realpath(d) == self.source:
                disk_uuid = u
        if disk_uuid:
            identifer = 'UUID={0}'.format(disk_uuid)
        else:
            # This is *not* ideal, but better than nothing.
            identifer = self.source
        primary_key = self.secrets[0]
        luksinfo = '{0}\t{1}\t{2}\tluks'.format(self.name,
                                                identifer,
                                                (primary_key.path if primary_key.path else '-'))
        if luksinfo not in conflines:
            with open(conf, 'a') as fh:
                fh.write('{0}\n'.format(luksinfo))
        if init_hook:
            _logger.debug('Symlinked initramfs crypttab.')
            os.symlink('/etc/crypttab', os.path.join(chroot_base, 'etc', 'crypttab.initramfs'))
        _logger.debug('Generated crypttab line: {0}'.format(luksinfo))
        return(None)
