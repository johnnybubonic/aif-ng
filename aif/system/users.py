# There isn't a python package that can manage *NIX users (well), unfortunately.
# So we do something stupid:
# https://www.tldp.org/LDP/sag/html/adduser.html
# https://unix.stackexchange.com/a/153227/284004
# https://wiki.archlinux.org/index.php/users_and_groups#File_list

import datetime
import os
import re
import warnings
##
import passlib.context
import passlib.hash
##
import aif.utils


_skipline_re = re.compile(r'^\s*(#|$)')
_now = datetime.datetime.utcnow()
_epoch = datetime.datetime.fromtimestamp(0)
_since_epoch = _now - _epoch


class Group(object):
    def __init__(self, group_xml):
        self.xml = group_xml
        self.name = None
        self.gid = None
        self.password = None
        self.create = False
        self.members = set()
        if self.xml:
            self.name = self.xml.attrib['name']
            self.gid = self.xml.attrib.get('gid')
            self.password = self.xml.attrib.get('password', 'x')
            self.create = aif.utils.xmlBool(self.xml.attrib.get('create', 'false'))
            if self.gid:
                self.gid = int(self.gid)
        else:
            if not self.password:
                self.password = 'x'


class Password(object):
    def __init__(self, password_xml):
        self.xml = password_xml
        self.disabled = False
        self.password = None
        self.hash = None
        self.hash_type = None
        self.hash_rounds = None
        self._pass_context = passlib.context.CryptContext(schemes = ['sha512_crypt', 'sha256_crypt', 'md5_crypt'])
        if self.xml:
            self.disabled = aif.utils.xmlBool(self.xml.attrib.get('locked', 'false'))
            self._password_xml = self.xml.xpath('passwordPlain|passwordHash')
            if self._password_xml:
                self._password_xml = self._password_xml[0]
                if self._password_xml.tag == 'passwordPlain':
                    self.password = self._password_xml.text
                    self.hash_type = self._password_xml.attrib.get('hashType', 'sha512')
                    # 5000 rounds is the crypt(3) default.
                    self.hash_rounds = int(self._password_xml.get('rounds', 5000))
                    self._pass_context.update(default = '{0}_crypt'.format(self.hash_type))
                    self.hash = passlib.hash.sha512_crypt.using(rounds = self.hash_rounds).hash(self.password)
                else:
                    self.hash = self._password_xml.text
                    self.hash_type = self._password_xml.attrib.get('hashType', '(detect)')
                    if self.hash_type == '(detect)':
                        self.detectHashType()
        else:
            self.disabled = True
            self.hash = ''

    def detectHashType(self):
        if self.hash.startswith(('!', 'x')):
            self.disabled = True
            self.hash = re.sub(r'^[!x]+', '', self.hash)
        self.hash_type = re.sub(r'_crypt$', '', self._pass_context.identify(self.hash))
        if not self.hash_type:
            warnings.warn('Could not determine hash type')
        return()


