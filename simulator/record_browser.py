"""Record an actual headed Chromium window on Linux, including browser chrome.

This is an observer for Hosted HTTP operator runs. It does not generate model
responses or simulate GUI clicks, and cannot record a different/local browser.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
from urllib.request import urlopen


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default='http://127.0.0.1:18632/')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--duration',type=float,default=0,help='Seconds; 0 records until Ctrl-C/SIGTERM')
    p.add_argument('--width',type=int,default=1600)
    p.add_argument('--height',type=int,default=1200)
    p.add_argument('--fps',type=int,default=15)
    p.add_argument('--display',type=int,default=97)
    a=p.parse_args()
    for executable in ('Xvfb','chromium','ffmpeg'):
        if not shutil.which(executable):p.error('Missing executable: '+executable)
    if a.output.exists():p.error('Output already exists; choose a new filename')
    if a.width<800 or a.height<600 or a.width%2 or a.height%2 or not 1<=a.fps<=30 or a.duration<0:
        p.error('Use even dimensions >=800x600, fps 1..30, duration >=0')
    display=f':{a.display}'
    if Path(f'/tmp/.X{a.display}-lock').exists() or Path(f'/tmp/.X11-unix/X{a.display}').exists():
        p.error('Display is already in use; select another --display')
    with urlopen(a.url,timeout=10) as r:
        if r.status!=200:p.error('Dashboard unavailable')
    a.output=a.output.resolve();a.output.parent.mkdir(parents=True,exist_ok=True)
    children=[];encoder=None
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
    started=time.time()
    metadata={'kind':'full_browser_window','url':a.url,'width':a.width,'height':a.height,'fps':a.fps,
              'started_at_unix':started,'note':'Actual headed server Chromium, with browser chrome. Hosted HTTP observer, not a recording of local GUI-agent clicks.'}
    log=a.output.with_suffix('.log').open('w')
    try:
        with tempfile.TemporaryDirectory(prefix='vicl-browser-') as profile:
            profile_dir=Path(profile)/'Default';profile_dir.mkdir()
            (profile_dir/'Preferences').write_text(json.dumps({'translate':{'enabled':False}}))
            x=subprocess.Popen(['Xvfb',display,'-screen','0',f'{a.width}x{a.height}x24','-nolisten','tcp'],stdout=log,stderr=log)
            children.append(x)
            for _ in range(100):
                if x.poll() is not None:raise RuntimeError('Xvfb failed; see capture log')
                if Path(f'/tmp/.X11-unix/X{a.display}').exists():break
                time.sleep(.1)
            else:raise RuntimeError('Xvfb not ready')
            env={k:v for k,v in os.environ.items() if not k.startswith('VLM_')}
            env['DISPLAY']=display
            chromium=subprocess.Popen(['chromium','--no-first-run','--no-default-browser-check',
                '--disable-dev-shm-usage','--disable-gpu','--disable-features=Translate','--lang=zh-CN',f'--user-data-dir={profile}',
                '--window-position=0,0',f'--window-size={a.width},{a.height}',a.url],env=env,stdout=log,stderr=log)
            children.append(chromium)
            # Record startup as well; do not silently omit early actions.
            encoder=subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','warning','-f','x11grab',
                '-draw_mouse','1','-framerate',str(a.fps),'-video_size',f'{a.width}x{a.height}',
                '-i',display+'.0','-c:v','libx264','-preset','veryfast','-crf','23','-pix_fmt','yuv420p',
                '-movflags','+faststart',str(a.output)],stdin=subprocess.PIPE,stdout=log,stderr=log)
            print('RECORDING',a.output,flush=True)
            try:
                while not a.duration or time.time()-started<a.duration:
                    if encoder.poll() is not None:raise RuntimeError('Recorder exited; see capture log')
                    if any(c.poll() is not None for c in children):raise RuntimeError('Browser/display exited; see capture log')
                    time.sleep(.25)
            except KeyboardInterrupt:pass
            finally:
                if encoder.poll() is None:
                    encoder.communicate(b'q\n',timeout=30)
                metadata['encoder_exit_code']=encoder.returncode
                # Close browser before removing its temporary profile.
                for c in reversed(children):
                    if c.poll() is None:c.terminate()
                for c in reversed(children):
                    try:c.wait(timeout=10)
                    except subprocess.TimeoutExpired:c.kill();c.wait()
    finally:
        if encoder and encoder.poll() is None:encoder.kill();encoder.wait()
        for c in reversed(children):
            if c.poll() is None:c.terminate();c.wait(timeout=10)
        metadata['ended_at_unix']=time.time()
        a.output.with_suffix('.json').write_text(json.dumps(metadata,indent=2))
        log.close()
    if metadata.get('encoder_exit_code')!=0:raise RuntimeError('Recording failed; inspect log')
    print('SAVED',a.output,flush=True)

if __name__=='__main__':main()
