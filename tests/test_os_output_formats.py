"""Formatting tolerance must not collapse different ICL representations."""
import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('os_formats',ROOT/'scripts/os_content_formats.py')
formats=importlib.util.module_from_spec(spec);spec.loader.exec_module(formats)

@pytest.mark.parametrize('mode,expected,actual',[
 ('json','{"name":"A","passed":true}','{\n\t"passed": true,\n\t"name": "A"\n}'),
 ('diff-lines','x: before -> after','  x : before  ->  after\r\n'),
 ('diff-csv','key,before,after\nx,before,after\n','"key","before","after"\r\n"x","before","after"\r\n'),
 ('summary-lines','build_artifact: "b"\npassed: true\nassertions: [{"name":"x","passed":true}]',' build_artifact : "b" \r\npassed : true\r\nassertions: [ { "passed": true, "name": "x" } ]\r\n'),
 ('units','3.500 KiB','  3.500\tKiB\r\n'),
 ('trim-lines','[r5] Review packet\nTitle two','  [r5] Review packet\r\nTitle two\r\n'),
])
def test_cosmetic_edits_pass(mode,expected,actual):
 assert formats.normal(actual,mode)==formats.normal(expected,mode)

@pytest.mark.parametrize('mode,expected,actual',[
 ('json','{"accepted":true}','{"accepted":1}'),
 ('json','{"accepted":true}','{"accepted":"true"}'),
 ('json','[1,2]','[2,1]'),
 ('json','{"decision":"Approved"}','{"status":"ok"}'),
 ('units','3.500 KiB','3.5 KiB'),
 ('units','3.500 KiB','3.500 MiB'),
 ('diff-lines','x: before -> after','x: after -> before'),
 ('trim-lines','[r5] Review packet','Review packet [r5]'),
])
def test_method_content_and_type_errors_fail(mode,expected,actual):
 assert formats.normal(actual,mode)!=formats.normal(expected,mode)

def test_summary_csv_parses_nested_json_but_keeps_boolean_type():
 import csv,io,json
 def document(assertions,passed='true'):
  stream=io.StringIO();w=csv.writer(stream);w.writerow(['build_artifact','passed','assertions']);w.writerow(['b',passed,assertions]);return stream.getvalue()
 one=document('[{"name":"x","passed":true}]')
 assert formats.normal(one,'summary-csv')==formats.normal(document('[ { "passed": true, "name": "x" } ]'),'summary-csv')
 assert formats.normal(one,'summary-csv')!=formats.normal(document('[{"name":"x","passed":true}]','"true"'),'summary-csv')
 with pytest.raises(ValueError):formats.normal('build_artifact,passed,assertions\nb,true,[{"name":"x","passed":true}]','summary-csv')

def test_duplicate_json_fields_rejected():
 with pytest.raises(ValueError):formats.normal('{"accepted":false,"accepted":true}','json')

def test_recorder_formats_and_complete_examples_are_available():
 import json
 release=json.loads((ROOT/'tasks/os/catalog.json').read_text())
 ids={'OS-M-10','OS-M-11','OS-M-12','OS-H-01','OS-H-02','OS-H-06','OS-H-08','OS-H-11','OS-H-12'}
 for case in release['cases']:
  if case['id'] not in ids:continue
  for variant in 'ABC':
   for group in case['demo_examples'][variant]:
    guide=group['guide'];assert guide['output_format']
    assert guide['output_format'] in case['rules'][variant]
    assert any(s['expected'] for s in guide['steps'])


def test_review_returns_the_same_explicit_guides_and_public_output_constraints(monkeypatch):
 import json
 from vic import os_release
 release=json.loads((ROOT/'tasks/os/catalog.json').read_text())
 monkeypatch.setattr(os_release,'catalog',lambda source:release)
 monkeypatch.setattr(os_release,'demonstrations',lambda source,data:([],''))
 review=os_release.review_catalog(ROOT)
 row=next(r for r in review if r['id']=='OS-H-11')
 assert 'two text lines' in row['instruction']
 assert row['demo_examples']['B'][0]['guide']['output_format']
 assert row['demo_apps']==['Notepad']
