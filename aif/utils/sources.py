import ftplib
import io
import pathlib
import re
##
import requests
import requests.auth
##
import aif.constants_fallback
from . import gpg_handler
from . import hash_handler
from . import parser


class ChecksumFile(object):
    _bsd_re = re.compile(r'^(?P<fname>\(.*\))\s+=\s+(?P<cksum>.*)$')

    def __init__(self, checksum_xml, filetype):
        self.xml = checksum_xml
        self.uri = self.xml.text.strip()
        self.filetype = filetype
        self.hashes = None
        downloader = getDLHandler(self.uri)  # Recursive objects for the win?
        dl = downloader(self.xml)
        dl.get()
        self.data = dl.data.read()
        dl.data.seek(0, 0)
        self._convert()

    def _convert(self):
        data = self.data
        if not isinstance(data, str):
            data = data.decode('utf-8')
        data.strip()
        self.hashes = {}
        if self.filetype not in ('gnu', 'bsd'):
            raise ValueError('filetype attribute must be either "gnu" or "bsd"')
        for line in data.splitlines():
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
        return(None)


class Downloader(object):
    def __init__(self, netresource_xml, *args, **kwargs):
        self.xml = netresource_xml
        self.uri = parser.URI(self.xml.text.strip())
        self.user = self.xml.attrib.get('user')
        if not self.user and self.uri.user:
            self.user = self.uri.user
        self.password = self.xml.attrib.get('password')
        if not self.password and self.uri.password:
            self.password = self.uri.password
        self.real_uri = ('{0}://'
                         '{1}'
                         '{2}'
                         '{3}').format(self.uri.scheme,
                                       (self.uri.base if self.uri.base else ''),
                                       (':{0}'.format(self.uri.port) if self.uri.port else ''),
                                       self.uri.path)
        self.gpg = None
        self.checksum = None
        self.data = io.BytesIO()

    def get(self):
        pass  # Dummy method.
        return(None)

    def parseGpgVerify(self, results):
        pass

    def verify(self, verify_xml, *args, **kwargs):
        gpg_xml = verify_xml.find('gpg')
        hash_xml = verify_xml.find('hash')
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
        keys_xml = gpg_xml.find('keys')
        sigs_xml = gpg_xml.find('sigs')
        fnargs = {'keyring_import': True}
        fnargs.update(kwargs)
        if keys_xml is not None:
            fnargs['keys'] = []
            for key_id_xml in keys_xml.findall('keyID'):
                if key_id_xml.text == 'auto':
                    k = self.gpg.findKeyByID(aif.constants_fallback.ARCH_RELENG_KEY, **fnargs)
                elif key_id_xml.text == 'detect':
                    fnargs['strict'] = False
                    continue
                else:
                    k = self.gpg.findKeyByID(key_id_xml.text.strip(), **fnargs)
                fnargs['keys'].append(k)
            for key_file_xml in keys_xml.findall('keyFile'):
                downloader = getDLHandler(key_file_xml.text.strip())  # Recursive objects for the win?
                dl = downloader(key_file_xml)
                dl.get()
                k = self.gpg.getKeyData(dl.data.read(), **fnargs)[0]
                dl.data.seek(0, 0)
                fnargs['keys'].extend(k)
        if sigs_xml is not None:
            for sig_text_xml in sigs_xml.findall('signature'):
                sig = sig_text_xml.text.strip()
                sigchk = self.gpg.verifyData(self.data.read(), detached = sig, **fnargs)
                self.data.seek(0, 0)
                results.update(sigchk)
            for sig_file_xml in sigs_xml.findall('signatureFile'):
                downloader = getDLHandler(sig_file_xml.text.strip())
                dl = downloader(sig_file_xml)
                dl.get()
                sigchk = self.gpg.verifyData(self.data.read(), detached = dl.data.read(), **fnargs)
                dl.data.seek(0, 0)
                self.data.seek(0, 0)
                results.update(sigchk)
        self.gpg.clean()
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
        if checksum_file_xml is not None:
            for cksum_xml in checksum_file_xml:
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
                results.append(result)
        if checksum_xml is not None:
            for cksum_xml in checksum_xml:
                # Thankfully, this is a LOT easier.
                htype = cksum_xml.attrib['hashType'].strip().lower()
                result = (cksum_xml.text.strip().lower() == checksums[htype])
                results.append(result)
        result = all(results)
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

    def _connect(self):
        self._conn = ftplib.FTP()
        self._conn.connect(host = self.uri.base, port = self.port)
        self._conn.login(user = self.user, passwd = self.password)
        return(None)

    def get(self):
        self._connect()
        self.data.seek(0, 0)
        self._conn.retrbinary('RETR {0}'.format(self.uri.path), self.data.write)
        self.data.seek(0, 0)
        self._close()
        return(None)

    def _close(self):
        self._conn.quit()
        return(None)


class FTPSDownloader(FTPDownloader):
    def __init__(self, netresource_xml, *args, **kwargs):
        super().__init__(netresource_xml, *args, **kwargs)

    def _connect(self):
        self._conn = ftplib.FTP_TLS()
        self._conn.connect(host = self.uri.base, port = self.port)
        self._conn.login(user = self.user, passwd = self.password)
        self._conn.prot_p()
        return(None)


class HTTPDownloader(Downloader):
    def __init__(self, netresource_xml, *args, **kwargs):
        super().__init__(netresource_xml, *args, **kwargs)
        self.auth = self.xml.attrib.get('authType', 'none').lower()
        if self.auth == 'none':
            self.auth = None
            self.realm = None
            self.user = None
            self.password = None
        else:
            if self.auth == 'basic':
                self.auth = requests.auth.HTTPBasicAuth(self.user, self.password)
            elif self.auth == 'digest':
                self.auth = requests.auth.HTTPDigestAuth(self.user, self.password)

    def get(self):
        self.data.seek(0, 0)
        req = requests.get(self.real_uri, auth = self.auth)
        self.data.write(req.content)
        self.data.seek(0, 0)
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
        raise RuntimeError('Could not detect which download handler to use')
    return(None)
