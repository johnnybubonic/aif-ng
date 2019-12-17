import copy
import hashlib
import os
import pathlib
import zlib
##
import aif.constants_fallback


class Hash(object):
    def __init__(self, hash_algos = None, *args, **kwargs):
        self.hashers = None
        self.valid_hashtypes = list(aif.constants_fallback.HASH_SUPPORTED_TYPES)
        self.hash_algos = hash_algos
        self.configure()

    def configure(self, *args, **kwargs):
        self.hashers = {}
        if self.hash_algos:
            if not isinstance(self.hash_algos, list):
                self.hash_algos = [self.hash_algos]
        else:
            self.hash_algos = copy.deepcopy(self.valid_hashtypes)
        for h in self.hash_algos:
            if h not in self.valid_hashtypes:
                raise ValueError('Hash algorithm not supported')
            if h not in aif.constants_fallback.HASH_EXTRA_SUPPORTED_TYPES:
                hasher = hashlib.new(h)
            else:  # adler32 and crc32
                hasher = getattr(zlib, h)
            self.hashers[h] = hasher
        return()

    def hashData(self, data, *args, **kwargs):
        results = {}
        if not self.hashers or not self.hash_algos:
            self.configure()
        for hashtype, hasher in self.hashers.items():
            if hashtype in aif.constants_fallback.HASH_EXTRA_SUPPORTED_TYPES:
                results[hashtype] = hasher(data)
            else:
                hasher.update(data)
                results[hashtype] = hasher.hexdigest()
        return(results)

    def hashFile(self, file_path, *args, **kwargs):
        if not isinstance(file_path, (str, pathlib.Path, pathlib.PurePath)):
            raise ValueError('file_path must be a path expression')
        file_path = str(file_path)
        with open(file_path, 'rb') as fh:
            results = self.hashData(fh.read())
        return(results)

    def verifyData(self, data, checksum, checksum_type, *args, **kwargs):
        if isinstance(data, str):
            data = data.encode('utf-8')
        if not isinstance(checksum, str):
            checksum = checksum.decode('utf-8')
        if checksum_type not in self.hash_algos:
            raise ValueError('Hash algorithm not supported; try reconfiguring')
        self.configure()
        cksum = self.hashData(data)
        cksum_htype = cksum[checksum_type]
        if cksum == checksum:
            result = True
        else:
            result = False
        return(result)

    def verifyFile(self, filepath, checksum, checksum_type, *args, **kwargs):
        filepath = os.path.abspath(os.path.expanduser(filepath))
        with open(filepath, 'rb') as fh:
            result = self.verifyData(fh.read(), checksum, checksum_type, **kwargs)
        return(result)
