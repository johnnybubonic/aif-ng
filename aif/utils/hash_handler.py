import hashlib
import pathlib
import zlib
##
import aif.constants_fallback
from . import file_handler


class Hash(object):
    def __init__(self, file_path):
        self.hashers = None

    def configure(self, hashalgo = None):
        self.hashers = {}
        if hashalgo:
            if not isinstance(hashalgo, list):
                hashalgo = [hashalgo]
        else:
            hashalgo = list(aif.constants_fallback.HASH_SUPPORTED_TYPES)
        for h in hashalgo:
            if h not in aif.constants_fallback.HASH_SUPPORTED_TYPES:
                raise ValueError('Hash algorithm not supported')
            if h not in aif.constants_fallback.HASH_EXTRA_SUPPORTED_TYPES:
                hasher = hashlib.new(h)
            else:  # adler32 and crc32
                hasher = getattr(zlib, h)
            self.hashers[h] = hasher
        return()

    def hashData(self, data):
        results = {}
        if not self.hashers:
            self.configure()
        for hashtype, hasher in self.hashers.items():
            if hashtype in aif.constants_fallback.HASH_EXTRA_SUPPORTED_TYPES:
                results[hashtype] = hasher(data)
            else:
                rslt = hasher.update(data)
                results[hashtype] = rslt.hexdigest()
        return(results)

    def hashFile(self, file_path):
        if not isinstance(file_path, (str, file_handler.File, pathlib.Path, pathlib.PurePath)):
            raise ValueError('file_path must be a path expression')
        file_path = str(file_path)
        with open(file_path, 'rb') as fh:
            results = self.hashData(fh.read())
        return(results)
