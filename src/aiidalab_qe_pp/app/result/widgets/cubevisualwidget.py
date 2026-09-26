import ipywidgets as ipw
from weas_widget import WeasWidget
from aiidalab_qe_pp.app.result.widgets.cubevisualmodel import CubeVisualModel
import numpy as np


class CubeVisualWidget(ipw.VBox):
    """Widget to visualize the output data from PPWorkChain."""

    def __init__(self, model: CubeVisualModel, node, cube_data, plot_num, **kwargs):
        super().__init__(
            children=[ipw.HTML("Loading Cube data...")],
            **kwargs,
        )
        self._model = model
        self._model.node = node
        self._model.cube_data = cube_data
        self._model.plot_num = plot_num
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
        # WeasWidget Setting
        self.viewer = WeasWidget(guiConfig=self.guiConfig)
        self.viewer.from_ase(self._model.input_structure)
        isovalue = 2 * np.std(self._model.cube_data) + np.mean(self._model.cube_data)
        self.viewer.avr.iso.volumetric_data = {"values": self._model.cube_data}
        self.viewer.avr.iso.settings = {
            "positive": {"isovalue": isovalue},
            "negative": {"isovalue": -isovalue, "color": "yellow"},
        }
        self.viewer.avr.color_type = "JMOL"
        self.viewer.avr.model_style = 1

        # Download Cubefile Button
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

        if self._model.reduce_cube_files:
            self.children = [
                self.viewer,
                self.download_button,
                self.download_source_box,
            ]
        else:
            self.children = [self.viewer, self.download_button]

        self.rendered = True
