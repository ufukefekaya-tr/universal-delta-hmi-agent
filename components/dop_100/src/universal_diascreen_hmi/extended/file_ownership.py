# SPDX-License-Identifier: Apache-2.0
"""OS leases for template effects; live operations cannot be reconciled away."""
from contextlib import contextmanager
import os
from .common import no_links,require


@contextmanager
def worker_lease(workspace):
    path=no_links(workspace/'.runtime/template-worker.lock')
    with path.open('a+b') as stream:
        require(os.fstat(stream.fileno()).st_nlink==1,'STATE_LINK','Worker lease must not be hardlinked')
        if stream.tell()==0:stream.write(b'0');stream.flush()
        stream.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:require(False,'OPERATION_LIVE','An owned template worker is still running')
            try:yield
            finally:stream.seek(0);msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:require(False,'OPERATION_LIVE','An owned template worker is still running')
            try:yield
            finally:fcntl.flock(stream,fcntl.LOCK_UN)


@contextmanager
def immutable_read(path):
    """Keep the exact inspected file open against writes/replacement on Windows."""
    path=no_links(path)
    if os.name=='nt':
        import ctypes
        from ctypes import wintypes
        import msvcrt
        api=ctypes.WinDLL('kernel32',use_last_error=True)
        api.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,
                                 wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        api.CreateFileW.restype=wintypes.HANDLE
        handle=api.CreateFileW(str(path),0x80000000,1,None,3,0x80,None)
        if handle==wintypes.HANDLE(-1).value:raise ctypes.WinError(ctypes.get_last_error())
        try:fd=msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY)
        except BaseException:
            api.CloseHandle.argtypes=[wintypes.HANDLE];api.CloseHandle(handle);raise
        stream=os.fdopen(fd,'rb')
    else:stream=path.open('rb')
    with stream:
        before=os.fstat(stream.fileno())
        require(before.st_nlink==1 and before.st_size<=64*1024*1024,'OUTPUT_FILE','Bounded non-hardlinked output required')
        data=stream.read(64*1024*1024+1)
        require(len(data)==before.st_size,'OUTPUT_DRIFT','Output changed while reading')
        def unchanged():
            no_links(path)
            after=os.fstat(stream.fileno());current=path.stat()
            # Windows path-stat can retain a tunneled creation timestamp while
            # handle-stat has the current one. File ID, size and write time are
            # the path identity; compare change time only on the held handle.
            keys=('st_dev','st_ino','st_size','st_mtime_ns')
            require(all(getattr(before,k)==getattr(after,k)==getattr(current,k) for k in keys),
                    'OUTPUT_DRIFT','Output identity changed during verification')
            require(before.st_ctime_ns==after.st_ctime_ns,'OUTPUT_DRIFT','Held output changed during verification')
        unchanged()
        yield data,unchanged
        unchanged()
