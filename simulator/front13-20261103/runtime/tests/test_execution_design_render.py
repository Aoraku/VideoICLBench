import pytest
from videoicl_isaaclab.execution_design_render import configure_render_for_specs, REVISION, SETTINGS


class Settings:
    def __init__(self):
        self.data = {'/rtx/translucency/enabled': False}
        self.writes = []
    def get(self, key):return self.data.get(key)
    def set_bool(self, key, value):
        assert type(value) is bool
        self.data[key] = value;self.writes.append(key)
    def set_int(self, key, value):
        assert type(value) is int
        self.data[key] = value;self.writes.append(key)


def test_legacy_and_mixed_cohorts_do_not_change_renderer():
    settings = Settings()
    assert configure_render_for_specs([{}], settings)['applied'] is False
    revised = dict(execution_design=dict(revision=REVISION))
    with pytest.raises(ValueError, match='isolated'):
        configure_render_for_specs([{}, revised], settings)
    assert settings.writes == []
    assert settings.data == {'/rtx/translucency/enabled': False}


def test_revised_transmission_readback_preserves_physics_settings():
    settings = Settings();settings.data['/physics/timeStepsPerSecond'] = 120
    receipt = configure_render_for_specs([dict(execution_design=dict(revision=REVISION))], settings)
    assert receipt['before']['/rtx/translucency/enabled'] is False
    assert receipt['actual'] == SETTINGS
    assert settings.data['/physics/timeStepsPerSecond'] == 120
    assert receipt['visual_acceptance'] == 'pending_native_review'


def test_readback_failure_cannot_silently_admit_black_transmission():
    settings = Settings()
    settings.set_bool = lambda key, value: None
    with pytest.raises(RuntimeError, match='readback'):
        configure_render_for_specs([dict(execution_design=dict(revision=REVISION))], settings)