class User(object):
    def __init__(self, user_xml):
        self.xml = user_xml
        self.name = None
        self.uid = None
        self.gid = None
        self.primary_group = None
        self.password = None
        self.sudo = None
        self.comment = None
        self.shell = None
        self.minimum_age = None
        self.maximum_age = None
        self.warning_period = None
        self.inactive_period = None
        self.expire_date = None
        self.groups = []
        self.passwd_entry = []
        self.shadow_entry = []
        self._initVals()

    def _initVals(self):
        if isinstance(self, RootUser) or not self.xml:
            # We manually assign these.
            return()
        self.name = self.xml.attrib['name']
        self.password = Password(self.xml.find('password'))
        self.sudo = aif.utils.xmlBool(self.xml.attrib.get('sudo', 'false'))
        self.home = self.xml.attrib.get('home', '/home/{0}'.format(self.name))
        self.uid = self.xml.attrib.get('uid')
        if self.uid:
            self.uid = int(self.uid)
        self.primary_group = Group(None)
        self.primary_group.name = self.xml.attrib.get('group', self.name)
        self.primary_group.gid = self.xml.attrib.get('gid')
        if self.primary_group.gid:
            self.primary_group.gid = int(self.primary_group.gid)
        self.primary_group.create = True
        self.primary_group.members.add(self.name)
        self.shell = self.xml.attrib.get('shell', '/bin/bash')
        self.comment = self.xml.attrib.get('comment')
        self.minimum_age = int(self.xml.attrib.get('minAge', 0))
        self.maximum_age = int(self.xml.attrib.get('maxAge', 0))
        self.warning_period = int(self.xml.attrib.get('warnDays', 0))
        self.inactive_period = int(self.xml.attrib.get('inactiveDays', 0))
        self.expire_date = self.xml.attrib.get('expireDate')
        self.last_change = _since_epoch.days - 1
        if self.expire_date:
            # https://www.w3.org/TR/xmlschema-2/#dateTime
            try:
                self.expire_date = datetime.datetime.fromtimestamp(int(self.expire_date))  # It's an Epoch
            except ValueError:
                self.expire_date = re.sub(r'^[+-]', '', self.expire_date)  # Strip the useless prefix
                # Combine the offset into a strftime/strptime-friendly offset
                self.expire_date = re.sub(r'([+-])([0-9]{2}):([0-9]{2})$', r'\g<1>\g<2>\g<3>', self.expire_date)
                _common = '%Y-%m-%dT%H:%M:%S'
                for t in ('{0}%z'.format(_common), '{0}Z'.format(_common), '{0}.%f%z'.format(_common)):
                    try:
                        self.expire_date = datetime.datetime.strptime(self.expire_date, t)
                        break
                    except ValueError:
                        continue
        for group_xml in self.xml.findall('xGroup'):
            g = Group(group_xml)
            g.members.add(self.name)
            self.groups.append(g)
        return()

    def genShadow(self):
        if not all((self.uid, self.gid)):
            raise RuntimeError(('User objects must have a UID and GID set before their '
                                'passwd/shadow entries can be generated'))
        if isinstance(self, RootUser):
            # This is handled manually.
            return()
        # passwd(5)
        self.passwd_entry = [self.name,  # Username
                             'x',  # self.password.hash is not used because shadow, but this would be password
                             str(self.uid),  # UID
                             str(self.gid),  # GID
                             (self.comment if self.comment else ''),  # GECOS
                             self.home,  # Home directory
                             self.shell]  # Shell
        # shadow(5)
        self.shadow_entry = [self.name,  # Username
                             self.password.hash,  # Password hash (duh)
                             (str(self.last_change) if self.last_change else ''),  # Days since epoch last passwd change
                             (str(self.minimum_age) if self.minimum_age else '0'),  # Minimum password age
                             (str(self.maximum_age) if self.maximum_age else ''),  # Maximum password age
                             (str(self.warning_period) if self.warning_period else ''),  # Passwd expiry warning period
                             (str(self.inactive_period) if self.inactive_period else ''),  # Password inactivity period
                             (str(self.expire_date.timestamp()) if self.expire_date else ''),  # Expiration date
                             '']  # "Reserved"
        return()


class RootUser(User):
    def __init__(self, rootpassword_xml):
        super().__init__(None)
        self.xml = rootpassword_xml
        self.name = 'root'
        self.password = Password(self.xml)
        self.uid = 0
        self.gid = 0
        self.primary_group = Group(None)
        self.primary_group.gid = 0
        self.primary_group.name = 'root'
        self.home = '/root'
        self.shell = '/bin/bash'
        self.passwd_entry = [self.name, 'x', str(self.uid), str(self.gid), '', self.home, self.shell]
        self.shadow_entry = [self.name, self.password.hash, str(_since_epoch.days - 1), '', '', '', '', '', '']


