"""Private, no-follow control files for the destructive node proof only."""

import json
import os
from pathlib import Path
import stat
from uuid import uuid4


def private_path(path, mode, *, directory=False):
    """Reject aliasing, foreign ownership and any widening of the private mode."""
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('fault proof path is not absolute and canonical')
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != mode:
        raise ValueError('fault proof path ownership/mode differs')
    if not directory and info.st_nlink != 1:
        raise ValueError('fault proof file has another link')
    for parent in path.parents:
        metadata = parent.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_mode & 0o022:
            raise ValueError('fault proof ancestor is writable by another identity')


class PrivateControlDirectory:
    """Keep fixture control reads/writes anchored to the validated directory inode."""

    def __init__(self, root):
        private_path(root, 0o700, directory=True)
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self):
        os.close(self.fd)

    def read(self, name):
        if Path(name).name != name:
            raise ValueError('control file is not a basename')
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=self.fd)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > 65536):
                raise ValueError('control file ownership/mode/size differs')
            return json.load(source)

    def write(self, name, value):
        if Path(name).name != name:
            raise ValueError('control file is not a basename')
        temporary = uuid4().hex + '.tmp'
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=self.fd)
        try:
            with os.fdopen(descriptor, 'w') as target:
                json.dump(value, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass
