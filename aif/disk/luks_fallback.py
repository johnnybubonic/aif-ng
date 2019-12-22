import logging
import os
import re
import secrets
import subprocess
import tempfile
import uuid
##
import parse
from lxml import etree
##
import aif.disk.block_fallback as block
import aif.disk.lvm_fallback as lvm
import aif.disk.mdadm_fallback as mdadm


_logger = logging.getLogger(__name__)


class LuksSecret(object):
    def __init__(self, *args, **kwargs):
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
        self.path = os.path.realpath(path)
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
            raise ValueError('Invalid partobj type')
        self.devpath = '/dev/mapper/{0}'.format(self.name)
        self.info = None

    def addSecret(self, secretobj):
        if not isinstance(secretobj, LuksSecret):
            _logger.error('secretobj must be of type '
                          'aif.disk.luks.LuksSecret '
                          '(aif.disk.luks.LuksSecretPassphrase or '
                          'aif.disk.luks.LuksSecretFile).')
            raise ValueError('Invalid secretobj type')
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
                cmd_str = ['cryptsetup',
                           '--batch-mode',
                           'luksFormat',
                           '--type', 'luks2',
                           '--key-file', '-',
                           self.source]
                cmd = subprocess.run(cmd_str,
                                     input = secret.passphrase,
                                     stdout = subprocess.PIPE,
                                     stderr = subprocess.PIPE)
                if cmd.returncode != 0:
                    _logger.warning('Command returned non-zero status')
                    _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
                    for a in ('stdout', 'stderr'):
                        x = getattr(cmd, a)
                        if x:
                            _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
                    raise RuntimeError('Failed to encrypt successfully')
            else:
                # TODO: does the key-file need to be the same path in the installed system?
                tmpfile = tempfile.mkstemp()
                with open(tmpfile[1], 'wb') as fh:
                    fh.write(secret.passphrase)
                cmd_str = ['cryptsetup',
                           '--batch-mode',
                           'luksAdd',
                           '--type', 'luks2',
                           '--key-file', '-',
                           self.source,
                           tmpfile[1]]
                cmd = subprocess.run(cmd_str,
                                     input = self.secrets[0].passphrase,
                                     stdout = subprocess.PIPE,
                                     stderr = subprocess.PIPE)

                os.remove(tmpfile[1])
                if cmd.returncode != 0:
                    _logger.warning('Command returned non-zero status')
                    _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
                    for a in ('stdout', 'stderr'):
                        x = getattr(cmd, a)
                        if x:
                            _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
                    raise RuntimeError('Failed to encrypt successfully')
        self.created = True
        return(None)

    def lock(self):
        if not self.created:
            raise RuntimeError('Cannot lock a LUKS volume before it is created')
        if self.locked:
            return(None)
        cmd_str = ['cryptsetup',
                   '--batch-mode',
                   'luksClose',
                   self.name]
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to lock successfully')
        self.locked = True
        return(None)

    def unlock(self, passphrase = None):
        if not self.created:
            raise RuntimeError('Cannot unlock a LUKS volume before it is created')
        if not self.locked:
            return(None)
        cmd_str = ['cryptsetup',
                   '--batch-mode',
                   'luksOpen',
                   '--key-file', '-',
                   self.source,
                   self.name]
        cmd = subprocess.run(cmd_str, input = self.secrets[0].passphrase)
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to unlock successfully')
        self.locked = False
        return(None)

    def updateInfo(self):
        if self.locked:
            raise RuntimeError('Must be unlocked to gather info')
        info = {}
        cmd_str = ['cryptsetup',
                   '--batch-mode',
                   'luksDump',
                   self.source]
        cmd = subprocess.run(cmd_str, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
        if cmd.returncode != 0:
            _logger.warning('Command returned non-zero status')
            _logger.debug('Exit status: {0}'.format(str(cmd.returncode)))
            for a in ('stdout', 'stderr'):
                x = getattr(cmd, a)
                if x:
                    _logger.debug('{0}: {1}'.format(a.upper(), x.decode('utf-8').strip()))
            raise RuntimeError('Failed to fetch info successfully')
        _info = cmd.stdout.decode('utf-8')
        k = None
        # I wish there was a better way to do this but I sure as heck am not writing a regex to do it.
        # https://gitlab.com/cryptsetup/cryptsetup/issues/511
        # https://pypi.org/project/parse/
        _tpl = ('LUKS header information\nVersion:        {header_ver}\nEpoch:          {epoch_ver}\n'
                'Metadata area:  {metadata_pos} [bytes]\nKeyslots area:  {keyslots_pos} [bytes]\n'
                'UUID:           {uuid}\nLabel:          {label}\nSubsystem:      {subsystem}\n'
                'Flags:          {flags}\n\nData segments:\n  0: crypt\n        '
                'offset: {offset_bytes} [bytes]\n        length: {crypt_length}\n        '
                'cipher: {crypt_cipher}\n        sector: {sector_size} [bytes]\n\nKeyslots:\n  0: luks2\n        '
                'Key:        {key_size} bits\n        Priority:   {priority}\n        '
                'Cipher:     {keyslot_cipher}\n        Cipher key: {cipher_key_size} bits\n        '
                'PBKDF:      {pbkdf}\n        Time cost:  {time_cost}\n        Memory:     {memory}\n        '
                'Threads:    {threads}\n        Salt:       {key_salt} \n        AF stripes: {af_stripes}\n        '
                'AF hash:    {af_hash}\n        Area offset:{keyslot_offset} [bytes]\n        '
                'Area length:{keyslot_length} [bytes]\n        Digest ID:  {keyslot_id}\nTokens:\nDigests:\n  '
                '0: pbkdf2\n        Hash:       {token_hash}\n        Iterations: {token_iterations}\n        '
                'Salt:       {token_salt}\n        Digest:     {token_digest}\n\n')
        info = parse.parse(_tpl, _info).named
        for k, v in info.items():
            # Technically we can do this in the _tpl string, but it's hard to visually parse.
            if k in ('af_stripes', 'cipher_key_size', 'epoch_ver', 'header_ver', 'key_size', 'keyslot_id',
                     'keyslot_length', 'keyslot_offset', 'keyslots_pos', 'memory', 'metadata_pos', 'offset_bytes',
                     'sector_size', 'threads', 'time_cost', 'token_iterations'):
                v = int(v)
            elif k in ('key_salt', 'token_digest', 'token_salt'):
                v = bytes.fromhex(re.sub(r'\s+', '', v))
            elif k in ('label', 'subsystem'):
                if re.search(r'\(no\s+', v.lower()):
                    v = None
            elif k == 'flags':
                if v.lower() == '(no flags)':
                    v = []
                else:
                    # Is this pace-separated or comma-separated? TODO.
                    v = [i.strip() for i in v.split() if i.strip() != '']
            elif k == 'uuid':
                v = uuid.UUID(hex = v)
        self.info = info
        _logger.debug('Rendered updated info: {0}'.format(self.inf))
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
