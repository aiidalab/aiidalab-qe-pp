import traitlets as tl
from aiida import orm
from aiidalab_qe.common.panel import PanelModel
from aiidalab_qe.common.mixins import HasInputStructure
from aiida_quantumespresso.workflows.pw.bands import PwBandsWorkChain
from aiida_quantumespresso.workflows.pw.base import PwBaseWorkChain
from aiida_quantumespresso.calculations.pw import PwCalculation
from paramiko.ssh_exception import SSHException
from aiidalab_qe.plugins.bands.bands_workchain import BandsWorkChain
from aiida_wannier90_workflows.workflows import ProjwfcBandsWorkChain
from aiida_quantumespresso.data.hubbard_structure import HubbardStructureData
from aiida.common.exceptions import NotExistent
import numpy as np


class PpConfigurationSettingsModel(PanelModel, HasInputStructure):
    title = "Pp Settings"
    dependencies = [
        "structure_uuid",
    ]

    structure_selected = tl.Unicode("""<div style="line-height: 140%; padding-top: 0px; padding-bottom: 10px; color: red;">
            Input structure is not set. Please set the structure first.
            </div>""")

    no_avail_cals = tl.Unicode("")

    pwcalc_type_options = tl.List(
        trait=tl.List(tl.Unicode()),
        default_value=[("Bands", "bands"), ("Nscf", "nscf")],
    )
    pwcalc_type = tl.Unicode("bands")

    pwcalc_avail_options = tl.List(
        trait=tl.List(tl.Union([tl.Unicode(), tl.Int()])), default_value=[]
    )
    pwcalc_avail = tl.Int(None, allow_none=True)
    computer = tl.Unicode("")

    reduce_cube_files = tl.Bool(False)

    calc_charge_dens = tl.Bool(False)
    calc_spin_dens = tl.Bool(False)
    calc_wfn = tl.Bool(False)
    calc_ildos = tl.Bool(False)
    calc_stm = tl.Bool(False)
    calc_potential = tl.Bool(False)
    calc_ldos_grid = tl.Bool(False)

    disable_calc_charge_dens = tl.Bool(False)
    disable_calc_spin_dens = tl.Bool(False)
    disable_calc_wfn = tl.Bool(False)
    disable_calc_ildos = tl.Bool(False)
    disable_calc_stm = tl.Bool(False)
    disable_calc_potential = tl.Bool(False)
    disable_calc_ldos_grid = tl.Bool(False)

    charge_dens = tl.Int(0)
    charge_dens_options = tl.List(
        trait=tl.List(tl.Union([tl.Unicode(), tl.Int()])),
        default_value=[
            ("Total charge", 0),
            ("Spin up", 1),
            ("Spin down", 2),
        ],
    )
    charge_dens_options_displayed = tl.Unicode("none")
    stm_options_displayed = tl.Unicode("none")
    ildos_options_displayed = tl.Unicode("none")
    ildos_spin_component_options_displayed = tl.Unicode("none")
    ildos_stm_options_displayed = tl.Unicode("none")
    pwcalc_avail_displayed = tl.Unicode("block")
    wfn_options_displayed = tl.Unicode("none")
    ldos_options_displayed = tl.Unicode("none")

    ldos_emin = tl.Float(0)
    ldos_emax = tl.Float(0)
    ldos_delta_e = tl.Float(0.1)
    degauss_ldos = tl.Float(0.01)
    use_gauss_ldos = tl.Bool(False)

    ildos_emin = tl.Float(0)
    ildos_emax = tl.Float(0)

    ildos_spin_component_options = tl.List(
        trait=tl.List(tl.Union([tl.Unicode(), tl.Int()])),
        default_value=[("Up + Down", 0), ("Up", 1), ("Down", 2)],
    )
    ildos_spin_component = tl.Int(0)
    calc_ildos_stm = tl.Bool(False)
    ildos_stm_heights = tl.Unicode("2.0")
    ildos_stm_currents = tl.Unicode("0.1")

    stm_sample_bias = tl.Unicode("0.0")
    stm_heights = tl.Unicode("2.0")
    stm_currents = tl.Unicode("0.1")

    bands_calc_list = []
    nscf_calc_list = []

    current_calc_lsda = tl.Bool(False)
    current_calc_soc = tl.Bool(False)

    kbands_info = tl.Unicode("")
    kpoints_table = tl.Unicode("")
    number_of_kpoints = tl.Int(1)

    sel_orbital = tl.List(
        trait=tl.List(tl.Union([tl.Unicode(), tl.Int()])),
        default_value=[],
    )

    lsign = tl.Bool(False)

    def fetch_data(self):
        self.bands_calc_list = self.get_available_pwcalcs(self.input_structure, "bands")
        self.nscf_calc_list = self.get_available_pwcalcs(self.input_structure, "nscf")

    def update_pwcalc_avail_options(self, _=None):
        """Update the available PW calculations based on the selected calculation type."""
        calc_list = (
            self.bands_calc_list if self.pwcalc_type == "bands" else self.nscf_calc_list
        )
        if calc_list:
            # Set available calculations and select the first one as default
            self.no_avail_cals = ""
            self.pwcalc_avail_options = calc_list
            self.pwcalc_avail = calc_list[0][1]
            self.on_pwcalc_avail_change()
            self.pwcalc_avail_displayed = "block"
        else:
            # Disable calculations and clear options if no calculations are available
            self.no_avail_cals = f"""<div style="line-height: 140%; padding-top: 0px; padding-bottom: 10px; color: red;">
            No {self.pwcalc_type} calculations available for the selected structure. Please change the pw.x calculation type. If there are no calculations available please selected a different structure.
            </div>"""

            self.disable_all_calcs()
            self.pwcalc_avail_options = []
            self.pwcalc_avail = None
            self.pwcalc_avail_displayed = "none"

    def on_input_structure_change(self, _=None):
        if self.input_structure:
            self.structure_selected = """<div style="line-height: 140%; padding-top: 0px; padding-bottom: 10px; color: green;">
            Structure selected PK: {}.
            </div>""".format(self.input_structure.pk)

            if self.input_structure.pbc == (True, True, True):
                self.calc_stm = False
                self.disable_calc_stm = True

    def on_pwcalc_avail_change(self, _=None):
        if not self.pwcalc_avail:
            return
        calc = orm.load_node(self.pwcalc_avail)
        self.current_calc_lsda = calc.outputs.output_parameters["lsda"]
        self.current_calc_soc = calc.outputs.output_parameters["spin_orbit_calculation"]

        number_of_electrons = calc.outputs.output_parameters["number_of_electrons"]
        number_of_bands = calc.outputs.output_parameters["number_of_bands"]
        self.kbands_info = f"<strong>Number of electrons:</strong> {number_of_electrons}<br> <strong>Number of bands:</strong>  {number_of_bands}"

        kpoints = calc.outputs.output_band.get_kpoints()
        self.kpoints_table = self.update_kpoints_info(kpoints)
        self.number_of_kpoints = calc.outputs.output_parameters["number_of_k_points"]

        self.enable_all_calcs()
        if self.current_calc_lsda:
            self.disable_calc_spin_dens = False
            self.charge_dens_options = [
                ("Total charge", 0),
                ("Spin up", 1),
                ("Spin down", 2),
            ]

        else:
            self.disable_calc_spin_dens = True
            self.charge_dens_options = [("Total charge", 0)]

        if self.current_calc_soc:
            self.disable_calc_stm = True
        else:
            if self.input_structure.pbc != (True, True, True):
                self.disable_calc_stm = False
            else:
                self.disable_calc_stm = True

        if self.pwcalc_type == "nscf":
            self.disable_calc_ldos_grid = True
        else:
            self.disable_calc_ldos_grid = False

    def _get_default(self, trait):
        return self._defaults.get(trait, self.traits()[trait].default_value)

    def on_change_calc_charge_dens(self, _=None):
        if self.calc_charge_dens:
            self.charge_dens_options_displayed = "block"
        else:
            self.charge_dens_options_displayed = "none"

    def on_change_calc_ldos_grid(self, _=None):
        if self.calc_ldos_grid:
            self.ldos_options_displayed = "block"
        else:
            self.ldos_options_displayed = "none"

    def on_change_calc_stm(self, _=None):
        if self.calc_stm:
            self.stm_options_displayed = "block"
        else:
            self.stm_options_displayed = "none"

    def on_change_calc_wfn(self, _=None):
        if self.calc_wfn:
            self.wfn_options_displayed = "block"
        else:
            self.wfn_options_displayed = "none"

    def on_change_calc_ildos(self, _=None):
        if self.calc_ildos:
            self.ildos_options_displayed = "block"
            if self.current_calc_lsda:
                self.ildos_spin_component_options_displayed = "block"
            else:
                self.ildos_spin_component_options_displayed = "none"
        else:
            self.ildos_options_displayed = "none"

    def on_change_calc_ildos_stm(self, _=None):
        if self.calc_ildos_stm:
            self.ildos_stm_options_displayed = "block"
        else:
            self.ildos_stm_options_displayed = "none"

    def disable_all_calcs(self):
        self.disable_calc_charge_dens = True
        self.disable_calc_spin_dens = True
        self.disable_calc_wfn = True
        self.disable_calc_ildos = True
        self.disable_calc_stm = True
        self.disable_calc_potential = True
        self.disable_calc_ldos_grid = True

    def enable_all_calcs(self):
        self.disable_calc_charge_dens = False
        self.disable_calc_spin_dens = False
        self.disable_calc_wfn = False
        self.disable_calc_ildos = False
        self.disable_calc_stm = False
        self.disable_calc_potential = False
        self.disable_calc_ldos_grid = False

    def update_kpoints_info(self, list_kpoints):
        """Update table with the kpoints. Number - (kx,ky,kz).  list_kpoints"""
        rounded_kpoints = np.round(list_kpoints, 4).tolist()
        table_data = [
            (index + 1, kpoint) for index, kpoint in enumerate(rounded_kpoints)
        ]
        table_html = "<table>"
        table_html += "<tr><th style='text-align:center; width: 100px;'>Kpoint</th><th style='text-align:center;'>Crystal</th></tr>"
        table_html += "<tr><th style='text-align:center; width: 100px;'>Index</th><th style='text-align:center;'>coord</th></tr>"
        for row in table_data:
            table_html += "<tr>"
            for cell in row:
                table_html += "<td style='text-align:center;'>{}</td>".format(cell)
            table_html += "</tr>"
        table_html += "</table>"

        return table_html

    def get_available_pwcalcs(self, structure, wc_type):
        avail_list = []
        if wc_type == "bands":
            calc_list = (
                orm.QueryBuilder()
                .append(
                    (orm.StructureData, HubbardStructureData),
                    filters={"id": structure.pk},
                    tag="structure",
                )
                .append(
                    BandsWorkChain,
                    filters={
                        "attributes.exit_status": 0,
                    },
                    with_incoming="structure",
                    tag="bands_wc_qe",
                )
                .append(
                    (PwBandsWorkChain, ProjwfcBandsWorkChain),
                    filters={
                        "attributes.exit_status": 0,
                    },
                    with_incoming="bands_wc_qe",
                    tag="bands_wc",
                )
                .append(
                    PwBaseWorkChain,
                    filters={
                        "attributes.exit_status": 0,
                    },
                    with_incoming="bands_wc",
                    tag="base",
                )
                .append(
                    PwCalculation,
                    filters={
                        "attributes.exit_status": 0,
                    },
                    project=["*"],
                    with_incoming="base",
                    tag="calc",
                )
                .all(flat=True)
            )

        elif wc_type == "nscf":
            calc_list = (
                orm.QueryBuilder()
                .append(
                    (orm.StructureData, HubbardStructureData),
                    filters={"id": structure.pk},
                    tag="structure",
                )
                .append(
                    PwBaseWorkChain,
                    filters={
                        "attributes.exit_status": 0,
                    },
                    with_incoming="structure",
                    tag="base",
                )
                .append(
                    PwCalculation,
                    filters={
                        "attributes.exit_status": 0,
                    },
                    project=["*"],
                    with_incoming="base",
                    tag="calc",
                )
                .all(flat=True)
            )

        calc_list = [
            calc
            for calc in calc_list
            if calc.inputs.parameters["CONTROL"]["calculation"] == wc_type
        ]

        for calc in calc_list:
            try:
                self.computer = calc.computer.label
                calc.outputs.remote_folder.listdir()
                description = "PK: {} LSDA: {} SOC: {} Computer: {}".format(
                    calc.pk,
                    calc.outputs.output_parameters["lsda"],
                    calc.outputs.output_parameters["spin_orbit_calculation"],
                    self.computer,
                )

                avail_list.append((description, calc.pk))
            except OSError:
                # If OSError occurs, skip this iteration
                continue
            # Fix this in future
            except SSHException:
                continue
            # Skip calculations without necessary information
            except NotExistent:
                continue

        return avail_list

    def get_model_state(self):
        return {
            "reduce_cube_files": self.reduce_cube_files,
            "current_calc_lsda": self.current_calc_lsda,
            "pwcalc_avail": self.pwcalc_avail,
            "calc_charge_dens": self.calc_charge_dens,
            "calc_spin_dens": self.calc_spin_dens,
            "calc_potential": self.calc_potential,
            "calc_wfn": self.calc_wfn,
            "calc_ildos": self.calc_ildos,
            "calc_stm": self.calc_stm,
            "calc_ldos_grid": self.calc_ldos_grid,
            "ldos_emin": self.ldos_emin,
            "ldos_emax": self.ldos_emax,
            "ldos_delta_e": self.ldos_delta_e,
            "degauss_ldos": self.degauss_ldos,
            "use_gauss_ldos": self.use_gauss_ldos,
            "charge_dens": self.charge_dens,
            "ildos_emin": self.ildos_emin,
            "ildos_emax": self.ildos_emax,
            "ildos_spin_component": self.ildos_spin_component,
            "calc_ildos_stm": self.calc_ildos_stm,
            "ildos_stm_heights": self.ildos_stm_heights,
            "ildos_stm_currents": self.ildos_stm_currents,
            "stm_sample_bias": self.stm_sample_bias,
            "stm_heights": self.stm_heights,
            "stm_currents": self.stm_currents,
            "sel_orbital": self.sel_orbital,
            "pwcalc_type": self.pwcalc_type,
            "lsign": self.lsign,
        }

    def set_model_state(self, parameters: dict):
        self.reduce_cube_files = parameters.get("reduce_cube_files", False)
        self.pwcalc_type = parameters.get("pwcalc_type", "bands")
        self.current_calc_lsda = parameters.get("current_calc_lsda", False)
        self.pwcalc_avail = parameters.get("pwcalc_avail", None)
        self.calc_charge_dens = parameters.get("calc_charge_dens", False)
        self.calc_spin_dens = parameters.get("calc_spin_dens", False)
        self.calc_potential = parameters.get("calc_potential", False)
        self.calc_wfn = parameters.get("calc_wfn", False)
        self.calc_ildos = parameters.get("calc_ildos", False)
        self.calc_stm = parameters.get("calc_stm", False)
        self.calc_ldos_grid = parameters.get("calc_ldos_grid", False)
        self.ldos_emin = parameters.get("ldos_emin", 0)
        self.ldos_emax = parameters.get("ldos_emax", 0)
        self.ldos_delta_e = parameters.get("ldos_delta_e", 0.1)
        self.degauss_ldos = parameters.get("degauss_ldos", 0.01)
        self.use_gauss_ldos = parameters.get("use_gauss_ldos", False)
        self.charge_dens = parameters.get("charge_dens", 0)
        self.ildos_emin = parameters.get("ildos_emin", 0)
        self.ildos_emax = parameters.get("ildos_emax", 0)
        self.ildos_spin_component = parameters.get("ildos_spin_component", 0)
        self.stm_sample_bias = parameters.get("stm_sample_bias", "0.0")
        self.stm_heights = parameters.get("stm_heights", "2.0")
        self.stm_currents = parameters.get("stm_currents", "0.00005")
        self.calc_ildos_stm = parameters.get("calc_ildos_stm", False)
        self.ildos_stm_heights = parameters.get("ildos_stm_heights", "2.0")
        self.ildos_stm_currents = parameters.get("ildos_stm_currents", "0.1")
        self.sel_orbital = parameters.get("sel_orbital", [])
        self.pwcalc_avail_options = [
            [
                "PK: {} LSDA: {} SOC: {} Computer: {}".format(
                    parameters.get("pwcalc_avail", None),
                    parameters.get("current_calc_lsda", False),
                    parameters.get("current_calc_soc", False),
                    parameters.get("computer", "localhost"),
                ),
                parameters.get("pwcalc_avail", 0),
            ]
        ]
        self.lsign = parameters.get("lsign", False)
        self.on_change_calc_charge_dens()
        self.on_change_calc_stm()
        self.on_change_calc_wfn()
        self.on_change_calc_ildos()
        self.on_change_calc_ildos_stm()
        self.on_change_calc_ldos_grid()
