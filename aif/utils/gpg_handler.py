import copy
import io
import os
import shutil
import tempfile
##
import gpg
import gpg.errors


class GPG(object):
    def __init__(self, homedir = None, primary_key = None):
        self.homedir = homedir
        self.primary_key = primary_key
        self.temporary = None
        self.gpg = None
        self._imported_keys = []

    def _initContext(self):
        if not self.homedir:
            self.homedir = tempfile.mkdtemp(suffix = '.gpg', prefix = '.aif.')
        self.homedir = os.path.abspath(os.path.expanduser(self.homedir))
        self.temporary = False
        if not os.path.isdir(self.homedir):
            self.temporary = True
            os.makedirs(self.homedir, exist_ok = True)
            os.chmod(self.homedir, 0o0700)
        self.gpg = gpg.Context(home_dir = self.homedir)
        if self.temporary:
            self.primary_key = self.createKey('AIF-NG File Verification Key', sign = True, force = True)
        else:
            self.primary_key = self.getKey(self.primary_key, secret = True)
        return(None)

    def clean(self):
        # This is mostly just to cleanup the stuff we did before.
        self.primary_key = self.primary_key.fpr
        if self.temporary:
            self.primary_key = None
            shutil.rmtree(self.homedir)
        self.gpg = None
        return(None)

    def createKey(self, userid, *args, **kwargs):
        # algorithm=None, expires_in=0, expires=True, sign=False, encrypt=False, certify=False,
        # authenticate=False, passphrase=None, force=False
        keyinfo = {'userid': userid,
                   'algorithm': kwargs.get('algorithm', 'rsa4096'),
                   'expires_in': kwargs.get('expires_in'),
                   'sign': kwargs.get('sign', True),
                   'encrypt': kwargs.get('encrypt', False),
                   'certify': kwargs.get('certify', False),
                   'authenticate': kwargs.get('authenticate', False),
                   'passphrase': kwargs.get('passphrase'),
                   'force': kwargs.get('force')}
        if not keyinfo['expires_in']:
            del(keyinfo['expires_in'])
            keyinfo['expires'] = False
        k = self.gpg.create_key(**keyinfo)
        return(k.fpr)

    def findKey(self, searchstr, secret = False, local = True, remote = True,
                secret_only = False, keyring_import = False):
        fltr = 0
        if secret:
            fltr = fltr | gpg.constants.KEYLIST_MODE_WITH_SECRET
        if local:
            fltr = fltr | gpg.constants.KEYLIST_MODE_LOCAL
        if remote:
            fltr = fltr | gpg.constants.KEYLIST_MODE_EXTERN
        keys = [k for k in self.gpg.keylist(pattern = searchstr, secret = secret_only, mode = fltr)]
        if keyring_import:
            self.importKeys(keys, native = True)
        return(keys)

    def getKey(self, key_id, secret = False, strict = False):
        try:
            getattr(key_id, 'fpr')
            return(key_id)
        except AttributeError:
            if not strict:
                self.findKey(key_id, keyring_import = True)
            try:
                key = self.gpg.get_key(key_id, secret = secret)
            except gpg.errors.KeyNotFound:
                key = None
            return(key)
        return(None)

    def getKeyFile(self, keyfile, keyring_import = False):
        keyfile = os.path.abspath(os.path.expanduser(keyfile))
        with open(keyfile, 'rb') as fh:
            rawkey_data = fh.read()
            fh.seek(0, 0)
            keys = [k for k in self.gpg.keylist(source = fh)]
        if keyring_import:
            self.importKeys(keys, native = True)
        return((keys, rawkey_data))

    def getKeyStr(self, keydata, keyring_import = False):
        orig_keydata = keydata
        if isinstance(keydata, str):
            keydata = keydata.encode('utf-8')
        buf = io.BytesIO(keydata)
        keys = [k for k in self.gpg.keylist(source = buf)]
        buf.close()
        if keyring_import:
            self.importKeys(keys, native = True)
        return((keys, orig_keydata))

    def importKeys(self, keydata, native = False):
        if not native:
            self.gpg.key_import(keydata)
        else:
            if not isinstance(keydata, list):
                keydata = [keydata]
            self.gpg.op_import_keys(keydata)
        return(None)

    def verifyData(self, data, keys = None, strict = False, detached = None, *args, **kwargs):
        results = {}
        if keys:
            if not isinstance(keys, list):
                keys = [self.getKey(keys)]
            else:
                keys = [self.getKey(k) for k in keys]
        if isinstance(data, str):
            data = data.encode('utf-8')
        args = {'signed_data': data}
        if detached:
            if isinstance(detached, str):
                detached = detached.encode('utf-8')
            args['signature'] = detached
        if strict:
            if keys:
                if not isinstance(keys, list):
                    keys = [keys]
                args['verify'] = keys
            results[None] = self.gpg.verify(**args)
        else:
            if keys:
                for k in keys:
                    _args = copy.deepcopy(args)
                    _args['verify'] = [k]
                    results[k.fpr] = self.gpg.verify(**_args)
            else:
                results[None] = self.gpg.verify(**args)
        return(results)

    def verifyFile(self, filepath, *args, **kwargs):
        filepath = os.path.abspath(os.path.expanduser(filepath))
        with open(filepath, 'rb') as fh:
            results = self.verifyData(fh.read(), **kwargs)
        return(results)
