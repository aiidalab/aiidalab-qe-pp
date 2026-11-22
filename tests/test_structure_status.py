from types import SimpleNamespace

import pytest

from aiidalab_qe.app.configuration.model import ConfigurationStepModel
from aiidalab_qe_pp.app.model import PpConfigurationSettingsModel
from aiidalab_qe_pp.app.setting import PpConfigurationSettingPanel


@pytest.fixture
def structure_lookup(monkeypatch):
    structures = {
        "silicon": SimpleNamespace(pk=17, pbc=(True, True, True)),
        "other": SimpleNamespace(pk=29, pbc=(True, True, True)),
    }
    monkeypatch.setattr(
        PpConfigurationSettingsModel,
        "input_structure",
        property(lambda model: structures.get(model.structure_uuid)),
    )
    # Exercise the real dropdown without requiring a remote computer.
    monkeypatch.setattr(
        PpConfigurationSettingsModel,
        "get_available_pwcalcs",
        lambda self, structure, kind: (
            [("Si bands", 41)] if structure.pk == 17 and kind == "bands" else []
        ),
    )
    monkeypatch.setattr(
        PpConfigurationSettingsModel, "on_pwcalc_avail_change", lambda *_: None
    )


def test_preselected_structure_on_first_render(structure_lookup):
    host = ConfigurationStepModel()
    host.structure_uuid = "silicon"
    model = PpConfigurationSettingsModel()
    host.add_model("pp", model)
    panel = PpConfigurationSettingPanel(model)
    panel.render()

    assert "Structure selected PK: 17" in panel.structure_selected.value
    assert panel.pwcalc_avail.value == 41

    host.structure_uuid = "other"
    assert "Structure selected PK: 29" in panel.structure_selected.value
    assert model.pwcalc_avail is None
    assert model.pwcalc_avail_options == []
    host.structure_uuid = None
    assert "Input structure is not set" in panel.structure_selected.value


def test_structure_selected_after_first_render(structure_lookup):
    model = PpConfigurationSettingsModel()
    panel = PpConfigurationSettingPanel(model)
    panel.render()
    assert "Input structure is not set" in panel.structure_selected.value
    assert not model.no_avail_cals
    assert model.pwcalc_avail is None

    model.structure_uuid = "silicon"
    assert "Structure selected PK: 17" in panel.structure_selected.value
    assert panel.pwcalc_avail.value == 41
