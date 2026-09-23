"""Import user-browser recordings without creating a second application session."""
import subprocess
from pathlib import Path
import imageio_ffmpeg

MAX_BYTES = 150 * 1024 * 1024
MAX_SECONDS = 900


def convert(source: Path, output: Path, media_type: str, epoch: int):
    container = {'video/webm':'matroska','video/mp4':'mov'}[media_type]
    try:
        result = subprocess.run([
        imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error',
        '-protocol_whitelist', 'file,pipe', '-f', container, '-i', str(source),
        '-map', '0:v:0', '-an', '-t', str(MAX_SECONDS+1),
        '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2',
        '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast',
        '-pix_fmt', 'yuv420p', '-movflags', '+faststart', str(output),
        ], capture_output=True, timeout=300)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("录像转码超时，请缩短录像后重试。") from exc
    if result.returncode or not output.exists():
        raise ValueError('无法解码录像，请上传浏览器录制的 WebM 或 MP4 文件。')
    frames,duration = imageio_ffmpeg.count_frames_and_secs(str(output))
    if duration < .5 or duration > MAX_SECONDS:
        raise ValueError('录像长度应为 0.5 秒到 15 分钟。')
    return dict(epoch=epoch,frames=frames,fps=30,duration=duration,
                source='human_browser',entry_verified=False,
                status='pending_review',official=False)
