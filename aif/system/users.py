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
import aif.constants_fallback


_skipline_re = re.compile(r'^\s*(#|$)')
_now = datetime.datetime.utcnow()
_epoch = datetime.datetime.fromtimestamp(0)
_since_epoch = _now - _epoch

# TODO: still need to generate UID/GIDs for new groups and users


class Group(object):
    def __init__(self, group_xml):
        self.xml = group_xml
        self.name = None
        self.gid = None
        self.password = None
        self.create = False
        self.admins = set()
        self.members = set()
        self.group_entry = []
        self.gshadow_entry = []
        if self.xml is not None:
            self.name = self.xml.attrib['name']
            self.gid = self.xml.attrib.get('gid')
            # TODO: add to XML?
            self.password = Password(self.xml.attrib.get('password'), gshadow = True)
            self.password.detectHashType()
            self.create = aif.utils.xmlBool(self.xml.attrib.get('create', 'false'))
            if self.gid:
                self.gid = int(self.gid)
        else:
            if not self.password:
                self.password = '!!'

    def genFileLine(self):
        if not self.gid:
            raise RuntimeError(('Group objects must have a gid set before their '
                                'group/gshadow entries can be generated'))
        # group(5)
        self.group_entry = [self.name,  # Group name
                            'x',  # Password, normally, but we use shadow for this
                            self.gid,  # GID
                            ','.join(self.members)]  # Comma-separated members
        # gshadow(5)
        self.gshadow_entry = [self.name,  # Group name
                              (self.password.hash if self.password.hash else '!!'),  # Password hash (if it has one)
                              ','.join(self.admins),  # Users with administrative control of group
                              ','.join(self.members)]  # Comma-separated members of group
        return()

    def parseGroupLine(self, line):
        groupdict = dict(zip(['name', 'password', 'gid', 'members'],
                             line.split(':')))
        members = [i for i in groupdict['members'].split(',') if i.strip() != '']
        if members:
            self.members = set(members)
        self.gid = int(groupdict['gid'])
        self.name = groupdict['name']
        return()

    def parseGshadowLine(self, line):
        groupdict = dict(zip(['name', 'password', 'admins', 'members'],
                             line.split(':')))
        self.password = Password(None, gshadow = True)
        self.password.hash = groupdict['password']
        self.password.detectHashType()
        admins = [i for i in groupdict['admins'].split(',') if i.strip() != '']
        members = [i for i in groupdict['members'].split(',') if i.strip() != '']
        if admins:
            self.admins = set(admins)
        if members:
            self.members = set(members)
        return()


class Password(object):
    def __init__(self, password_xml, gshadow = False):
        self.xml = password_xml
        self._is_gshadow = gshadow
        if not self._is_gshadow:
            self.disabled = False
        self.password = None
        self.hash = None
        self.hash_type = None
        self.hash_rounds = None
        self._pass_context = passlib.context.CryptContext(schemes = ['{0}_crypt'.format(i)
                                                                     for i in
                                                                     aif.constants_fallback.CRYPT_SUPPORTED_HASHTYPES])
        if self.xml is not None:
            if not self._is_gshadow:
                self.disabled = aif.utils.xmlBool(self.xml.attrib.get('locked', 'false'))
            self._password_xml = self.xml.xpath('passwordPlain|passwordHash')
            if self._password_xml is not None:
                self._password_xml = self._password_xml[0]
                if self._password_xml.tag == 'passwordPlain':
                    self.password = self._password_xml.text.strip()
                    self.hash_type = self._password_xml.attrib.get('hashType', 'sha512')
                    # 5000 rounds is the crypt(3) default.
                    self.hash_rounds = int(self._password_xml.get('rounds', 5000))
                    self._pass_context.update(default = '{0}_crypt'.format(self.hash_type))
                    self.hash = passlib.hash.sha512_crypt.using(rounds = self.hash_rounds).hash(self.password)
                else:
                    self.hash = self._password_xml.text.strip()
                    self.hash_type = self._password_xml.attrib.get('hashType', '(detect)')
                    if self.hash_type == '(detect)':
                        self.detectHashType()
        else:
            if not self._is_gshadow:
                self.disabled = True
            self.hash = ''

    def detectHashType(self):
        if not self.hash.startswith('$'):
            if not self._is_gshadow:
                self.disabled = True
            self.hash = re.sub(r'^[^$]+($)?', r'\g<1>', self.hash)
        if self.hash not in ('', None):
            self.hash_type = re.sub(r'_crypt$', '', self._pass_context.identify(self.hash))
            if not self.hash_type:
                warnings.warn('Could not determine hash type')
        return()


