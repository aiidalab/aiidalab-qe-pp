from aiidalab_qe.common.mvc import Model
import traitlets as tl
from aiida.orm import StructureData
from aiida.orm.nodes.process.workflow.workchain import WorkChainNode
import numpy as np
from ase.atoms import Atoms
from pymatgen.io.common import VolumetricData
import re
import base64
from IPython.display import Javascript
from IPython.display import display
import tempfile
import os
from aiidalab_qe_pp.app.result.widgets.error_timeout import ErrorTimeoutMixin
from aiidalab_qe_pp.app.utils import download_remote_file


class WfnVisualModel(ErrorTimeoutMixin, Model):
    node = tl.Instance(WorkChainNode, allow_none=True)
    input_structure = tl.Instance(Atoms, allow_none=True)
    aiida_structure = tl.Instance(StructureData, allow_none=True)
    cube_data = tl.Instance(np.ndarray, allow_none=True)
    reduce_cube_files = tl.Bool(False)
    error_message = tl.Unicode("")

    kpoint_band_data = tl.List(
        trait=tl.Dict(),
        allow_none=True,
        default_value=[],
    )
    cube_data_dict = tl.Dict(
        allow_none=True,
        default_value={},
    )

    kpoints_dropdown_options = tl.List()
    bands_dropdown_options = tl.List()

    spin_options = tl.List(
        trait=tl.List(tl.Union([tl.Unicode(), tl.Unicode()])),
        default_value=[("Up", "up"), ("Down", "down")],
    )
    spin_displayed = tl.Unicode("none")
    spin = tl.Unicode("up")

    kpoint = tl.Int(1)
    band = tl.Int(1)

    lsda = tl.Bool(False)
    number_of_k_points = tl.Int(0)

    def fetch_data(self):
        self.input_structure = self.node.inputs.structure.get_ase()
        self.aiida_structure = self.node.inputs.structure
        self.kpoint_band_data = self.process_orbitals(
            self.node.inputs.parameters["wfn"]
        )
        self.lsda = self.node.inputs.parameters["wfn"]["lsda"]
        self.number_of_k_points = self.node.inputs.parameters["wfn"][
            "number_of_k_points"
        ]
        self.cube_data_dict = self.get_cube_data_dict()
        self.kpoints_dropdown_options = [
            entry["kpoint"] for entry in self.kpoint_band_data
        ]
        if self.lsda:
            self.kpoints_dropdown_options = self.kpoints_dropdown_options[
                : len(self.kpoints_dropdown_options) // 2
            ]
            self.spin_displayed = "block"
        self.kpoint = self.kpoints_dropdown_options[0]
        self._update_bands_options(self.kpoint)
        self.band = self.bands_dropdown_options[0]
        self.reduce_cube_files = self.node.inputs.parameters.get(
            "reduce_cube_files", False
        )

    def _update_bands_options(self, kpoint):
        bands = next(
            entry["bands"]
            for entry in self.kpoint_band_data
            if entry["kpoint"] == self.kpoint
        )
        self.bands_dropdown_options = bands

    def expand_kpoint_band_string(self, s):
        match = re.match(r"kp_(\d+)_kb_(\d+)_(\d+)", s)
        if match:
            kpoint = match.group(1)
            start_band = int(match.group(2))
            end_band = int(match.group(3))

            return [
                f"kp_{kpoint}_kb_{band}" for band in range(start_band, end_band + 1)
            ]
        else:
            raise ValueError("String format is not correct")

    def on_kpoints_change(self):
        self._update_bands_options(self.kpoint)
        self.band = self.bands_dropdown_options[0]

    def get_cube_data_dict(self):
        data_dict = {}

        for key in self.node.outputs.wfn.keys():
            if hasattr(self.node.outputs.wfn[key], "output_data_multiple"):
                labels = self.expand_kpoint_band_string(key)
                output_data_multiple = self.node.outputs.wfn[key].output_data_multiple

                for i, output_key in enumerate(output_data_multiple.keys()):
                    data_dict[labels[i]] = output_data_multiple[output_key]
            elif hasattr(self.node.outputs.wfn[key], "output_data"):
                data_dict[key] = self.node.outputs.wfn[key].output_data
        return data_dict

    def update_plot(self):
        """Update the viewer with the selected kpoint and band data."""
        kpoint = self.kpoint
        if self.lsda and self.spin == "down":
            kpoint += self.number_of_k_points

        key = f"kp_{kpoint}_kb_{self.band}"
        self.cube_data = self.cube_data_dict.get(key).get_array("data")
        isovalue = 2 * np.std(self.cube_data) + np.mean(self.cube_data)
        return self.cube_data, isovalue

    def process_orbitals(self, data):
        orbitals = data["orbitals"]
        kpoint_band_dict = {}

        for orbital in orbitals:
            kpoint = orbital["kpoint"]
            if "kband(2)" in orbital:
                bands = list(range(orbital["kband(1)"], orbital["kband(2)"] + 1))
            else:
                bands = [orbital["kband(1)"]]

            if kpoint not in kpoint_band_dict:
                kpoint_band_dict[kpoint] = set()

            kpoint_band_dict[kpoint].update(bands)

        # Convert the dictionary to the desired list format
        kpoint_band_data = [
            {"kpoint": kpoint, "bands": sorted(list(bands))}
            for kpoint, bands in kpoint_band_dict.items()
        ]

        return kpoint_band_data

    def download_cube(self, _=None):
        """Download the cube file with the current kpoint and band in the filename."""
        kpoint = self.kpoint
        band = self.band

        if self.lsda and self.spin == "down":
            kpoint += self.number_of_k_points

        filename = f"plot_wfn_kp_{kpoint}_kb_{band}"

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

    def get_key_remote_folder(self, outputs, kpoint, band):
        result = ""
        for key in outputs.keys():
            list_elements = key.split("_")
            rel_kpoint = int(list_elements[1])
            if len(list_elements) == 4:
                rel_band = [int(list_elements[3])]
            elif len(list_elements) == 5:
                rel_band = list(range(int(list_elements[3]), int(list_elements[4]) + 1))

            if rel_kpoint == kpoint and band in rel_band:
                result = key

        return result

    def download_source_files(self, _=None):
        kpoint = self.kpoint
        band = self.band

        if self.lsda and self.spin == "down":
            kpoint += self.number_of_k_points

        key_dict = self.get_key_remote_folder(self.node.outputs.wfn, kpoint, band)

        if key_dict == "":
            message = "Unfortunately there is no access to this file."
            self.error_message = (
                f'<div style="color: red; font-weight: bold;">{message}</div>'
            )
            self.schedule_error_clear(3.0)
            return

        remote_folder = self.node.outputs.wfn[key_dict].remote_folder

        if remote_folder.is_empty:
            message = "Unfortunately the remote folder is empty."
            self.error_message = (
                f'<div style="color: red; font-weight: bold;">{message}</div>'
            )
            self.schedule_error_clear(10.0)
            return

        filtered_files = [
            file for file in remote_folder.listdir() if file.endswith("aiida.fileout")
        ]

        file_download = None
        if "aiida.fileout" in filtered_files:
            file_download = "aiida.fileout"
        else:
            # To take the numbers between B and aiida.fileout
            pattern = re.compile(r"B(\d+)aiida\.fileout$")
            for file in filtered_files:
                match = pattern.search(file)
                if match:
                    band_number = int(match.group(1))
                    if band_number == band:
                        file_download = file
                        break
        if file_download is None:
            self.error_message = "Unfortunately there is a problem with the file."
            self.schedule_error_clear(3.0)
            return

        download_remote_file(
            remote_folder, f"plot_wfn_kp_{kpoint}_kb_{band}.cube", file_download
        )
