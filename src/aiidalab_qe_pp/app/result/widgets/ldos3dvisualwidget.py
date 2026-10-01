import ipywidgets as ipw
from weas_widget import WeasWidget
from aiidalab_qe_pp.app.result.widgets.ldos3dvisualmodel import Ldos3DVisualModel


class Ldos3DVisualWidget(ipw.VBox):
    """Widget to visualize the output data from PPWorkChain."""

    def __init__(self, model: Ldos3DVisualModel, node, **kwargs):
        super().__init__(
            children=[ipw.HTML("Loading Ldos3D data...")],
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

        self.ldos_files_list = ipw.Dropdown(
            description="Ldos files:",
            style={"description_width": "initial"},
            layout={"width": "500px"},
        )
        ipw.dlink(
            (self._model, "ldos_files_list_options"),
            (self.ldos_files_list, "options"),
        )
        ipw.link((self._model, "ldos_file"), (self.ldos_files_list, "value"))
        self.ldos_files_list.observe(self._on_ldos_file_change, "value")

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
                self.ldos_files_list,
                self.plot,
                self.download_button,
                self.download_source_box,
            ]
        else:
            self.children = [self.ldos_files_list, self.plot, self.download_button]
        self.rendered = True

    def _update_plot(self):
        cube_data, isovalue = self._model.update_plot()
        self.plot.avr.iso.volumetric_data = {"values": cube_data}
        self.plot.avr.iso.settings = {
            "positive": {"isovalue": isovalue},
            "negative": {"isovalue": -isovalue, "color": "yellow"},
        }
        self.plot.avr.draw()

    def _on_ldos_file_change(self, _):
        self._update_plot()
