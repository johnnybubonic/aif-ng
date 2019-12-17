import os
import pathlib


class File(object):
    def __init__(self, file_path):
        self.orig_path = file_path
        self.fullpath = os.path.abspath(os.path.expanduser(self.orig_path))
        self.path_rel = pathlib.PurePosixPath(self.orig_path)
        self.path_full = pathlib.PurePosixPath(self.fullpath)

    def __str__(self):
        return(self.fullpath)


class Directory(object):
    def __init__(self, dir_path):
        self.orig_path = dir_path
        self.fullpath = os.path.abspath(os.path.expanduser(self.orig_path))
        self.path_rel = pathlib.PurePosixPath(self.orig_path)
        self.path_full = pathlib.PurePosixPath(self.fullpath)
        self.files = []
        self.dirs = []

    def __str__(self):
        return(self.fullpath)

    def populateFilesDirs(self, recursive = False, native = False):
        if not recursive:
            for i in os.listdir(self.fullpath):
                if os.path.isdir(os.path.join(self.fullpath, i)):
                    self.dirs.append(i)
                elif os.path.isfile(os.path.join(self.fullpath, i)):
                    if not native:
                        self.files.append(i)
                    else:
                        self.files.append(File(i))
        else:
            for root, dirs, files in os.walk(self.fullpath):
                for f in files:
                    fpath = os.path.join(root, f)
                    relfpath = str(pathlib.PurePosixPath(fpath).relative_to(self.path_full))
                    if not native:
                        self.files.append(relfpath)
                    else:
                        self.files.append(relfpath)
                for d in dirs:
                    dpath = os.path.join(root, d)
                    reldpath = str(pathlib.PurePosixPath(dpath).relative_to(self.path_full))
                    self.dirs.append(reldpath)
                if root not in self.dirs:
                    self.dirs.append(root)
        if not native:
            self.dirs.sort()
            self.files.sort()
        return(None)
