#!/usr/bin/env python3
"""Render six original instrumental loops without external audio samples."""
from pathlib import Path
import subprocess
import tempfile
import wave

import imageio_ffmpeg
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def render(index):
    rate, seconds = 24000, 24
    signal = np.zeros(rate*seconds, dtype=np.float64)
    # Eight bars at 80 BPM. Each edition has its own key and arpeggio pattern.
    root = [48,50,53,55,57,60][index]
    chords = [(0,4,7),(5,9,12),(9,12,16),(7,11,14)]
    for bar in range(8):
        chord = chords[(bar+index)%4]
        for beat in range(8):
            start = int((bar*3+beat*.375)*rate)
            length = min(int(rate*1.5),len(signal)-start)
            t = np.arange(length)/rate
            pitch = root + chord[(beat*(1+index%2)+index)%3] + (12 if beat%4==3 else 0)
            hz = 440*2**((pitch-69)/12)
            env = (1-np.exp(-t*80))*np.exp(-t*(3.5+index*.15))
            tone = np.sin(2*np.pi*hz*t)+.27*np.sin(2*np.pi*hz*2*t)+.08*np.sin(2*np.pi*hz*3*t)
            signal[start:start+length] += tone*env*.19
        start = int(bar*3*rate);length=min(rate*3,len(signal)-start);t=np.arange(length)/rate
        hz=440*2**((root+chord[0]-12-69)/12)
        signal[start:start+length] += np.sin(2*np.pi*hz*t)*(1-np.exp(-t*25))*np.exp(-t*1.2)*.16
    fade = np.minimum(np.arange(len(signal))/ (rate*.05),1)*np.minimum(np.arange(len(signal))[::-1]/(rate*.4),1)
    signal = np.tanh(signal)*fade
    return rate, (signal*27000).astype('<i2')


if __name__ == '__main__':
    dest = ROOT/'apps/music/blog/static/benchmark'
    with tempfile.TemporaryDirectory() as work:
        for index in range(6):
            rate,signal=render(index)
            wav=Path(work)/'source.wav'
            with wave.open(str(wav),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(rate);f.writeframes(signal.tobytes())
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-i',str(wav),
                            '-c:a','aac','-b:a','96k','-movflags','+faststart',str(dest/f'track-{index}.m4a')],check=True)
            print(f'track-{index}.m4a',flush=True)
