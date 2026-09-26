"""PP Plugin results panel."""

from aiidalab_qe.common.panel import ResultsPanel
from aiidalab_qe_pp.app.result.model import PpResultsModel
import ipywidgets as ipw

from aiidalab_qe_pp.app.result.widgets.cubevisualmodel import CubeVisualModel
from aiidalab_qe_pp.app.result.widgets.cubevisualwidget import CubeVisualWidget
from aiidalab_qe_pp.app.result.widgets.stmvisualmodel import STMVisualModel
from aiidalab_qe_pp.app.result.widgets.stmvisualwidget import STMVisualWidget

from aiidalab_qe_pp.app.result.widgets.wfnvisualwidget import WfnVisualWidget
from aiidalab_qe_pp.app.result.widgets.wfnvisualmodel import WfnVisualModel

from aiidalab_qe_pp.app.result.widgets.ldos3dvisualwidget import Ldos3DVisualWidget
from aiidalab_qe_pp.app.result.widgets.ldos3dvisualmodel import Ldos3DVisualModel


class PpResultsPanel(ResultsPanel[PpResultsModel]):
    title = "Post-processing"
    identifier = "pp"
    workchain_labels = ["pp"]

    def render(self):
        if self.rendered:
            return

        self.tabs = ipw.Tab(
            layout=ipw.Layout(min_height="250px"),
            selected_index=None,
        )
        self.tabs.observe(
            self._on_tab_change,
            "selected_index",
        )

        tab_data = []
        pp_node = self._model.get_pp_node()

        needs_charge_dens = self._model.needs_charge_dens_tab()

        if needs_charge_dens:
            node = self._model.fetch_child_process_node()
            cube_data = pp_node.charge_dens.output_data.get_array("data")
            plot_num = "charge_dens"
            cube_visual_model = CubeVisualModel()
            cube_visual_widget = CubeVisualWidget(
                cube_visual_model, node, cube_data, plot_num
            )
            tab_data.append(("Charge density", cube_visual_widget))

        needs_spin_dens = self._model.needs_spin_dens_tab()
        if needs_spin_dens:
            node = self._model.fetch_child_process_node()
            cube_data = pp_node.spin_dens.output_data.get_array("data")
            plot_num = "spin_dens"
            cube_visual_model = CubeVisualModel()
            cube_visual_widget = CubeVisualWidget(
                cube_visual_model, node, cube_data, plot_num
            )

            tab_data.append(("Spin density", cube_visual_widget))

        needs_potential = self._model.needs_potential_tab()
        if needs_potential:
            node = self._model.fetch_child_process_node()
            cube_data = pp_node.potential.output_data.get_array("data")
            plot_num = "potential"
            cube_visual_model = CubeVisualModel()
            cube_visual_widget = CubeVisualWidget(
                cube_visual_model, node, cube_data, plot_num
            )
            tab_data.append(("Potential", cube_visual_widget))

        needs_wfn = self._model.needs_wfn_tab()
        if needs_wfn:
            node = self._model.fetch_child_process_node()
            wfn_visual_model = WfnVisualModel()
            wfn_visual_widget = WfnVisualWidget(
                wfn_visual_model,
                node,
            )
            tab_data.append(("Orbitals", wfn_visual_widget))

        needs_ildos = self._model.needs_ildos_tab()
        if needs_ildos:
            node = self._model.fetch_child_process_node()
            cube_data = pp_node.ildos.output_data.get_array("data")
            plot_num = "ildos"
            cube_visual_model = CubeVisualModel()
            cube_visual_widget = CubeVisualWidget(
                cube_visual_model, node, cube_data, plot_num
            )
            tab_data.append(("ILDOS", cube_visual_widget))

        needs_ildos_stm = self._model.needs_ildos_stm_tab()
        if needs_ildos_stm:
            ildos_stm_visual_model = STMVisualModel()
            ildos_stm_visual_widget = STMVisualWidget(
                ildos_stm_visual_model, pp_node["ildos_stm"]
            )
            tab_data.append(("ILDOS STM", ildos_stm_visual_widget))

        needs_stm = self._model.needs_stm_tab()
        if needs_stm:
            stm_visual_model = STMVisualModel()
            stm_visual_widget = STMVisualWidget(stm_visual_model, pp_node["stm"])
            tab_data.append(("STM", stm_visual_widget))

        needs_ldos = self._model.needs_ldos_tab()
        if needs_ldos:
            node = self._model.fetch_child_process_node()
            cube_visual_model = Ldos3DVisualModel()
            cube_visual_widget = Ldos3DVisualWidget(
                cube_visual_model,
                node,
            )
            tab_data.append(("LDOS", cube_visual_widget))

        # Assign children and titles dynamically
        self.tabs.children = [content for _, content in tab_data]
        for index, (title, _) in enumerate(tab_data):
            self.tabs.set_title(index, title)

        self.children = [self.tabs]
        self.tabs.selected_index = 0
        self.rendered = True

    def close(self):
        if getattr(self, "_pp_closed", False):
            return
        self._pp_closed = True
        if hasattr(self, "tabs"):
            self.tabs.unobserve(self._on_tab_change, "selected_index")
            for child in self.tabs.children:
                child.close()
            self.tabs.children = ()
            self.tabs.close()
            self.tabs.layout.close()
        super().close()

    def _on_tab_change(self, change):
        if (tab_index := change["new"]) is None:
            return
        self.tabs.children[tab_index].render()  # type: ignore
