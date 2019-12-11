import os
import pathlib


class File(object):
    def __init__(self, file_path):
        self.orig_path = file_path
        self.fullpath = os.path.abspath(os.path.expanduser(self.orig_path))
        self.path_rel = pathlib.PurePosixPath(self.orig_path)
        self.path_full = pathlib.PurePosixPath(self.fullpath)


class Directory(object):
    def __init__(self, dir_path):
        self.orig_path = dir_path
        self.fullpath = os.path.abspath(os.path.expanduser(self.orig_path))
        self.path_rel = pathlib.PurePosixPath(self.orig_path)
        self.path_full = pathlib.PurePosixPath(self.fullpath)
        self.files = []
        self.dirs = []

    def populateFilesDirs(self, recursive = False):
        if not recursive:
            for i in os.listdir(self.fullpath):
                if os.path.isdir(os.path.join(self.fullpath, i)):
                    self.dirs.append(i)
                elif os.path.isfile(os.path.join(self.fullpath, i)):
                    self.files.append(i)
        else:
            for root, dirs, files in os.walk(self.fullpath):
                for f in files:
                    fpath = os.path.join(root, f)
                    relfpath = pathlib.PurePosixPath(fpath).relative_to(self.path_full)
                    self.files.append(relfpath)
                for d in dirs:
                    dpath = os.path.join(root, d)
                    reldpath = pathlib.PurePosixPath(dpath).relative_to(self.path_full)
                    self.dirs.append(reldpath)
                if root not in self.dirs:
                    self.dirs.append(dirs)
        self.dirs.sort()
        self.files.sort()
        return(None)
