import ftplib
import io
import logging
import pathlib
import re
##
import requests
import requests.auth
from lxml import etree
##
import aif.constants_fallback
from . import gpg_handler
from . import hash_handler
from . import parser


_logger = logging.getLogger(__name__)


class ChecksumFile(object):
    _bsd_re = re.compile(r'^(?P<fname>\(.*\))\s+=\s+(?P<cksum>.*)$')

    def __init__(self, checksum_xml, filetype):
        self.xml = checksum_xml
        if self.xml is not None:
            _logger.debug('checksum_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        else:
            _logger.error('checksum_xml is required but not specified')
            raise ValueError('checksum_xml is required')
        self.uri = self.xml.text.strip()
        self.filetype = filetype
        if filetype:
            _logger.debug('URI and filetype: {{{0}}}{1}'.format(self.uri, self.filetype))
        else:
            _logger.error('filetype is required but not specified')
            raise ValueError('filetype is required')
        self.hashes = None
        downloader = getDLHandler(self.uri)  # Recursive objects for the win?
        dl = downloader(self.xml)
        dl.get()
        self.data = dl.data.read()
        dl.data.seek(0, 0)
        self._convert()

    def _convert(self):
        if not isinstance(self.data, str):
            self.data = self.data.decode('utf-8')
        self.data.strip()
        self.hashes = {}
        if self.filetype not in ('gnu', 'bsd'):
            _logger.error('Passed an invalid filetype: {0}'.format(self.filetype))
            raise ValueError('filetype attribute must be either "gnu" or "bsd"')
        for line in self.data.splitlines():
            if self.filetype == 'gnu':
                hashtype = None  # GNU style splits their hash types into separate files by default.
                h, fname = line.split(None, 1)
            elif self.filetype == 'bsd':
                l = line.split(None, 1)
                hashtype = l.pop(0).lower()
                r = self._bsd_re.search(l[0])
                h = r.group('cksum')
                fname = r.group('fname')
            if hashtype not in self.hashes:
                self.hashes[hashtype] = {}
            self.hashes[hashtype][fname] = h
        _logger.debug('Generated hash set: {0}'.format(self.hashes))
        return(None)


class Downloader(object):
    def __init__(self, netresource_xml, *args, **kwargs):
        self.xml = netresource_xml
        _logger.info('Instantiated class {0}'.format(type(self).__name__))
        if netresource_xml is not None:
            _logger.debug('netresource_xml: {0}'.format(etree.tostring(self.xml, with_tail = False).decode('utf-8')))
        else:
            _logger.error('netresource_xml is required but not specified')
            raise ValueError('netresource_xml is required')
        _logger.debug('args: {0}'.format(','.join(args)))
        _logger.debug('kwargs: {0}'.format(kwargs))
        self.uri = parser.URI(self.xml.text.strip())
        _logger.debug('Parsed URI: {0}'.format(self.uri))
        self.user = self.xml.attrib.get('user')
        if not self.user and self.uri.user:
            self.user = self.uri.user
        self.password = self.xml.attrib.get('password')
        _logger.debug('Parsed user: {0}'.format(self.user))
        _logger.debug('Parsed password: {0}'.format(self.password))
        if not self.password and self.uri.password:
            self.password = self.uri.password
        self.real_uri = ('{0}://'
                         '{1}'
                         '{2}'
                         '{3}').format(self.uri.scheme,
                                       (self.uri.base if self.uri.base else ''),
                                       (':{0}'.format(self.uri.port) if self.uri.port else ''),
                                       self.uri.path)
        _logger.debug('Rebuilt URI: {0}'.format(self.real_uri))
        self.gpg = None
        self.checksum = None
        self.data = io.BytesIO()

    def get(self):
        pass  # Dummy method.
        return(None)

    def parseGpgVerify(self, results):
        pass  # TODO? Might not need to.
        return(None)

    def verify(self, verify_xml, *args, **kwargs):
        gpg_xml = verify_xml.find('gpg')
        if gpg_xml is not None:
            _logger.debug('gpg_xml: {0}'.format(etree.tostring(gpg_xml, with_tail = False).decode('utf-8')))
        else:
            _logger.debug('No <gpg> in verify_xml')
        hash_xml = verify_xml.find('hash')
        if hash_xml is not None:
            _logger.debug('hash_xml: {0}'.format(etree.tostring(hash_xml, with_tail = False).decode('utf-8')))
        else:
            _logger.debug('No <hash> in verify_xml')
        results = {}
        if gpg_xml is not None:
            results['gpg'] = self.verifyGPG(gpg_xml)
        if hash_xml is not None:
            results['hash'] = self.verifyHash(hash_xml)
        return(results)

    def verifyGPG(self, gpg_xml, *args, **kwargs):
        results = {}
        # We don't allow custom GPG homedirs since this is probably running from a LiveCD/USB/whatever anyways.
        # This means we can *always* instantiate the GPG handler from scratch.
        self.gpg = gpg_handler.GPG()
        _logger.info('Established GPG session.')
        _logger.debug('GPG home dir: {0}'.format(self.gpg.home))
        _logger.debug('GPG primary key: {0}'.format(self.gpg.primary_key.fpr))
        keys_xml = gpg_xml.find('keys')
        if keys_xml is not None:
            _logger.debug('keys_xml: {0}'.format(etree.tostring(keys_xml, with_tail = False).decode('utf-8')))
        else:
            _logger.error('No required <keys> in gpg_xml')
            raise ValueError('<keys> is required in a GPG verification block')
        sigs_xml = gpg_xml.find('sigs')
        if sigs_xml is not None:
            _logger.debug('sigs_xml: {0}'.format(etree.tostring(sigs_xml, with_tail = False).decode('utf-8')))
        else:
            _logger.error('No required <sigs> in gpg_xml')
            raise ValueError('<sigs> is required in a GPG verification block')
        fnargs = {'strict': keys_xml.attrib.get('detect')}
        if fnargs['strict']:  # We have to manually do this since it's in our parent's __init__
            if fnargs['strict'].lower() in ('true', '1'):
                fnargs['strict'] = True
            else:
                fnargs['strict'] = False
        else:
            fnargs['strict'] = False
        fnargs.update(kwargs)
        if keys_xml is not None:
            fnargs['keys'] = []
            for key_id_xml in keys_xml.findall('keyID'):
                _logger.debug('key_id_xml: {0}'.format(etree.tostring(key_id_xml, with_tail = False).decode('utf-8')))
                if key_id_xml.text == 'auto':
                    _logger.debug('Key ID was set to "auto"; using {0}'.format(aif.constants_fallback.ARCH_RELENG_KEY))
                    self.gpg.findKeyByID(aif.constants_fallback.ARCH_RELENG_KEY, source = 'remote',
                                         keyring_import = True, **fnargs)
                    k = self.gpg.findKeyByID(aif.constants_fallback.ARCH_RELENG_KEY, source = 'local', **fnargs)
                else:
                    _logger.debug('Finding key: {0}'.format(key_id_xml.text.strip()))
                    self.gpg.findKeyByID(key_id_xml.text.strip(), source = 'remote', keyring_import = True, **fnargs)
                    k = self.gpg.findKeyByID(key_id_xml.text.strip(), source = 'local', **fnargs)
                    if k:
                        _logger.debug('Key {0} found'.format(k.fpr))
                    else:
                        _logger.error('Key {0} not found'.format(key_id_xml.text.strip()))
                        raise RuntimeError('Could not find key ID specified')
                fnargs['keys'].append(k)
            for key_file_xml in keys_xml.findall('keyFile'):
                _logger.debug('key_file_xml: {0}'.format(etree.tostring(key_file_xml,
                                                                        with_tail = False).decode('utf-8')))
                downloader = getDLHandler(key_file_xml.text.strip())  # Recursive objects for the win?
                dl = downloader(key_file_xml)
                dl.get()
                k = self.gpg.getKeyData(dl.data.read(), keyring_import = True, **fnargs)[0]
                if k:
                    fnargs['keys'].extend(k)
                else:
                    pass  # No keys found in key file. We log this in GPG.getKeyData() though.
                dl.data.seek(0, 0)
            if not fnargs['keys']:
                _logger.debug('Found no keys in keys_xml')
                raise RuntimeError('Could not find any keys')
        if sigs_xml is not None:
            for sig_text_xml in sigs_xml.findall('signature'):
                _logger.debug('Found <signature>')
                sig = sig_text_xml.text.strip()
                sigchk = self.gpg.verifyData(self.data.read(), detached = sig, **fnargs)
                self.data.seek(0, 0)
                results.update(sigchk)
            for sig_file_xml in sigs_xml.findall('signatureFile'):
                _logger.debug('Found <signatureFile>: {0}'.format(sig_file_xml.text.strip()))
                downloader = getDLHandler(sig_file_xml.text.strip())
                dl = downloader(sig_file_xml)
                dl.get()
                sigchk = self.gpg.verifyData(self.data.read(), detached = dl.data.read(), **fnargs)
                dl.data.seek(0, 0)
                self.data.seek(0, 0)
                results.update(sigchk)
        self.gpg.clean()
        _logger.debug('Rendered results: {0}'.format(results))
        return(results)

    def verifyHash(self, hash_xml, *args, **kwargs):
        results = []
        algos = [str(ht) for ht in hash_xml.xpath('//checksum/@hashType|//checksumFile/@hashType')]
        self.checksum = hash_handler.Hash(hash_algos = algos)
        self.checksum.configure()
        checksum_xml = hash_xml.findall('checksum')
        checksum_file_xml = hash_xml.findall('checksumFile')
        checksums = self.checksum.hashData(self.data.read())
        self.data.seek(0, 0)
        if checksum_file_xml:
            for cksum_xml in checksum_file_xml:
                _logger.debug('cksum_xml: {0}'.format(etree.tostring(cksum_xml, with_tail = False).decode('utf-8')))
                htype = cksum_xml.attrib['hashType'].strip().lower()
                ftype = cksum_xml.attrib['fileType'].strip().lower()
                fname = cksum_xml.attrib.get('filePath',
                                             pathlib.PurePath(self.uri.path).name)
                cksum_file = ChecksumFile(cksum_xml, ftype)
                if ftype == 'gnu':
                    cksum = cksum_file.hashes[None][fname]
                elif ftype == 'bsd':
                    cksum = cksum_file.hashes[htype][fname]
                result = (cksum == checksums[htype])
                if result:
                    _logger.debug('Checksum type {0} matches ({1})'.format(htype, cksum))
                else:
                    _logger.warning(('Checksum type {0} mismatch: '
                                     '{1} (data) vs. {2} (specified)').format(htype, checksums[htype], cksum))
                results.append(result)
        if checksum_xml:
            for cksum_xml in checksum_xml:
                _logger.debug('cksum_xml: {0}'.format(etree.tostring(cksum_xml, with_tail = False).decode('utf-8')))
                # Thankfully, this is a LOT easier.
                htype = cksum_xml.attrib['hashType'].strip().lower()
                result = (cksum_xml.text.strip().lower() == checksums[htype])
                if result:
                    _logger.debug('Checksum type {0} matches ({1})'.format(htype, checksums[htype]))
                else:
                    _logger.warning(('Checksum type {0} mismatch: '
                                     '{1} (data) vs. {2} (specified)').format(htype,
                                                                              checksums[htype],
                                                                              cksum_xml.text.strip().lower()))
                results.append(result)
        result = all(results)
        _logger.debug('Overall result of checksumming: {0}'.format(result))
        return(result)


class FSDownloader(Downloader):
    def __init__(self, netresource_xml, *args, **kwargs):
        super().__init__(netresource_xml, *args, **kwargs)
        delattr(self, 'user')
        delattr(self, 'password')

    def get(self):
        self.data.seek(0, 0)
        with open(self.uri.path, 'rb') as fh:
            self.data.write(fh.read())
        self.data.seek(0, 0)
        _logger.info('Read in {0} bytes'.format(self.data.getbuffer().nbytes))
        return(None)


class FTPDownloader(Downloader):
    def __init__(self, netresource_xml, *args, **kwargs):
        super().__init__(netresource_xml, *args, **kwargs)
        if not self.user:
            self.user = ''
        if not self.password:
            self.password = ''
        self.port = (self.uri.port if self.uri.port else 0)
        self._conn = None
        _logger.debug('User: {0}'.format(self.user))
        _logger.debug('Password: {0}'.format(self.password))
        _logger.debug('Port: {0}'.format(self.port))

    def _connect(self):
        self._conn = ftplib.FTP()
        self._conn.connect(host = self.uri.base, port = self.port)
        self._conn.login(user = self.user, passwd = self.password)
        _logger.info('Connected.')
        return(None)

    def get(self):
        self._connect()
        self.data.seek(0, 0)
        self._conn.retrbinary('RETR {0}'.format(self.uri.path), self.data.write)
        self.data.seek(0, 0)
        self._close()
        _logger.info('Read in {0} bytes'.format(self.data.getbuffer().nbytes))
        return(None)

    def _close(self):
        self._conn.quit()
        _logger.info('Closed connection')
        return(None)


class FTPSDownloader(FTPDownloader):
    def __init__(self, netresource_xml, *args, **kwargs):
        super().__init__(netresource_xml, *args, **kwargs)

    def _connect(self):
        self._conn = ftplib.FTP_TLS()
        self._conn.connect(host = self.uri.base, port = self.port)
        self._conn.login(user = self.user, passwd = self.password)
        self._conn.prot_p()
        _logger.info('Connected.')
        return(None)


class HTTPDownloader(Downloader):
    def __init__(self, netresource_xml, *args, **kwargs):
        super().__init__(netresource_xml, *args, **kwargs)
        self.auth = self.xml.attrib.get('authType', 'none').lower()
        if self.auth == 'none':
            _logger.debug('No auth.')
            self.auth = None
            self.realm = None
            self.user = None
            self.password = None
        else:
            if self.auth == 'basic':
                self.auth = requests.auth.HTTPBasicAuth(self.user, self.password)
                _logger.info('HTTP basic auth configured.')
            elif self.auth == 'digest':
                self.auth = requests.auth.HTTPDigestAuth(self.user, self.password)
                _logger.info('HTTP digest auth configured.')

    def get(self):
        self.data.seek(0, 0)
        req = requests.get(self.real_uri, auth = self.auth)
        if not req.ok:
            _logger.error('Could not fetch remote resource: {0}'.format(self.real_uri))
            raise RuntimeError('Unable to fetch remote resource')
        self.data.write(req.content)
        self.data.seek(0, 0)
        _logger.info('Read in {0} bytes'.format(self.data.getbuffer().nbytes))
        return(None)


def getDLHandler(uri):
    uri = uri.strip()
    if re.search(r'^file://', uri, re.IGNORECASE):
        return(FSDownloader)
    elif re.search(r'^https?://', uri, re.IGNORECASE):
        return(HTTPDownloader)
    elif re.search(r'^ftp://', uri, re.IGNORECASE):
        return(FTPDownloader)
    elif re.search(r'^ftps://', uri, re.IGNORECASE):
        return(FTPSDownloader)
    else:
        _logger.error('Unable to detect which download handler to instantiate.')
        raise RuntimeError('Could not detect which download handler to use')
    return(None)
