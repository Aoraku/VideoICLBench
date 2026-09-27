"""Materialize playable editions whose actual timeline matches the library duration."""
from functools import lru_cache
import hashlib
from pathlib import Path
import subprocess
import tempfile
import threading

import imageio_ffmpeg

_locks = {}
_guard = threading.Lock()
_slots = threading.Semaphore(2)


@lru_cache(maxsize=24)
def _digest(path, modified, size):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def edition(root, cache, kind, asset_index, duration):
    if kind not in ('audio','video') or type(asset_index) is not int or asset_index not in range(6):
        raise ValueError('Unknown media resource')
    if type(duration) is not int or not 1<=duration<=1800:
        raise ValueError('Unsupported media duration')
    source = (root/'apps/media/assets'/f'clip-{asset_index}.mp4' if kind=='video' else
              root/'apps/music/blog/static/benchmark'/f'track-{asset_index}.m4a')
    info=source.stat()
    key=hashlib.sha256(f'v1:{kind}:{duration}:{_digest(str(source),info.st_mtime_ns,info.st_size)}'.encode()).hexdigest()
    suffix='.mp4' if kind=='video' else '.m4a'
    cache.mkdir(parents=True,exist_ok=True)
    dest=cache/(key+suffix)
    with _guard:
        mutex=_locks.setdefault(str(dest),threading.Lock())
    with mutex:
        if dest.is_file():return dest
        with _slots, tempfile.TemporaryDirectory(dir=cache) as work:
            pending=Path(work)/('edition'+suffix)
            options=(['-c:v','libx264','-preset','ultrafast','-crf','28','-c:a','aac','-b:a','32k'] if kind=='video' else
                     ['-vn','-af',f'afade=t=out:st={max(0,duration-1.5)}:d={min(1.5,duration)}','-c:a','aac','-b:a','96k'])
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-stream_loop','-1',
                            '-i',str(source),'-t',str(duration),*options,'-movflags','+faststart',str(pending)],
                           check=True,capture_output=True,timeout=120)
            pending.replace(dest)
    return dest
