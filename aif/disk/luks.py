import os
import secrets
##
from . import _common
import aif.disk.block as block
import aif.disk.lvm as lvm
import aif.disk.mdadm as mdadm


_BlockDev = _common.BlockDev


class LuksSecret(object):
    def __init__(self, *args, **kwargs):
        _common.addBDPlugin('crypto')
        self.passphrase = None
        self.size = 4096
        self.path = None


class LuksSecretPassphrase(LuksSecret):
    def __init__(self, passphrase):
        super().__init__()
        self.passphrase = passphrase


class LuksSecretFile(LuksSecret):
    # TODO: might do a little tweaking in a later release to support *reading from* bytes.
    def __init__(self, path, passphrase = None, bytesize = 4096):
        super().__init__()
        self.path = os.path.realpath(path)
        self.passphrase = passphrase
        self.size = bytesize  # only used if passphrase == None
        self._genSecret()

    def _genSecret(self):
        if not self.passphrase:
            # TODO: is secrets.token_bytes safe for *persistent* random data?
            self.passphrase = secrets.token_bytes(self.size)
        if not isinstance(self.passphrase, bytes):
            self.passphrase = self.passphrase.encode('utf-8')
        return()


class LUKS(object):
    def __init__(self, luks_xml, partobj):
        self.xml = luks_xml
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
            raise ValueError(('partobj must be of type '
                              'aif.disk.block.Disk, '
                              'aif.disk.block.Partition, '
                              'aif.disk.lvm.LV, or'
                              'aif.disk.mdadm.Array'))
        _common.addBDPlugin('crypto')
        self.devpath = '/dev/mapper/{0}'.format(self.name)

    def addSecret(self, secretobj):
        if not isinstance(secretobj, LuksSecret):
            raise ValueError('secretobj must be of type aif.disk.luks.LuksSecret '
                             '(aif.disk.luks.LuksSecretPassphrase or '
                             'aif.disk.luks.LuksSecretFile)')
        self.secrets.append(secretobj)
        return()

    def createSecret(self, secrets_xml = None):
        if not secrets_xml:  # Find all of them from self
            for secret in self.xml.findall('secrets'):
                secretobj = None
                secrettypes = set()
                for s in secret.iterchildren():
                    secrettypes.add(s.tag)
                if all((('passphrase' in secrettypes),
                        ('keyFile' in secrettypes))):
                    # This is safe, because a valid config only has at most one of both types.
                    kf = secret.find('keyFile')
                    secretobj = LuksSecretFile(kf.text,  # path
                                               passphrase = secret.find('passphrase').text,
                                               bytesize = kf.attrib.get('size', 4096))  # TECHNICALLY should be a no-op.
                elif 'passphrase' in secrettypes:
                    secretobj = LuksSecretPassphrase(secret.find('passphrase').text)
                elif 'keyFile' in secrettypes:
                    kf = secret.find('keyFile')
                    secretobj = LuksSecretFile(kf.text,
                                               passphrase = None,
                                               bytesize = kf.attrib.get('size', 4096))
                self.secrets.append(secretobj)
        else:
            secretobj = None
            secrettypes = set()
            for s in secrets_xml.iterchildren():
                secrettypes.add(s.tag)
            if all((('passphrase' in secrettypes),
                    ('keyFile' in secrettypes))):
                # This is safe, because a valid config only has at most one of both types.
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
        return()

    def create(self):
        if not self.secrets:
            raise RuntimeError('Cannot create a LUKS volume with no secrets added')
        for idx, secret in enumerate(self.secrets):
            if idx == 0:
                _BlockDev.crypto.luks_format_luks2(self.source,
                                                   self.cipher,
                                                   self.keysize,
                                                   self.passphrase,
                                                   self.key_file,
                                                   self.min_entropy)
            else:
                pass  # TODO: *add* keyfile/passphrase/whatev.
        pass
        self.created = True
        return()

    def lock(self):
        if not self.created:
            raise RuntimeError('Cannot lock a LUKS volume before it is created')
        if self.locked:
            return()

        pass
        self.locked = True
        return()

    def unlock(self, passphrase = None):
        if not self.created:
            raise RuntimeError('Cannot unlock a LUKS volume before it is created')
        if not self.locked:
            return()

        pass
        self.locked = False
        return()
