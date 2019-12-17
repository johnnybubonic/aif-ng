import copy
import io
import os
import shutil
import tempfile
##
import gpg
import gpg.errors


class KeyEditor(object):
    def __init__(self):
        self.trusted = False

    def truster(self, kw, arg, *args, **kwargs):
        if kw == 'GET_LINE':
            if arg == 'keyedit.prompt':
                if not self.trusted:
                    return('trust')
                else:
                    return('save')
            elif arg == 'edit_ownertrust.value' and not self.trusted:
                self.trusted = True
                return('4')  # "Full"
            else:
                return('save')
        return(None)


class GPG(object):
    def __init__(self, homedir = None, primary_key = None, *args, **kwargs):
        self.homedir = homedir
        self.primary_key = primary_key
        self.temporary = None
        self.ctx = None
        self._imported_keys = []
        self._initContext()

    def _initContext(self):
        if not self.homedir:
            self.homedir = tempfile.mkdtemp(suffix = '.gpg', prefix = '.aif.')
            self.temporary = True
        self.homedir = os.path.abspath(os.path.expanduser(self.homedir))
        if not os.path.isdir(self.homedir):
            os.makedirs(self.homedir, exist_ok = True)
            os.chmod(self.homedir, 0o0700)
        self.ctx = gpg.Context(home_dir = self.homedir)
        if self.temporary:
            self.primary_key = self.createKey('AIF-NG File Verification Key', sign = True, force = True).fpr
        self.primary_key = self.findKeyByID(self.primary_key, source = 'secret')
        self.ctx.signers = [self.primary_key]
        return(None)

    def clean(self):
        # This is mostly just to cleanup the stuff we did before.
        self.primary_key = self.primary_key.fpr
        if self.temporary:
            self.primary_key = None
            shutil.rmtree(self.homedir)
        self.ctx = None
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
        k = self.ctx.create_key(**keyinfo)
        return(k)

    def findKey(self, searchstr, secret = False, local = True, remote = True,
                secret_only = False, keyring_import = False, *args, **kwargs):
        fltr = 0
        if secret:
            fltr = fltr | gpg.constants.KEYLIST_MODE_WITH_SECRET
        if local:
            fltr = fltr | gpg.constants.KEYLIST_MODE_LOCAL
        if remote:
            fltr = fltr | gpg.constants.KEYLIST_MODE_EXTERN
        keys = [k for k in self.ctx.keylist(pattern = searchstr, secret = secret_only, mode = fltr)]
        if keyring_import:
            self.importKeys(keys, native = True)
        return(keys)

    def findKeyByID(self, key_id, source = 'remote', keyring_import = False, *args, **kwargs):
        # So .get_key() CAN get a remote key from a keyserver... but you can't have ANY other keylist modes defined.
        # Ugh.
        sources = {'remote': gpg.constants.KEYLIST_MODE_EXTERN,
                   'local': gpg.constants.KEYLIST_MODE_LOCAL,
                   'secret': gpg.constants.KEYLIST_MODE_WITH_SECRET}
        if source not in sources.keys():
            raise ValueError('source parameter must be one (and only one) of: {0}'.format(sources.keys()))
        orig_mode = self.ctx.get_keylist_mode()
        self.ctx.set_keylist_mode(sources[source])
        try:
            key = self.ctx.get_key(key_id, secret = (True if source == 'secret' else False))
        except gpg.errors.KeyNotFound:
            key = None
        self.ctx.set_keylist_mode(orig_mode)
        if keyring_import and key:
            self.importKeys(key, native = True)
        return(key)

    def getKey(self, key_id, secret = False, strict = False, *args, **kwargs):
        try:
            getattr(key_id, 'fpr')
            return(key_id)
        except AttributeError:
            if not strict:
                self.findKeyByID(key_id, keyring_import = True, **kwargs)
            try:
                key = self.ctx.get_key(key_id, secret = secret)
            except gpg.errors.KeyNotFound:
                key = None
            return(key)
        return(None)

    def getKeyFile(self, keyfile, keyring_import = False, *args, **kwargs):
        keyfile = os.path.abspath(os.path.expanduser(keyfile))
        with open(keyfile, 'rb') as fh:
            rawkey_data = fh.read()
            fh.seek(0, 0)
            keys = [k for k in self.ctx.keylist(source = fh)]
        if keyring_import:
            self.importKeys(keys, native = True)
        return((keys, rawkey_data))

    def getKeyData(self, keydata, keyring_import = False, *args, **kwargs):
        orig_keydata = keydata
        if isinstance(keydata, str):
            keydata = keydata.encode('utf-8')
        buf = io.BytesIO(keydata)
        keys = [k for k in self.ctx.keylist(source = buf)]
        buf.close()
        if keyring_import:
            self.importKeys(keys, native = True)
        return((keys, orig_keydata))

    def importKeys(self, keydata, native = False, local = True, remote = True, *args, **kwargs):
        fltr = 0
        orig_km = None
        keys = []
        if local:
            fltr = fltr | gpg.constants.KEYLIST_MODE_LOCAL
        if remote:
            fltr = fltr | gpg.constants.KEYLIST_MODE_EXTERN
        if self.ctx.get_keylist_mode() != fltr:
            orig_km = self.ctx.get_keylist_mode()
            self.ctx.set_keylist_mode(fltr)
        if not native:  # It's raw key data (.gpg, .asc, etc.).
            formatted_keys = b''
            if isinstance(keydata, str):
                formatted_keys += keydata.encode('utf-8')
            elif isinstance(keydata, list):
                for k in keydata:
                    if isinstance(k, str):
                        formatted_keys += k.encode('utf-8')
                    else:
                        formatted_keys += k
            else:
                formatted_keys += keydata
            for rslt in self.ctx.key_import(formatted_keys).imports:
                keys.append(self.ctx.get_key(rslt.fpr))
        else:  # It's a native Key() object (or a list of them).
            if not isinstance(keydata, list):
                keydata = [keydata]
            keys = keydata
            self.ctx.op_import_keys(keydata)
        if orig_km:
            self.ctx.set_keylist_mode(orig_km)
        for k in keys:
            self.ctx.key_sign(k, local = True)
            trusteditor = KeyEditor()
            self.ctx.interact(k, trusteditor.truster)
        return(None)

    def verifyData(self, data, keys = None, strict = False, detached = None, *args, **kwargs):
        results = {}
        if keys:
            if not isinstance(keys, list):
                keys = [self.getKey(keys, source = 'local')]
            else:
                keys = [self.getKey(k, source = 'local') for k in keys]
        if isinstance(data, str):
            data = data.encode('utf-8')
        fnargs = {'signed_data': data}
        if detached:
            if isinstance(detached, str):
                detached = detached.encode('utf-8')
            if not isinstance(detached, bytes) and not hasattr(detached, 'read'):
                raise TypeError('detached must be bytes or a file-like object (make sure the position is correct!)')
            fnargs['signature'] = detached
        if strict:
            fnargs['verify'] = keys
            results[None] = self.ctx.verify(**fnargs)
        else:
            if keys:
                for k in keys:
                    _fnargs = copy.deepcopy(fnargs)
                    _fnargs['verify'] = [k]
                    try:
                        print(self.ctx.get_keylist_mode())
                        sigchk = self.ctx.verify(**_fnargs)
                        results[k.fpr] = (True, sigchk[1].results, None)
                    except gpg.errors.MissingSignatures as e:
                        results[k.fpr] = (False, e.results, 'Missing Signature')
                    except gpg.errors.BadSignatures as e:
                        results[k.fpr] = (False, e.results, 'Bad Signature')
            else:
                results[None] = self.ctx.verify(**fnargs)
        return(results)

    def verifyFile(self, filepath, *args, **kwargs):
        filepath = os.path.abspath(os.path.expanduser(filepath))
        with open(filepath, 'rb') as fh:
            results = self.verifyData(fh.read(), **kwargs)
        return(results)
