"""Inspect real media containers and authenticated byte-range playback."""
from pathlib import Path
import re
import subprocess

import imageio_ffmpeg
import pytest
from vic.config import ROOT
from vic.business import generate
from vic_apps.media_resources import edition
from test_application_api import clients
from test_direct_applications import human, credential
from test_api import admin


def duration(path):
    text=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-i',str(path)],capture_output=True,text=True).stderr
    h,m,s=map(float,re.search(r'Duration: (\d+):(\d+):([\d.]+)',text).groups())
    return h*3600+m*60+s


@pytest.mark.parametrize('kind,seconds,index', [('audio',239,0),('audio',240,1),('audio',241,2),
                                              ('video',599,3),('video',600,4),('video',601,5)])
def test_actual_media_duration_matches_threshold_metadata(tmp_path,kind,seconds,index):
    file=edition(ROOT,tmp_path,kind,index,seconds)
    assert duration(file)==seconds
    modified=file.stat().st_mtime_ns
    assert edition(ROOT,tmp_path,kind,index,seconds)==file
    assert file.stat().st_mtime_ns==modified
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-i',str(file),'-t','0.2','-f','null','-'],
                   check=True,capture_output=True)


def test_every_music_and_video_fixture_has_a_source_asset():
    for task in (17,18,21,22,25,26,27,28,31,32,34,35):
        for seed in (0,1,1000,1001):
            state=generate(task,seed)
            for item in state['items']:
                assert type(item['duration']) is int and 1<=item['duration']<=1800
                index=item['asset_index']
                source=ROOT/(f'apps/media/assets/clip-{index}.mp4' if state['app']=='media' else
                             f'apps/music/blog/static/benchmark/track-{index}.m4a')
                assert source.is_file()


def test_video_route_serves_ranges_and_rejects_stale_credentials(clients):
    c,w=clients;run=human(c,25);path='/api/runs/'+run['id']
    envelope=w.get(path,headers=credential(run))
    cookie=envelope.headers['set-cookie']
    assert 'HttpOnly' in cookie and f'Path={path}/media/' in cookie
    item=next(x for x in envelope.json()['state']['items'] if x['duration']==600)
    url=path+'/media/'+item['id']
    response=w.get(url,headers={'Range':'bytes=0-1023'})
    assert response.status_code==206 and len(response.content)==1024
    assert response.headers['content-type']=='video/mp4'
    assert response.headers['content-range'].startswith('bytes 0-1023/')
    assert w.get(path+'/media/unknown').status_code==404
    c.post('/v1/runs/'+run['id']+'/reset',headers=admin()).raise_for_status()
    assert w.get(url).status_code==403


def test_music_has_playable_audio_with_same_duration_as_library(clients,tmp_path):
    c,w=clients;run=human(c,22)
    state=w.get('/api/runs/'+run['id'],headers=credential(run)).json()['state']
    item=next(x for x in state['items'] if x['duration']==240)
    path='/native/music/'+run['id']+'/'
    assert w.get(path+'audio/'+item['id']).status_code==403
    w.post(path+'authorize',headers=credential(run)).raise_for_status()
    page=w.get(path+'songs/'+item['id']+'/')
    assert '<audio controls' in page.text and path+'audio/'+item['id'] in page.text
    assert '240 秒' in page.text
    audio=w.get(path+'audio/'+item['id'])
    assert audio.status_code==200 and audio.headers['content-type']=='audio/mp4'
    file=tmp_path/'audio.m4a';file.write_bytes(audio.content)
    assert duration(file)==240
    assert w.get(path+'audio/'+item['id'],headers={'Range':'bytes=0-255'}).status_code==206


def test_failed_media_generation_can_be_retried_without_losing_run(clients,monkeypatch):
    from vic_apps import media_resources
    c,w=clients;run=human(c,25);path='/api/runs/'+run['id']
    snapshot=w.get(path,headers=credential(run)).json()
    item=snapshot['state']['items'][0]
    original=media_resources.edition
    def fail(*args,**kwargs):
        raise subprocess.TimeoutExpired('ffmpeg',120)
    monkeypatch.setattr(media_resources,'edition',fail)
    response=w.get(path+'/media/'+item['id'])
    assert response.status_code==503 and response.headers['retry-after']=='5'
    assert w.get(path,headers=credential(run)).json()==snapshot
    monkeypatch.setattr(media_resources,'edition',original)
    assert w.get(path+'/media/'+item['id'],headers={'Range':'bytes=0-63'}).status_code==206