class UserDB(object):
    def __init__(self, chroot_base, rootpassword_xml, users_xml):
        self.root = RootUser(rootpassword_xml)
        self.users = []
        self.defined_groups = []
        self.sys_users = []
        self.sys_groups = []
        for user_xml in users_xml.findall('user'):
            u = User(user_xml)
            self.users.append(u)
            self.defined_groups.append(u.primary_group)
            self.defined_groups.extend(u.groups)
        self.passwd_file = os.path.join(chroot_base, 'etc', 'passwd')
        self.shadow_file = os.path.join(chroot_base, 'etc', 'shadow')
        self.group_file = os.path.join(chroot_base, 'etc', 'group')
        self.logindefs_file = os.path.join(chroot_base, 'etc', 'login.defs')
        self.login_defaults = {}
        self._parseLoginDefs()
        self._parseShadow()

    def _parseLoginDefs(self):
        with open(self.logindefs_file, 'r') as fh:
            logindefs = fh.read().splitlines()
        for line in logindefs:
            if _skipline_re.search(line):
                continue
            l = [i.strip() for i in line.split(None, 1)]
            if len(l) < 2:
                l.append(None)
            self.login_defaults[l[0]] = l[1]
        # Convert to native objects
        for k in ('FAIL_DELAY', 'PASS_MAX_DAYS', 'PASS_MIN_DAYS', 'PASS_WARN_AGE', 'UID_MIN', 'UID_MAX',
                  'SYS_UID_MIN', 'SYS_UID_MAX', 'GID_MIN', 'GID_MAX', 'SYS_GID_MIN', 'SYS_GID_MAX', 'LOGIN_RETRIES',
                  'LOGIN_TIMEOUT', 'LASTLOG_UID_MAX', 'MAX_MEMBERS_PER_GROUP', 'SHA_CRYPT_MIN_ROUNDS',
                  'SHA_CRYPT_MAX_ROUNDS', 'SUB_GID_MIN', 'SUB_GID_MAX', 'SUB_GID_COUNT', 'SUB_UID_MIN', 'SUB_UID_MAX',
                  'SUB_UID_COUNT'):
            if k in self.login_defaults.keys():
                self.login_defaults[k] = int(self.login_defaults[k])
        for k in ('TTYPERM', ):
            if k in self.login_defaults.keys():
                self.login_defaults[k] = int(self.login_defaults[k], 8)
        for k in ('ERASECHAR', 'KILLCHAR', 'UMASK'):
            if k in self.login_defaults.keys():
                v = self.login_defaults[k]
                if v.startswith('0x'):
                    v = int(v, 16)
                elif v.startswith('0'):
                    v = int(v, 8)
                else:
                    v = int(v)
                self.login_defaults[k] = v
        for k in ('LOG_UNKFAIL_ENAB', 'LOG_OK_LOGINS', 'SYSLOG_SU_ENAB', 'SYSLOG_SG_ENAB', 'DEFAULT_HOME',
                  'CREATE_HOME', 'USERGROUPS_ENAB', 'MD5_CRYPT_ENAB'):
            if k in self.login_defaults.keys():
                v = self.login_defaults[k].lower()
                self.login_defaults[k] = (True if v == 'yes' else False)
        return()

    def _parseShadow(self):
        def parseShadowLine(line):
            shadowdict = dict(zip(['name', 'password', 'last_change', 'minimum_age', 'maximum_age', 'warning_period',
                                   'inactive_period', 'expire_date', 'RESERVED'],
                                  line))
            p = Password(None)
            p.hash = shadowdict['password']
            p.detectHashType()
            shadowdict['password'] = p
            del(shadowdict['RESERVED'])
            for i in ('last_change', 'minimum_age', 'maximum_age', 'warning_period', 'inactive_period'):
                if shadowdict[i].strip() == '':
                    shadowdict[i] = None
                else:
                    shadowdict[i] = int(shadowdict[i])
            if shadowdict['expire_date'].strip() == '':
                shadowdict['expire_date'] = None
            else:
                shadowdict['expire_date'] = datetime.datetime.fromtimestamp(shadowdict['expire_date'])
            return(shadowdict)

        def parseUserLine(line):
            userdict = dict(zip(['name', 'password', 'uid', 'gid', 'comment', 'home', 'shell'], line))
            del(userdict['password'])  # We don't use this because shadow
            for i in ('uid', 'gid'):
                userdict[k] = int(userdict[k])
            if userdict['comment'].strip() == '':
                userdict['comment'] = None
            return(userdict)

        def parseGroupLine(line):
            groupdict = dict(zip(['name', 'password', 'gid', 'members'], line))
            groupdict['members'] = set(','.split(groupdict['members']))
            return(groupdict)

        sys_shadow = {}
        users = {}
        groups = {}
        for f in ('shadow', 'passwd', 'group'):
            sys_shadow[f] = []
            with open(getattr(self, '{0}_file'.format(f)), 'r') as fh:
                for line in fh.read().splitlines():
                    if _skipline_re.search(line):
                        continue
                    sys_shadow[f].append(line.split(':'))
        # TODO: iterate through sys_shadow, convert passwd + shadow into a User obj, convert group into Group objs,
        #  and associate between the two. might require a couple iterations...
        for groupline in sys_shadow['group']:
            group = parseGroupLine(groupline)
            g = Group(None)
            for k, v in group.items():
                setattr(g, k, v)
            self.sys_groups.append(g)
            groups[g.name] = g
        for userline in sys_shadow['passwd']:
            user = parseUserLine(userline)
            users[user['name']] = user
        for shadowline in sys_shadow['shadow']:
            user = parseShadowLine(shadowline)
            udict = users[user['name']]
            udict.update(user)
            u = User(None)
            for k, v in udict.items():
                setattr(u, k, v)
            self.sys_users.append(u)
        return()
