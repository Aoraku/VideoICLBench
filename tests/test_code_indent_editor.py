"""The displayed OJ draft is editable and submits the bytes the user entered."""
import json
import pytest
from streamlit.testing.v1 import AppTest
from vic import business
from vic.config import ROOT
from vic_apps.domain import initialize


@pytest.mark.parametrize('variant', ['A', 'B', 'C'])
def test_indent_draft_can_be_edited_and_submitted(variant):
    state = initialize(business.generate(58, 0))
    app = AppTest.from_string(f'''
import sys
sys.path.insert(0, {str(ROOT / 'apps/code/app')!r})
import streamlit as st
import benchmark_bridge as bridge
import json
state = json.loads({json.dumps(state)!r})
bridge.business = lambda: {{'epoch': 0, 'state': state}}
def save(op, target, value):
    st.session_state['saved'] = [op, target, value]
bridge.command = save
bridge.render_files()
''').run()
    assert not app.exception
    assert len(app.text_area) == 1
    assert app.text_area[0].label == '编辑源代码'
    assert app.text_area[0].value == state['source']['text']
    assert not app.text_area[0].disabled
    answer = business.transform(58, 'ABC'.index(variant), state)
    app.text_area[0].set_value(answer).run()
    assert app.text_area[0].value == answer
    next(button for button in app.button if button.label == '提交代码').click().run()
    assert not app.exception
    assert app.session_state['saved'] == ['save', 'target', answer]
