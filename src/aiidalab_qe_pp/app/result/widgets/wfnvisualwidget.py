import ipywidgets as ipw

from aiidalab_qe_pp.app.result.widgets.wfnvisualmodel import WfnVisualModel
from weas_widget import WeasWidget


class WfnVisualWidget(ipw.VBox):
    def __init__(self, model: WfnVisualModel, node, **kwargs):
        super().__init__(
            children=[ipw.HTML("Loading wfn data...")],
            **kwargs,
        )
        self._model = model
        self._model.node = node
        self._model.fetch_data()
        self.rendered = False

    def close(self):
        if hasattr(self, "_model"):
            self._model.cancel_error_timeout()
        super().close()

    def render(self):
        if self.rendered:
            return

        self.guiConfig = {
            "components": {
                "atomsControl": True,
                "buttons": True,
                "cameraControls": True,
                "enabled": True,
            },
            "buttons": {
                "fullscreen": True,
                "download": True,
                "measurement": True,
                "enabled": True,
            },
        }

        self.kpoints_dropdown = ipw.Dropdown(
            description="Kpoint:",
            style={"description_width": "initial"},
            layout={"width": "150px"},
        )
        ipw.dlink(
            (self._model, "kpoints_dropdown_options"),
            (self.kpoints_dropdown, "options"),
        )
        ipw.link((self._model, "kpoint"), (self.kpoints_dropdown, "value"))
        self.kpoints_dropdown.observe(self._on_kpoints_change, "value")

        self.bands_dropdown = ipw.Dropdown(
            description="Band:",
            style={"description_width": "initial"},
            layout={"width": "150px"},
        )
        ipw.dlink(
            (self._model, "bands_dropdown_options"), (self.bands_dropdown, "options")
        )
        ipw.link((self._model, "band"), (self.bands_dropdown, "value"))
        self.bands_dropdown.observe(self._on_band_change, "value")

        self.spin = ipw.Dropdown(
            description="Spin:",
            style={"description_width": "initial"},
            layout={"width": "150px"},
        )
        ipw.dlink((self._model, "spin_options"), (self.spin, "options"))
        ipw.link((self._model, "spin"), (self.spin, "value"))
        ipw.link(
            (self._model, "spin_displayed"),
            (self.spin.layout, "display"),
        )
        self.spin.observe(self._on_spin_change, "value")

        self.controls = ipw.HBox(
            [self.kpoints_dropdown, self.bands_dropdown, self.spin]
        )

        self.download_button = ipw.Button(
            description="Cube file",
            button_style="primary",
            icon="download",
        )
        self.download_button.on_click(self._model.download_cube)

        # Download original files from HPC source
        self.info_original_files = ipw.HTML(
            """
            <b>Download original files from computer source:</b>
            <p>Since you selected the option to reduce the cube files, the original files can be downloaded from the computer source, provided the directories are still available.</p>
            <p>Please ensure your SSH connection is working and click on the 'Source file' button.</p>
            """
        )
        self.download_source_button = ipw.Button(
            description="Source file",
            button_style="primary",
            icon="download",
        )
        self.download_source_button.on_click(self._model.download_source_files)
        self.error_message = ipw.HTML("")
        ipw.link((self._model, "error_message"), (self.error_message, "value"))
        self.download_source_box = ipw.VBox(
            [self.info_original_files, self.download_source_button, self.error_message]
        )

        self.plot = WeasWidget(guiConfig=self.guiConfig)
        self.plot.from_ase(self._model.input_structure)
        self.plot.avr.color_type = "JMOL"
        self.plot.avr.model_style = 1
        self._update_plot()

        if self._model.reduce_cube_files:
            self.children = [
                self.controls,
                self.plot,
                self.download_button,
                self.download_source_box,
            ]
        else:
            self.children = [self.controls, self.plot, self.download_button]
        self.rendered = True

    def _update_plot(self):
        cube_data, isovalue = self._model.update_plot()
        self.plot.avr.iso.volumetric_data = {"values": cube_data}
        self.plot.avr.iso.settings = {
            "positive": {"isovalue": isovalue},
            "negative": {"isovalue": -isovalue, "color": "yellow"},
        }
        self.plot.avr.draw()

    def _on_kpoints_change(self, _):
        self._model.on_kpoints_change()
        self._update_plot()

    def _on_band_change(self, _):
        self._update_plot()

    def _on_spin_change(self, _):
        self._update_plot()
