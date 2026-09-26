from aiidalab_qe.common.mvc import Model
import traitlets as tl
from aiida.orm import StructureData
from aiida.orm.nodes.process.workflow.workchain import WorkChainNode
import numpy as np
from ase.atoms import Atoms
from pymatgen.io.common import VolumetricData
import base64
from IPython.display import display, Javascript
import tempfile
import os
from aiidalab_qe_pp.app.result.widgets.error_timeout import ErrorTimeoutMixin

from aiidalab_qe_pp.app.utils import download_remote_file


class Ldos3DVisualModel(ErrorTimeoutMixin, Model):
    node = tl.Instance(WorkChainNode, allow_none=True)
    input_structure = tl.Instance(Atoms, allow_none=True)
    aiida_structure = tl.Instance(StructureData, allow_none=True)
    cube_data = tl.Instance(np.ndarray, allow_none=True)
    reduce_cube_files = tl.Bool(False)
    error_message = tl.Unicode("")

    # calc_node_options = tl.List(trait=tl.List(tl.Union([tl.Unicode(), tl.Unicode()])), default_value=[])
    ldos_files_list_options = tl.List(
        trait=tl.List(tl.Union([tl.Unicode(), tl.Unicode()])), default_value=[]
    )  # tl.List()
    ldos_file = tl.Unicode()

    def fetch_data(self):
        self.input_structure = self.node.inputs.structure.get_ase()
        self.aiida_structure = self.node.inputs.structure
        self.reduce_cube_files = self.node.inputs.parameters.get(
            "reduce_cube_files", False
        )
        self.ldos_files_list_options = self.get_ldos_files_list_options()
        self.ldos_file = self.ldos_files_list_options[0][1]
        if "output_data_multiple" in self.node.outputs.ldos_grid:
            self.cube_data = self.node.outputs.ldos_grid.output_data_multiple[
                self.ldos_file
            ].get_array("data")
        else:
            self.cube_data = self.node.outputs.ldos_grid.output_data.get_array("data")

    def get_ldos_files_list_options(self):
        import re

        pattern = r"^\s*Energy\s*=.*"
        aiida_out = self.node.outputs.ldos_grid.retrieved.get_object_content(
            "aiida.out"
        )
        description_list = [
            match.strip() for match in re.findall(pattern, aiida_out, re.MULTILINE)
        ]
        fermi = self.node.inputs.parameters.get("fermi", 0.0)
        updated_description_list = [
            f"Energy =  {float(line.split('=')[1].split('eV')[0].strip()) - fermi:.5f} eV, broadening ={line.split('broadening =')[1]}"
            for line in description_list
        ]

        if "output_data_multiple" in self.node.outputs.ldos_grid:
            keys = list(self.node.outputs.ldos_grid.output_data_multiple.keys())
        else:
            keys = list("output_data")
        return list(zip(updated_description_list, keys))

    def update_plot(self):
        if "output_data_multiple" in self.node.outputs.ldos_grid:
            self.cube_data = self.node.outputs.ldos_grid.output_data_multiple[
                self.ldos_file
            ].get_array("data")
        else:
            self.cube_data = self.node.outputs.ldos_grid.output_data.get_array("data")
        isovalue = 2 * np.std(self.cube_data) + np.mean(self.cube_data)
        return self.cube_data, isovalue

    def download_cube(self, _=None):
        """Download the cube file with the current kpoint and band in the filename."""
        filename = f"ldos_{self.ldos_file}"
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
        remote_folder = self.node.outputs.ldos_grid.remote_folder
        if remote_folder.is_empty:
            message = "Unfortunately the remote folder is empty."
            self.error_message = (
                f'<div style="color: red; font-weight: bold;">{message}</div>'
            )
            self.schedule_error_clear(10.0)
            return

        filename = (
            f"plot_ldos_{self.ldos_file}.cube"
            if "output_data_multiple" in self.node.outputs.ldos_grid
            else "plot_ldos.cube"
        )
        filename_retrieved = (
            f"aiida.filplot{self.ldos_file}aiida.fileout"
            if "output_data_multiple" in self.node.outputs.ldos_grid
            else "aiida.fileout"
        )

        download_remote_file(
            remote_folder,
            filename,
            filename_retrieved,
        )