class User(object):
    def __init__(self, user_xml):
        self.xml = user_xml
        self.name = None
        self.uid = None
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
        if self.xml is None:
            # We manually assign these.
            return()
        self.name = self.xml.attrib['name']
        self.password = Password(self.xml.find('password'))
        self.sudo = aif.utils.xmlBool(self.xml.attrib.get('sudo', 'false'))
        self.home = self.xml.attrib.get('home', '/home/{0}'.format(self.name))
        self.uid = self.xml.attrib.get('uid')
        if self.uid is not None:
            self.uid = int(self.uid)
        self.primary_group = Group(None)
        self.primary_group.name = self.xml.attrib.get('group', self.name)
        self.primary_group.gid = self.xml.attrib.get('gid')
        if self.primary_group.gid is not None:
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
        if self.expire_date is not None:
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

    def genFileLine(self):
        if not all((self.uid, self.primary_group.gid)):
            raise RuntimeError(('User objects must have a uid and primary_group.gid set before their '
                                'passwd/shadow entries can be generated'))
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
                             (str((self.expire_date - _epoch).days) if self.expire_date else ''),  # Expiration date
                             '']  # "Reserved"
        return()

    def parseShadowLine(self, line):
        shadowdict = dict(zip(['name', 'password', 'last_change', 'minimum_age', 'maximum_age', 'warning_period',
                               'inactive_period', 'expire_date', 'RESERVED'],
                              line.split(':')))
        self.name = shadowdict['name']
        self.password = Password(None)
        self.password.hash = shadowdict['password']
        self.password.detectHashType()
        for i in ('last_change', 'minimum_age', 'maximum_age', 'warning_period', 'inactive_period'):
            if shadowdict[i].strip() == '':
                setattr(self, i, None)
            else:
                setattr(self, i, int(shadowdict[i]))
        if shadowdict['expire_date'].strip() == '':
            self.expire_date = None
        else:
            self.expire_date = datetime.datetime.fromtimestamp(shadowdict['expire_date'])
        return(shadowdict)

    def parsePasswdLine(self, line):
        userdict = dict(zip(['name', 'password', 'uid', 'gid', 'comment', 'home', 'shell'],
                            line.split(':')))
        self.name = userdict['name']
        self.primary_group = int(userdict['gid'])  # This gets transformed by UserDB() to the proper Group() obj
        self.uid = int(userdict['uid'])
        for k in ('home', 'shell'):
            if userdict[k].strip() != '':
                setattr(self, k, userdict[k])
        return()


