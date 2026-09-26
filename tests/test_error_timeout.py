"""Error-message callbacks must not create or outlive worker threads."""

import asyncio
import gc
import threading
import weakref
from unittest.mock import patch

import pytest
import ipywidgets as ipw

from aiidalab_qe_pp.app.result.result import PpResultsPanel
from aiidalab_qe_pp.app.result.model import PpResultsModel

from aiidalab_qe_pp.app.result.widgets.cubevisualmodel import CubeVisualModel
from aiidalab_qe_pp.app.result.widgets.ldos3dvisualmodel import Ldos3DVisualModel
from aiidalab_qe_pp.app.result.widgets.wfnvisualmodel import WfnVisualModel
from aiidalab_qe_pp.app.result.widgets.cubevisualwidget import CubeVisualWidget
from aiidalab_qe_pp.app.result.widgets.ldos3dvisualwidget import Ldos3DVisualWidget
from aiidalab_qe_pp.app.result.widgets.wfnvisualwidget import WfnVisualWidget


@pytest.mark.parametrize(
    "model_type", [CubeVisualModel, WfnVisualModel, Ldos3DVisualModel]
)
def test_replaces_timeout_on_ui_thread(model_type):
    async def check():
        model = model_type()
        threads = set(threading.enumerate())
        model.error_message = "first"
        model.schedule_error_clear(0)
        old_timeout = model._error_timeout
        model.error_message = "second"
        model.schedule_error_clear(3600)
        assert old_timeout.cancelled()
        await asyncio.sleep(0.001)
        assert model.error_message == "second"
        assert set(threading.enumerate()) == threads
        callback_threads = []
        model.observe(
            lambda change: callback_threads.append(threading.get_ident()),
            "error_message",
        )
        model.schedule_error_clear(0)
        await asyncio.sleep(0.001)
        assert model.error_message == ""
        assert model._error_timeout is None
        assert callback_threads == [threading.get_ident()]

    asyncio.run(check())


def test_timeout_does_not_keep_model_alive():
    async def check():
        model = WfnVisualModel()
        model.schedule_error_clear(3600)
        timeout = model._error_timeout
        reference = weakref.ref(model)
        del model
        gc.collect()
        assert reference() is None
        timeout.cancel()

    asyncio.run(check())


@pytest.mark.parametrize(
    "widget_type", [CubeVisualWidget, WfnVisualWidget, Ldos3DVisualWidget]
)
def test_widget_close_cancels_timeout(widget_type):
    async def check():
        model = CubeVisualModel()
        model.error_message = "still visible"
        model.schedule_error_clear(0)
        timeout = model._error_timeout
        # No AiiDA profile or scientific data is needed to exercise close.
        widget = widget_type.__new__(widget_type)
        with patch("ipywidgets.VBox.close"):
            widget._model = model
            widget.close()
            widget.close()
        assert timeout.cancelled()
        assert model._error_timeout is None
        await asyncio.sleep(0.001)
        assert model.error_message == "still visible"

    asyncio.run(check())


def test_headless_error_does_not_start_thread():
    model = CubeVisualModel()
    threads = set(threading.enumerate())
    model.error_message = "missing file"
    model.schedule_error_clear(0)
    assert model._error_timeout is None
    assert model.error_message == "missing file"
    assert set(threading.enumerate()) == threads


def test_panel_close_cancels_child_timeout_once():
    async def check():
        panel = PpResultsPanel(PpResultsModel())
        child = CubeVisualWidget.__new__(CubeVisualWidget)
        ipw.VBox.__init__(child)
        child._model = CubeVisualModel()
        child._model.schedule_error_clear(3600)
        timeout = child._model._error_timeout
        panel.tabs = ipw.Tab(children=[child], selected_index=None)
        panel.tabs.observe(panel._on_tab_change, "selected_index")
        panel.close()
        panel.close()
        assert timeout.cancelled()
        assert child.comm is None
        assert panel.tabs.comm is None

    asyncio.run(check())
