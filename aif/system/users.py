# There isn't a python package that can manage *NIX users (well), unfortunately.
# So we do something stupid:
# https://www.tldp.org/LDP/sag/html/adduser.html
# https://unix.stackexchange.com/a/153227/284004
# https://wiki.archlinux.org/index.php/users_and_groups#File_list

import os
##
import passlib  # validate password hash/gen hash


class Password(object):
    def __init__(self):
        pass


class RootUser(object):
    def __init__(self):
        pass


class User(object):
    def __init__(self):
        pass