class UserDB(object):
    def __init__(self, chroot_base, rootpass_xml, users_xml):
        self.rootpass = Password(rootpass_xml)
        self.xml = users_xml
        self.sys_users = []
        self.sys_groups = []
        self.new_users = []
        self.new_groups = []
        self._valid_uids = {'sys': set(),
                            'user': set()}
        self._valid_gids = {'sys': set(),
                            'user': set()}
        self.passwd_file = os.path.join(chroot_base, 'etc', 'passwd')
        self.shadow_file = os.path.join(chroot_base, 'etc', 'shadow')
        self.group_file = os.path.join(chroot_base, 'etc', 'group')
        self.gshadow_file = os.path.join(chroot_base, 'etc', 'gshadow')
        self.logindefs_file = os.path.join(chroot_base, 'etc', 'login.defs')
        self.login_defaults = {}
        self._parseLoginDefs()
        self._parseShadow()
        self._parseXML()

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
        sys_shadow = {}
        users = {}
        groups = {}
        for f in ('shadow', 'passwd', 'group', 'gshadow'):
            sys_shadow[f] = []
            with open(getattr(self, '{0}_file'.format(f)), 'r') as fh:
                for line in fh.read().splitlines():
                    if _skipline_re.search(line):
                        continue
                    sys_shadow[f].append(line)
        for groupline in sys_shadow['group']:
            g = Group(None)
            g.parseGroupLine(groupline)
            groups[g.gid] = g
        for gshadowline in sys_shadow['gshadow']:
            g = [i for i in groups.values() if i.name == gshadowline.split(':')[0]][0]
            g.parseGshadowLine(gshadowline)
            self.sys_groups.append(g)
            self.new_groups.append(g)
        for userline in sys_shadow['passwd']:
            u = User(None)
            u.parsePasswdLine(userline)
            users[u.name] = u
        for shadowline in sys_shadow['shadow']:
            u = users[shadowline.split(':')[0]]
            u.parseShadowLine(shadowline)
            self.sys_users.append(u)
            self.new_users.append(u)
        # Now that we've native-ized the above, we need to do some associations.
        for user in self.sys_users:
            for group in self.sys_groups:
                if not isinstance(user.primary_group, Group) and user.primary_group == group.gid:
                    user.primary_group = group
                if user.name in group.members and group != user.primary_group:
                    user.groups.append(group)
        if self.rootpass:
            rootuser = users['root']
            rootuser.password = self.rootpass
            rootuser.password.detectHashType()
        return()

    def _parseXML(self):
        for user_xml in self.xml.findall('user'):
            u = User(user_xml)
            # TODO: need to do unique checks for users and groups (especially for groups if create = True)
            # TODO: writer? sort by uid/gid? group membership parsing with create = False?
            # TODO: system accounts?
            if not u.uid:
                u.uid = self.getAvailUID()
            if not u.primary_group.gid:
                u.primary_group.gid = self.getAvailGID()
            self.new_users.append(u)
            self.new_groups.append(u.primary_group)
            for g in u.groups:
                if not g.gid:
                    g.gid = self.getAvailGID()
            self.new_groups.extend(u.groups)
        return()

    def getAvailUID(self, system = False):
        if not self.login_defaults:
            self._parseLoginDefs()
        if system:
            def_min = int(self.login_defaults.get('SYS_UID_MIN', 500))
            def_max = int(self.login_defaults.get('SYS_UID_MAX', 999))
            k = 'sys'
        else:
            def_min = int(self.login_defaults.get('UID_MIN', 1000))
            def_max = int(self.login_defaults.get('UID_MAX', 60000))
            k = 'user'
        if not self._valid_uids[k]:
            self._valid_uids[k] = set(i for i in range(def_min, (def_max + 1)))
        current_uids = set(i.uid for i in self.new_users)
        uid = min(self._valid_uids[k] - current_uids)
        return(uid)

    def getAvailGID(self, system = False):
        if not self.login_defaults:
            self._parseLoginDefs()
        if system:
            def_min = int(self.login_defaults.get('SYS_GID_MIN', 500))
            def_max = int(self.login_defaults.get('SYS_GID_MAX', 999))
            k = 'sys'
        else:
            def_min = int(self.login_defaults.get('GID_MIN', 1000))
            def_max = int(self.login_defaults.get('GID_MAX', 60000))
            k = 'user'
        if not self._valid_gids[k]:
            self._valid_gids[k] = set(i for i in range(def_min, (def_max + 1)))
        current_gids = set(i.gid for i in self.new_groups)
        gid = min(self._valid_gids[k] - current_gids)
        return(gid)
