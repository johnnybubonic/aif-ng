import copy
import io
import logging
import os
import shutil
import tempfile
##
import gpg
import gpg.errors


_logger = logging.getLogger(__name__)


class KeyEditor(object):
    def __init__(self):
        self.trusted = False
        _logger.info('Key editor instantiated.')

    def truster(self, kw, arg, *args, **kwargs):
        _logger.debug('Key trust editor invoked:')
        _logger.debug('Command: {0}'.format(kw))
        _logger.debug('Argument: {0}'.format(arg))
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        if kw == 'GET_LINE':
            if arg == 'keyedit.prompt':
                if not self.trusted:
                    _logger.debug('Returning: "trust"')
                    return('trust')
                else:
                    _logger.debug('Returning: "save"')
                    return('save')
            elif arg == 'edit_ownertrust.value' and not self.trusted:
                self.trusted = True
                _logger.debug('Status changed to trusted')
                _logger.debug('Returning: "4"')
                return('4')  # "Full"
            else:
                _logger.debug('Returning: "save"')
                return('save')
        return(None)


class GPG(object):
    def __init__(self, home = None, primary_key = None, *args, **kwargs):
        self.home = home
        self.primary_key = primary_key
        self.temporary = None
        self.ctx = None
        self._imported_keys = []
        _logger.debug('Homedir: {0}'.format(self.home))
        _logger.debug('Primary key: {0}'.format(self.primary_key))
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        _logger.info('Instantiated GPG class.')
        self._initContext()

    def _initContext(self):
        if not self.home:
            self.home = tempfile.mkdtemp(prefix = '.aif.', suffix = '.gpg')
            self.temporary = True
            _logger.debug('Set as temporary home.')
        self.home = os.path.abspath(os.path.expanduser(self.home))
        _logger.debug('Homedir finalized: {0}'.format(self.home))
        if not os.path.isdir(self.home):
            os.makedirs(self.home, exist_ok = True)
            os.chmod(self.home, 0o0700)
            _logger.info('Created {0}'.format(self.home))
        self.ctx = gpg.Context(home_dir = self.home)
        if self.temporary:
            self.primary_key = self.createKey('AIF-NG File Verification Key',
                                              sign = True,
                                              force = True,
                                              certify = True).fpr
        self.primary_key = self.findKeyByID(self.primary_key, source = 'secret')
        if self.primary_key:
            _logger.debug('Found primary key in secret keyring: {0}'.format(self.primary_key.fpr))
        else:
            _logger.error('Could not find primary key in secret keyring: {0}'.format(self.primary_key))
            raise RuntimeError('Primary key not found in secret keyring')
        self.ctx.signers = [self.primary_key]
        if self.ctx.signers:
            _logger.debug('Signers set to: {0}'.format(','.join([k.fpr for k in self.ctx.signers])))
        else:
            raise _logger.error('Could not assign signing keys; signing set empty')
        return(None)

    def clean(self):
        # This is mostly just to cleanup the stuff we did before.
        _logger.info('Cleaning GPG home.')
        self.primary_key = self.primary_key.fpr
        if self.temporary:
            self.primary_key = None
            shutil.rmtree(self.home)
            _logger.info('Deleted temporary GPG home: {0}'.format(self.home))
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
        _logger.debug('Key creation parameters: {0}'.format(keyinfo))
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        if not keyinfo['expires_in']:
            del(keyinfo['expires_in'])
            keyinfo['expires'] = False
        k = self.ctx.create_key(**keyinfo)
        _logger.info('Created key: {0}'.format(k.fpr))
        _logger.debug('Key info: {0}'.format(k))
        return(k)

    def findKey(self, searchstr, secret = False, local = True, remote = True,
                secret_only = False, keyring_import = False, *args, **kwargs):
        fltr = 0
        if secret:
            fltr = fltr | gpg.constants.KEYLIST_MODE_WITH_SECRET
            _logger.debug('Added "secret" to filter; new filter value: {0}'.format(fltr))
        if local:
            fltr = fltr | gpg.constants.KEYLIST_MODE_LOCAL
            _logger.debug('Added "local" to filter; new filter value: {0}'.format(fltr))
        if remote:
            fltr = fltr | gpg.constants.KEYLIST_MODE_EXTERN
            _logger.debug('Added "remote" to filter; new filter value: {0}'.format(fltr))
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        keys = [k for k in self.ctx.keylist(pattern = searchstr, secret = secret_only, mode = fltr)]
        _logger.info('Found {0} keys'.format(len(keys)))
        if keys:
            _logger.debug('Found keys: {0}'.format(keys))
        else:
            _logger.warning('Found no keys.')
        if keyring_import:
            _logger.debug('Importing enabled; importing found keys.')
            self.importKeys(keys, native = True)
        return(keys)

    def findKeyByID(self, key_id, source = 'remote', keyring_import = False, *args, **kwargs):
        # So .get_key() CAN get a remote key from a keyserver... but you can't have ANY other keylist modes defined.
        # Ugh.
        sources = {'remote': gpg.constants.KEYLIST_MODE_EXTERN,
                   'local': gpg.constants.KEYLIST_MODE_LOCAL,
                   'secret': gpg.constants.KEYLIST_MODE_WITH_SECRET}
        if source not in sources.keys():
            _logger.error('Invalid source parameter ({0}); must be one of: {1}'.format(source, sources.keys()))
            raise ValueError('Invalid source parameter')
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        orig_mode = self.ctx.get_keylist_mode()
        _logger.debug('Original keylist mode: {0}'.format(orig_mode))
        self.ctx.set_keylist_mode(sources[source])
        _logger.info('Set keylist mode: {0} ({1})'.format(source, sources[source]))
        _logger.debug('Searching for key ID: {0}'.format(key_id))
        try:
            key = self.ctx.get_key(key_id, secret = (True if source == 'secret' else False))
            _logger.info('Found key object for {0}'.format(key_id))
            _logger.debug('Found key: {0}'.format(key))
        except gpg.errors.KeyNotFound:
            key = None
            _logger.warning('Found no keys.')
        self.ctx.set_keylist_mode(orig_mode)
        _logger.info('Restored keylist mode ({0})'.format(orig_mode))
        if keyring_import and key:
            _logger.debug('Importing enabled; importing found keys.')
            self.importKeys(key, native = True)
        return(key)

    def getKey(self, key_id, secret = False, strict = False, *args, **kwargs):
        key = None
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        try:
            getattr(key_id, 'fpr')
            _logger.info('Key specified is already a native key object.')
            _logger.debug('Key: {0}'.format(key_id))
            return(key_id)
        except AttributeError:
            if not strict:
                _logger.debug('Strict mode disabled; attempting import of {0} first.'.format(key_id))
                self.findKeyByID(key_id, keyring_import = True, **kwargs)
            try:
                key = self.ctx.get_key(key_id, secret = secret)
                _logger.info('Found {0}.'.format(key_id))
                _logger.debug('Key: {0}'.format(key))
            except gpg.errors.KeyNotFound:
                _logger.warning('Could not locate {0} in keyring'.format(key_id))
        return(key)

    def getKeyData(self, keydata, keyring_import = False, *args, **kwargs):
        orig_keydata = keydata
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        if isinstance(keydata, str):
            _logger.debug('String passed as keydata; converting to bytes.')
            keydata = keydata.encode('utf-8')
        buf = io.BytesIO(keydata)
        _logger.info('Parsed {0} bytes; looking for key(s).'.format(buf.getbuffer().nbytes))
        keys = [k for k in self.ctx.keylist(source = buf)]
        _logger.info('Found {0} key(s) in data.'.format(len(keys)))
        if keys:
            _logger.debug('Keys found: {0}'.format(keys))
        else:
            _logger.warning('No keys found in data.')
        buf.close()
        if keyring_import:
            _logger.debug('Importing enabled; importing found keys.')
            self.importKeys(keys, native = True)
        return((keys, orig_keydata))

    def getKeyFile(self, keyfile, keyring_import = False, *args, **kwargs):
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        orig_keyfile = keyfile
        keyfile = os.path.abspath(os.path.expanduser(keyfile))
        _logger.info('Parsed absolute keyfile path: {0} => {1}'.format(orig_keyfile, keyfile))
        with open(keyfile, 'rb') as fh:
            rawkey_data = fh.read()
            fh.seek(0, 0)
            _logger.debug('Parsed {0} bytes; looking for key(s).'.format(len(rawkey_data)))
            keys = [k for k in self.ctx.keylist(source = fh)]
            _logger.info('Found {0} key(s) in data.'.format(len(keys)))
            if keys:
                _logger.debug('Keys found: {0}'.format(keys))
            else:
                _logger.warning('No keys found in data.')
        if keyring_import:
            _logger.debug('Importing enabled; importing found keys.')
            self.importKeys(keys, native = True)
        return((keys, rawkey_data))

    def importKeys(self, keydata, native = False, local = True, remote = True, *args, **kwargs):
        fltr = 0
        orig_km = None
        keys = []
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        if local:
            fltr = fltr | gpg.constants.KEYLIST_MODE_LOCAL
            _logger.debug('Added "local" to filter; new filter value: {0}'.format(fltr))
        if remote:
            fltr = fltr | gpg.constants.KEYLIST_MODE_EXTERN
            _logger.debug('Added "remote" to filter; new filter value: {0}'.format(fltr))
        if self.ctx.get_keylist_mode() != fltr:
            orig_km = self.ctx.get_keylist_mode()
            self.ctx.set_keylist_mode(fltr)
            _logger.info(('Current keylist mode ({0}) doesn\'t match filter ({1}); '
                          'set to new mode.').format(orig_km, fltr))
        if not native:  # It's raw key data (.gpg, .asc, etc.).
            _logger.info('Non-native keydata specified; parsing.')
            formatted_keys = b''
            if isinstance(keydata, str):
                formatted_keys += keydata.encode('utf-8')
                _logger.debug('Specified keydata was a string; converted to bytes.')
            elif isinstance(keydata, list):
                _logger.debug('Specified keydata was a list/list-like; iterating.')
                for idx, k in enumerate(keydata):
                    _logger.debug('Parsing entry {0} of {1} entries.'.format((idx + 1), len(keydata)))
                    if isinstance(k, str):
                        formatted_keys += k.encode('utf-8')
                        _logger.debug('Keydata ({0}) was a string; converted to bytes.'.format((idx + 1)))
                    else:
                        _logger.debug('Keydata ({0}) was already in bytes.'.format((idx + 1)))
                        formatted_keys += k
            else:
                _logger.warning('Could not identify keydata reliably; unpredictable results ahead.')
                formatted_keys = keydata
            rslt = self.ctx.key_import(formatted_keys).imports
            _logger.debug('Imported keys: {0}'.format(rslt))
            for r in rslt:
                k = self.ctx.get_key(r.fpr)
                if k:
                    _logger.debug('Adding key to keylist: {0}'.format(k))
                else:
                    _logger.warning('Could not find key ID {0}.'.format(r.fpr))
                keys.append(k)
        else:  # It's a native Key() object (or a list of them).
            _logger.info('Native keydata specified; parsing.')
            if not isinstance(keydata, list):
                _logger.debug('Specified keydata was not a list/list-like; fixing.')
                keydata = [keydata]
            keys = keydata
            _logger.debug('Importing keys: {0}'.format(keys))
            self.ctx.op_import_keys(keydata)
        if orig_km:
            self.ctx.set_keylist_mode(orig_km)
            _logger.info('Restored keylist mode to {0}'.format(orig_km))
        for k in keys:
            _logger.info('Signing {0} with a local signature.'.format(k.fpr))
            self.ctx.key_sign(k, local = True)
            _logger.debug('Adding trust for {0}.'.format(k.fpr))
            trusteditor = KeyEditor()
            self.ctx.interact(k, trusteditor.truster)
        return(None)

    def verifyData(self, data, keys = None, strict = False, detached = None, *args, **kwargs):
        results = {}
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        if keys:
            _logger.info('Keys were specified.')
            if not isinstance(keys, list):
                keys = [self.getKey(keys, source = 'local')]
            else:
                keys = [self.getKey(k, source = 'local') for k in keys]
            _logger.debug('Verifying against keys: {0}'.format(keys))
        if isinstance(data, str):
            data = data.encode('utf-8')
            _logger.debug('Specified data was a string; converted to bytes.')
        _logger.info('Verifying {0} bytes of data.'.format(len(data)))
        fnargs = {'signed_data': data}
        if detached:
            _logger.info('Specified a detached signature.')
            if isinstance(detached, str):
                detached = detached.encode('utf-8')
                _logger.debug('Specified signature was a string; converted to bytes.')
            if not isinstance(detached, bytes) and not hasattr(detached, 'read'):
                _logger.error('Detached signature was neither bytes nor a buffer-like object.')
                raise TypeError('detached must be bytes or buffer-like object')
            if isinstance(detached, bytes):
                _logger.info('Signature length: {0} bytes'.format(len(detached)))
            else:
                _logger.info('Signature length: {0} bytes'.format(detached.getbuffer().nbytes))
            fnargs['signature'] = detached
        if strict:
            _logger.debug('Strict mode enabled; data must be signed by ALL specified keys.')
            fnargs['verify'] = keys
            _logger.debug('Verifying with args: {0}'.format(fnargs))
            results[None] = self.ctx.verify(**fnargs)
        else:
            if keys:
                _logger.debug('Keys were specified but running in non-strict; iterating over all.')
                for k in keys:
                    _fnargs = copy.deepcopy(fnargs)
                    _fnargs['verify'] = [k]
                    _logger.info('Verifying against key {0}'.format(k.fpr))
                    try:
                        _logger.debug(('Verifying with args (data-stripped): '
                                       '{0}').format({k: (v if k not in ('signed_data',
                                                                         'signature')
                                                          else '(stripped)') for k, v in _fnargs.items()}))
                        sigchk = self.ctx.verify(**_fnargs)
                        _logger.info('Key {0} verification results: {1}'.format(k.fpr, sigchk))
                        results[k.fpr] = (True, sigchk[1], None)
                    except gpg.errors.MissingSignatures as e:
                        _logger.warning('Key {0}: missing signature'.format(k.fpr))
                        _logger.debug('Key {0} results: {1}'.format(k.fpr, e.results))
                        results[k.fpr] = (False, e.results, 'Missing Signature')
                    except gpg.errors.BadSignatures as e:
                        _logger.warning('Key {0}: bad signature'.format(k.fpr))
                        _logger.debug('Key {0} results: {1}'.format(k.fpr, e.results))
                        results[k.fpr] = (False, e.results, 'Bad Signature')
            else:
                _logger.debug('No keys specified but running in non-strict; accepting any signatures.')
                _logger.debug(('Verifying with args (data-stripped): '
                               '{0}').format({k: (v if k not in ('signed_data',
                                                                 'signature')
                                                  else '(stripped)') for k, v in fnargs.items()}))
                results[None] = self.ctx.verify(**fnargs)
                _logger.debug('Results for any/all signatures: {0}'.format(results[None]))
        return(results)

    def verifyFile(self, filepath, *args, **kwargs):
        orig_filepath = filepath
        filepath = os.path.abspath(os.path.expanduser(filepath))
        _logger.debug('File verification invoked. Transformed filepath: {0} => {1}'.format(orig_filepath, filepath))
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        with open(filepath, 'rb') as fh:
            results = self.verifyData(fh.read(), **kwargs)
        return(results)
