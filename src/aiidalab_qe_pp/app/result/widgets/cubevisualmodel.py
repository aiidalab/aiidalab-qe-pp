from aiidalab_qe.common.mvc import Model
import traitlets as tl
import base64
from ase.atoms import Atoms
from IPython.display import Javascript
from IPython.display import display
import tempfile
from pymatgen.io.common import VolumetricData
import os
from aiida.orm import StructureData
from aiida.orm.nodes.process.workflow.workchain import WorkChainNode
import numpy as np
from aiidalab_qe_pp.app.result.widgets.error_timeout import ErrorTimeoutMixin

from aiidalab_qe_pp.app.utils import download_remote_file


class CubeVisualModel(ErrorTimeoutMixin, Model):
    node = tl.Instance(WorkChainNode, allow_none=True)
    input_structure = tl.Instance(Atoms, allow_none=True)
    aiida_structure = tl.Instance(StructureData, allow_none=True)
    cube_data = tl.Instance(np.ndarray, allow_none=True)
    plot_num = tl.Unicode("spin_dens")
    reduce_cube_files = tl.Bool(False)
    error_message = tl.Unicode("")

    def fetch_data(self):
        self.input_structure = self.node.inputs.structure.get_ase()
        self.aiida_structure = self.node.inputs.structure
        self.reduce_cube_files = self.node.inputs.parameters.get(
            "reduce_cube_files", False
        )

    def download_cube(self, _=None, filename="plot"):
        # Create a temporary file, write to it, and initiate download
        with tempfile.NamedTemporaryFile(delete=False, suffix=".cube") as tmp:
            # Write the cube data to a temporary file using pymatgen's VolumetricData
            if self.aiida_structure.pbc != [True, True, True]:
                structure_temp = self.aiida_structure.clone()
                structure_temp.pbc = [True, True, True]
                structure = structure_temp.get_pymatgen()
            else:
                structure = self.aiida_structure.get_pymatgen()

            my_cube = VolumetricData(
                structure=structure, data={"total": self.cube_data}
            )
            my_cube.to_cube(tmp.name)

            # Move the file pointer back to the start for reading
            tmp.seek(0)
            raw_bytes = tmp.read()

        # Encode the file content to base64
        base64_payload = base64.b64encode(raw_bytes).decode()

        # if filename is not provided, use plot_num
        if filename == "plot":
            filename = f"plot_{self.plot_num}"

        # JavaScript to trigger download
        filename = f"{filename}.cube"
        js_download = Javascript(
            f"""
            var link = document.createElement('a');
            link.href = "data:application/octet-stream;base64,{base64_payload}";
            link.download = "{filename}";
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            """
        )
        display(js_download)

        # Clean up by removing the temporary file
        os.unlink(tmp.name)

    def download_source_files(self, _=None):
        remote_folder = self.node.outputs[f"{self.plot_num}"].remote_folder
        if remote_folder.is_empty:
            message = "Unfortunately the remote folder is empty."
            self.error_message = (
                f'<div style="color: red; font-weight: bold;">{message}</div>'
            )
            self.schedule_error_clear(10.0)
            return

        download_remote_file(
            remote_folder, f"plot_{self.plot_num}.cube", "aiida.fileout"
        )
