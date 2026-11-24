"""Private, no-follow control files for the destructive node proof only."""

import fcntl
import json
import os
from pathlib import Path
import stat
from uuid import uuid4


def private_path(path, mode, *, directory=False, uid=None, gid=None, trusted_uids=()):
    """Reject aliasing, foreign ownership and any widening of the private mode."""
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path:
        raise ValueError('fault proof path is not absolute and canonical')
    uid = os.getuid() if uid is None else uid
    gid = os.getgid() if gid is None else gid
    info = path.lstat()
    expected = stat.S_ISDIR if directory else stat.S_ISREG
    if (not expected(info.st_mode) or info.st_uid != uid or info.st_gid != gid
            or stat.S_IMODE(info.st_mode) != mode):
        raise ValueError('fault proof path ownership/mode differs')
    if not directory and info.st_nlink != 1:
        raise ValueError('fault proof file has another link')
    anchor = path if directory else path.parent
    metadata = anchor.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != uid
            or metadata.st_gid != gid or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise ValueError('fault proof private anchor ownership/mode differs')
    for parent in path.parents:
        metadata = parent.lstat()
        sticky_root = (parent in anchor.parents and metadata.st_uid == 0
                       and metadata.st_mode & stat.S_ISVTX)
        if (not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid not in {0, uid, os.getuid(), *trusted_uids}
                or (metadata.st_mode & 0o022 and not sticky_root)):
            raise ValueError('fault proof ancestor is writable by another identity')


class PrivateControlDirectory:
    """Keep fixture control reads/writes anchored to the validated directory inode."""

    def __init__(self, root, *, uid=None, gid=None, trusted_uids=()):
        self.uid = os.getuid() if uid is None else uid
        self.gid = os.getgid() if gid is None else gid
        private_path(root, 0o700, directory=True, uid=self.uid, gid=self.gid,
                     trusted_uids=trusted_uids)
        before = Path(root).lstat()
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if not os.path.samestat(before, os.fstat(self.fd)):
            os.close(self.fd)
            raise ValueError('control directory identity changed')

    def close(self):
        os.close(self.fd)

    def read(self, name):
        if Path(name).name != name:
            raise ValueError('control file is not a basename')
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=self.fd)
        with os.fdopen(descriptor, 'rb') as source:
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.uid or info.st_gid != self.gid
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > 65536):
                raise ValueError('control file ownership/mode/size differs')
            return json.loads(source.read(65537))

    def trace_bytes(self):
        """Read only a complete bounded trace under the writer's advisory lock."""
        descriptor = os.open('runtime-trace.jsonl', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                             dir_fd=self.fd)
        with os.fdopen(descriptor, 'rb') as source:
            fcntl.flock(source, fcntl.LOCK_SH | fcntl.LOCK_NB)
            info = os.fstat(source.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != self.uid or info.st_gid != self.gid
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1 or info.st_size > 1024 * 1024):
                raise ValueError('trace ownership/mode/size differs')
            data = source.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024 or data and not data.endswith(b'\n'):
                raise ValueError('trace is oversized or incomplete')
            return data

    def write(self, name, value):
        if Path(name).name != name:
            raise ValueError('control file is not a basename')
        try:
            existing = os.stat(name, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            existing = None
        if existing is not None and (not stat.S_ISREG(existing.st_mode)
                or existing.st_uid != self.uid or existing.st_gid != self.gid
                or stat.S_IMODE(existing.st_mode) != 0o600 or existing.st_nlink != 1):
            raise ValueError('existing control file ownership/mode differs')
        temporary = uuid4().hex + '.tmp'
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=self.fd)
        try:
            with os.fdopen(descriptor, 'w') as target:
                os.fchown(target.fileno(), self.uid, self.gid)
                json.dump(value, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, name, src_dir_fd=self.fd, dst_dir_fd=self.fd)
        finally:
            try:
                os.unlink(temporary, dir_fd=self.fd)
            except FileNotFoundError:
                pass
