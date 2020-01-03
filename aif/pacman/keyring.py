import csv
import logging
import os
import re
import sqlite3
##
import gpg


# We don't use utils.gpg_handler because this is pretty much all procedural.

_logger = logging.getLogger(__name__)


_createTofuDB = """BEGIN TRANSACTION;
CREATE TABLE IF NOT EXISTS "ultimately_trusted_keys" (
        "keyid" TEXT
);
CREATE TABLE IF NOT EXISTS "encryptions" (
        "binding"       INTEGER NOT NULL,
        "time"  INTEGER
);
CREATE TABLE IF NOT EXISTS "signatures" (
        "binding"       INTEGER NOT NULL,
        "sig_digest"    TEXT,
        "origin"        TEXT,
        "sig_time"      INTEGER,
        "time"  INTEGER,
        PRIMARY KEY("binding","sig_digest","origin")
);
CREATE TABLE IF NOT EXISTS "bindings" (
        "oid"   INTEGER PRIMARY KEY AUTOINCREMENT,
        "fingerprint"   TEXT,
        "email" TEXT,
        "user_id"       TEXT,
        "time"  INTEGER,
        "policy"        INTEGER CHECK(policy in (1,2,3,4,5)),
        "conflict"      STRING,
        "effective_policy"      INTEGER DEFAULT 0 CHECK(effective_policy in (0,1,2,3,4,5)),
        UNIQUE("fingerprint","email")
);
CREATE TABLE IF NOT EXISTS "version" (
        "version"       INTEGER
);
INSERT INTO "version" ("version") VALUES (1);
CREATE INDEX IF NOT EXISTS "encryptions_binding" ON "encryptions" (
        "binding"
);
CREATE INDEX IF NOT EXISTS "bindings_email" ON "bindings" (
        "email"
);
CREATE INDEX IF NOT EXISTS "bindings_fingerprint_email" ON "bindings" (
        "fingerprint",
        "email"
);
COMMIT;"""


class KeyEditor(object):
    def __init__(self, trustlevel = 4):
        self.trusted = False
        self.revoked = False
        self.trustlevel = trustlevel
        _logger.info('Key editor instantiated.')

    def revoker(self, kw, arg, *args, **kwargs):
        # The "save" commands here can also be "quit".
        _logger.debug('Key revoker invoked:')
        _logger.debug('Command: {0}'.format(kw))
        _logger.debug('Argument: {0}'.format(arg))
        if args:
            _logger.debug('args: {0}'.format(','.join(args)))
        if kwargs:
            _logger.debug('kwargs: {0}'.format(kwargs))
        if kw == 'GET_LINE':
            if arg == 'keyedit.prompt':
                if not self.revoked:
                    _logger.debug('Returning: "disable"')
                    self.revoked = True
                    return('disable')
                else:
                    _logger.debug('Returning: "save"')
                    return('save')
            else:
                _logger.debug('Returning: "save"')
                return('save')
        return (None)

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
                _logger.debug('Returning: "{0}"'.format(self.trustlevel))
                return(str(self.trustlevel))
            else:
                _logger.debug('Returning: "save"')
                return('save')
        return(None)


class PacmanKey(object):
    def __init__(self, chroot_base):
        # We more or less recreate /usr/bin/pacman-key in python.
        self.chroot_base = chroot_base
        self.home = os.path.join(self.chroot_base, 'etc', 'pacman.d', 'gnupg')
        self.conf = os.path.join(self.home, 'gpg.conf')
        self.agent_conf = os.path.join(self.home, 'gpg-agent.conf')
        self.db = os.path.join(self.home, 'tofu.db')
        # ...pacman devs, why do you create the gnupg home with 0755?
        os.makedirs(self.home, 0o0755, exist_ok = True)
        # Probably not necessary, but...
        with open(os.path.join(self.home, '.gpg-v21-migrated'), 'wb') as fh:
            fh.write(b'')
        _logger.info('Touched/wrote: {0}'.format(os.path.join(self.home, '.gpg-v21-migrated')))
        if not os.path.isfile(self.conf):
            with open(self.conf, 'w') as fh:
                fh.write(('# Generated by AIF-NG.\n'
                          'no-greeting\n'
                          'no-permission-warning\n'
                          'lock-never\n'
                          'keyserver-options timeout=10\n'))
            _logger.info('Wrote: {0}'.format(self.conf))
        if not os.path.isfile(self.agent_conf):
            with open(self.agent_conf, 'w') as fh:
                fh.write(('# Generated by AIF-NG.\n'
                          'disable-scdaemon\n'))
            _logger.info('Wrote: {0}'.format(self.agent_conf))
        self.key = None
        # ...PROBABLY order-specific.
        self._initTofuDB()
        self.gpg = gpg.Context(home_dir = self.home)
        self._initKey()
        self._initPerms()
        self._initKeyring()

    def _initKey(self):
        # These match what is currently used by pacman-key --init.
        _keyinfo = {'userid': 'Pacman Keyring Master Key <pacman@localhost>',
                    'algorithm': 'rsa2048',
                    'expires_in': 0,
                    'expires': False,
                    'sign': True,
                    'encrypt': False,
                    'certify': False,
                    'authenticate': False,
                    'passphrase': None,
                    'force': False}
        _logger.debug('Creating key with options: {0}'.format(_keyinfo))
        genkey = self.gpg.create_key(**_keyinfo)
        _logger.info('Created key: {0}'.format(genkey.fpr))
        self.key = self.gpg.get_key(genkey.fpr, secret = True)
        self.gpg.signers = [self.key]
        _logger.debug('Set signer/self key to: {0}'.format(self.key))

    def _initKeyring(self):
        krdir = os.path.join(self.chroot_base, 'usr', 'share', 'pacman', 'keyrings')
        keyrings = [i for i in os.listdir(krdir) if i.endswith('.gpg')]
        _logger.info('Importing {0} keyring(s).'.format(len(keyrings)))
        for idx, kr in enumerate(keyrings):
            krname = re.sub(r'\.gpg$', '', kr)
            krfile = os.path.join(krdir, kr)
            trustfile = os.path.join(krdir, '{0}-trusted'.format(krname))
            revokefile = os.path.join(krdir, '{0}-revoked'.format(krname))
            _logger.debug('Importing keyring: {0} ({1}/{2})'.format(krname, (idx + 1), len(keyrings)))
            with open(os.path.join(krdir, kr), 'rb') as fh:
                imported_keys = self.gpg.key_import(fh.read())
            if imported_keys:
                _logger.debug('Imported: {0}'.format(imported_keys))
            # We also have to sign/trust the keys. I still can't believe there isn't an easier way to do this.
            if os.path.isfile(trustfile):
                with open(trustfile, 'r') as fh:
                    for trust in csv.reader(fh, delimiter = ':'):
                        k_id = trust[0]
                        k_trust = int(trust[1])
                        k = self.gpg.get_key(k_id)
                        self.gpg.key_sign(k, local = True)
                        editor = KeyEditor(trustlevel = k_trust)
                        self.gpg.interact(k, editor.truster)
            # And revoke keys.
            if os.path.isfile(revokefile):
                with open(revokefile, 'r') as fh:
                    for fpr in fh.read().splitlines():
                        k = self.gpg.get_key(fpr)
                        editor = KeyEditor()
                        self.gpg.interact(k, editor.revoker)
        return(None)

    def _initPerms(self):
        # Again, not quite sure why it's so permissive. But pacman-key explicitly does it, so.
        filenames = {'pubring': 0o0644,
                     'trustdb': 0o0644,
                     'secring': 0o0600}
        for fname, filemode in filenames.items():
            fpath = os.path.join(self.home, '{0}.gpg'.format(fname))
            if not os.path.isfile(fpath):
                # TODO: Can we just manually create an empty file, or will GPG not like that?
                # I'm fairly certain that the key creation automatically creates these files, so as long as this
                # function is run after _initKey() then we should be fine.
                # with open(fpath, 'wb') as fh:
                #     fh.write(b'')
                # _logger.info('Wrote: {0}'.format(fpath))
                continue
            os.chmod(fpath, filemode)
        return(None)

    def _initTofuDB(self):
        # As glad as I am that GnuPG is moving more towards more accessible data structures...
        db = sqlite3.connect(self.db)
        cur = db.cursor()
        cur.executescript(_createTofuDB)
        db.commit()
        cur.close()
        db.close()
        return(None)
