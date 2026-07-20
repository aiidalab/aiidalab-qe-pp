from typing import Any

from aiida.plugins import CalculationFactory
from aiida.engine import ToContext, WorkChain, if_
from aiida import orm
from aiida.common import AttributeDict
from aiida_pythonjob.launch import prepare_pythonjob_inputs
from aiida_pythonjob import PythonJob, spec
import numpy as np
from aiidalab_qe_pp.app.utils import resized_cube_files

PpCalculation = CalculationFactory("quantumespresso.pp")
Critic2Calculation = CalculationFactory("critic2")


def get_parameters(calc_type: str, settings: dict) -> orm.Dict:
    """Return the parameters based on the calculation type, with optional settings."""

    # Existing code with slight modifications for safe accessing
    calc_config = {
        "charge_dens": {
            "plot_num": 0,
            "extra_params": {
                "spin_component": settings.get("spin_component", 1),
            },
        },
        "spin_dens": {"plot_num": 6, "extra_params": {}},
        "wfn": {
            "plot_num": 7,
            "extra_params": {
                "kpoint(1)": settings.get(
                    "kpoint", 1
                ),  # Default values or handle appropriately
                "kband(1)": settings.get("kband(1)", 0),
                **(
                    {"kband(2)": settings["kband(2)"]} if "kband(2)" in settings else {}
                ),
            },
        },
        "stm": {
            "plot_num": 5,
            "extra_params": {
                "sample_bias": settings.get("sample_bias", 0.0)  # Default value
            },
        },
        "ildos": {
            "plot_num": 10,
            "extra_params": {
                "emin": settings.get("emin", -10),  # Reasonable default
                "emax": settings.get("emax", 10),
                "spin_component": settings.get("ildos_spin_component", 0),
            },
        },
        "potential": {
            "plot_num": 11,
        },
        "ldos_grid": {
            "plot_num": 3,
            "extra_params": {
                "emin": settings.get("emin", 0),
                "emax": settings.get("emax", 0),
                "delta_e": settings.get("delta_e", 0.1),
                "degauss_ldos": settings.get("degauss_ldos", 0.01),
                "use_gauss_ldos": settings.get("use_gauss_ldos", False),
            },
        },
    }

    config = calc_config.get(calc_type, {})
    parameters = {
        "INPUTPP": {
            "plot_num": config.get("plot_num"),
            **config.get("extra_params", {}),
        },
        "PLOT": {
            "iflag": 3,
        },
    }

    return orm.Dict(parameters)


def parse_stm_parameters(settings: dict) -> dict:
    """Parse the STM parameters from settings into list of parameters."""
    sample_bias_text = settings.get("sample_bias")
    heights_text = settings.get("heights")
    currents_text = settings.get("currents")

    try:
        sample_bias_list = text2floatlist(sample_bias_text)
        heights_list = text2floatlist(heights_text)
        currents_list = text2floatlist(currents_text)
    except ValueError:
        raise ValueError("Invalid STM parameters")

    # Change eV to Rydberg
    sample_bias_list = [-bias / 13.6056980659 for bias in sample_bias_list]

    return {
        "sample_bias": sample_bias_list,
        "heights": heights_list,
        "currents": currents_list,
    }


def text2floatlist(input_string):
    # Split the input string into substrings
    string_list = input_string.split()
    float_list = [float(num) for num in string_list]
    return float_list


def create_valid_link_label(value):
    """
    This function creates a valid link label in AiiDA by:

    1. Converting the value to a string (if necessary).
    2. Handling negative values by prepending "neg_".
    3. Replacing any non-alphanumeric characters with underscores.
    """
    if not isinstance(value, str):
        value = str(value)

    # Handle negative values
    prefix = ""
    if value.startswith("-"):
        prefix = "neg_"  # Prepend "neg_" for negative values
        value = value[1:]

    valid_label = prefix + value.replace(".", "_")
    valid_label = "".join(char for char in valid_label if char.isalnum() or char == "_")

    return valid_label


class PPWorkChain(WorkChain):
    "WorkChain to compute vibrational property of a crystal."

    label = "pp"

    @classmethod
    def define(cls, spec):
        """Define the process specification."""
        super().define(spec)
        spec.input(
            "structure",
            valid_type=orm.StructureData,
            required=False,
        )
        spec.input(
            "parent_folder",
            valid_type=(orm.RemoteData, orm.FolderData),
            required=True,
            help="Output folder of a completed `PwCalculation`",
        )
        spec.input(
            "properties",
            valid_type=orm.List,
            default=lambda: orm.List(),
            help="The properties to calculate, used to control the logic of PPWorkChain.",
        )
        spec.input(
            "parameters",
            valid_type=orm.Dict,
            required=False,
        )
        spec.expose_inputs(
            PpCalculation, namespace="pp_calc", exclude=["parent_folder", "parameters"]
        )
        spec.input("python", valid_type=orm.Code)
        spec.expose_inputs(
            Critic2Calculation,
            namespace="critic2_calc",
            exclude=["parent_folder", "parameters"],
        )
        spec.outline(
            if_(cls.should_run_charge_dens)(
                cls.run_charge_dens,
                cls.inspect_charge_dens,
                if_(cls.should_reduce_charge_dens)(
                    cls.reduce_charge_dens,
                ),
            ),
            if_(cls.should_run_spin_dens)(
                cls.run_spin_dens,
                cls.inspect_spin_dens,
                if_(cls.should_reduce_spin_dens)(
                    cls.reduce_spin_dens,
                ),
            ),
            if_(cls.should_run_potential)(
                cls.run_potential,
                cls.inspect_potential,
                if_(cls.should_reduce_potential)(
                    cls.reduce_potential,
                ),
            ),
            if_(cls.should_run_ldos_grid)(
                cls.run_ldos_grid,
                cls.inspect_ldos_grid,
                if_(cls.should_reduce_ldos_grid)(
                    cls.reduce_ldos_grid,
                ),
            ),
            if_(cls.should_run_wfn)(
                cls.run_wfn,
                cls.inspect_wfn,
                if_(cls.should_reduce_wfn)(
                    cls.reduce_wfn,
                ),
            ),
            if_(cls.should_run_ildos)(
                cls.run_ildos,
                cls.inspect_ildos,
                if_(cls.should_reduce_ildos)(
                    cls.reduce_ildos,
                ),
                if_(cls.should_run_ildos_stm)(
                    cls.run_ildos_stm,
                    cls.inspect_ildos_stm,
                ),
            ),
            if_(cls.should_run_stm)(
                cls.run_stm,
                cls.inspect_stm,
                cls.run_critic2,
                cls.inspect_critic2,
            ),
            cls.results,
        )

        # spec.output_namespace("charge_dens", dynamic=True)
        spec.expose_outputs(
            PpCalculation,
            namespace="charge_dens",
            namespace_options={
                "required": False,
                "help": "Charge Density `PpCalculation`.",
            },
        )
        spec.expose_outputs(
            PpCalculation,
            namespace="spin_dens",
            namespace_options={
                "required": False,
                "help": "Spin Density `PpCalculation`.",
            },
        )
        spec.expose_outputs(
            PpCalculation,
            namespace="potential",
            namespace_options={"required": False, "help": "Potential `PpCalculation`."},
        )
        spec.expose_outputs(
            PpCalculation,
            namespace="ildos",
            namespace_options={"required": False, "help": "ILDOS `PpCalculation`."},
        )
        spec.expose_outputs(
            PpCalculation,
            namespace="stm",
            namespace_options={"required": False, "help": "STM `PpCalculation`."},
        )
        spec.expose_outputs(
            PpCalculation,
            namespace="wfn",
            namespace_options={"required": False, "help": "WFN `PpCalculation`."},
        )
        spec.output_namespace("stm", dynamic=True)
        spec.output_namespace("wfn", dynamic=True)
        spec.output_namespace("ldos_grid", dynamic=True)
        spec.output_namespace("ildos_stm", dynamic=True)

        spec.exit_code(
            201,
            "ERROR_CHARGE_DENS_FAILED",
            message="The charge density calculation failed.",
        )
        spec.exit_code(
            202,
            "ERROR_SPIN_DENS_FAILED",
            message="The spin density calculation failed.",
        )
        spec.exit_code(
            203, "ERROR_WFN_FAILED", message="The wavefunction calculation failed."
        )
        spec.exit_code(
            204, "ERROR_ILDOS_FAILED", message="The ILDOS calculation failed."
        )
        spec.exit_code(205, "ERROR_STM_FAILED", message="The STM calculation failed.")
        spec.exit_code(
            206,
            "ERROR_SUB_PROCESS_FAILED",
            message="One (or more) of the sub processes failed.",
        )
        spec.exit_code(
            207, "ERROR_POTENTIAL_FAILED", message="The potential calculation failed."
        )
        spec.exit_code(
            208,
            "ERROR_LDOS_GRID_FAILED",
            message="The LDOS Grid calculation failed.",
        )

    @classmethod
    def get_builder_from_protocol(
        cls,
        parent_folder,
        pp_code,
        critic2_code,
        python,
        parameters,
        properties,
        protocol=None,
        options=None,
        structure=None,  # To remove once we update to new version!
        **kwargs,
    ):
        # if options:
        #    metadata['options'] = recursive_merge(inputs['pw']['metadata']['options'], options)

        """Return a builder pre-set with the protocol values."""
        builder = cls.get_builder()

        builder.parent_folder = parent_folder
        builder.properties = properties
        builder.pp_calc.code = pp_code
        builder.critic2_calc.code = critic2_code
        builder.python = python

        builder.critic2_calc.metadata.options = {
            "resources": {
                "num_machines": 1,
                "num_mpiprocs_per_machine": 1,
            },
            "max_wallclock_seconds": 10800,
            "withmpi": False,
        }

        builder.parameters = parameters
        builder.structure = structure

        return builder

    def submission_pp_calc(self, calc_type: str):
        """Submit a PP calculation based on the calculation type."""

        calc = f"{calc_type[5:]}"
        inputs = AttributeDict(self.exposed_inputs(PpCalculation, namespace="pp_calc"))
        inputs.parent_folder = self.inputs.parent_folder
        calc_parameters = (
            {} if calc in ["spin_dens", "potential"] else self.inputs.parameters[calc]
        )
        parameters = get_parameters(calc, calc_parameters)
        inputs.parameters = parameters
        if self.inputs.parameters["reduce_cube_files"]:
            inputs.metadata.options.parse_data_files = False
        running = self.submit(PpCalculation, **inputs)
        self.report(f"launching {calc_type} PpCalculation<{running.pk}>")
        return running

    def submission_pythonjob_calc(self, workchain):
        """Submit a PythonJob calculation based on the calculation type."""
        inputs = prepare_pythonjob_inputs(
            function=resized_cube_files,
            code=self.inputs.python,
            outputs_spec=spec.namespace(results=Any),
            parent_folder=workchain.outputs.remote_folder,
            computer=self.inputs.python.computer,
            register_pickle_by_value=True,
        )
        node = self.submit(PythonJob, **inputs)
        self.report(f"launching PythonJob<{node.pk}> to reduce cube files")
        return node

    def submit_critic2_calculation(self, remote_folder, calc_type, mode, value, label):
        inputs = AttributeDict(
            self.exposed_inputs(Critic2Calculation, namespace="critic2_calc")
        )
        inputs.parent_folder = remote_folder
        inputs.parameters = orm.Dict(dict={"mode": mode, "value": value})
        inputs.metadata.label = f"{calc_type}_{mode}_{label}"
        inputs.metadata.call_link_label = f"{calc_type}_{mode}_{label}"
        running = self.submit(Critic2Calculation, **inputs)
        self.report(
            f"Launching STM Critic2Calculation<{running.pk}> {calc_type}_{mode}_{label}"
        )
        self.to_context(**{f"{calc_type}_{mode}_{label}": running})

    def should_run_charge_dens(self):
        return "calc_charge_dens" in self.inputs.properties

    def run_charge_dens(self):
        """Submit a charge density calculation."""
        running = self.submission_pp_calc("calc_charge_dens")
        return ToContext(calc_charge_dens=running)

    def inspect_charge_dens(self):
        """Inspect the results of the charge density calculation."""
        calculation = self.ctx.calc_charge_dens

        if not calculation.is_finished_ok:
            self.report(
                f"Charge Density PpCalculation failed with exit status {calculation.exit_status}"
            )
            return self.exit_codes.ERROR_CHARGE_DENS_FAILED

    def should_reduce_charge_dens(self):
        return self.inputs.parameters.get("reduce_cube_files", False)

    def reduce_charge_dens(self):
        """Submit aiida pythonjob calculation"""
        workchain = self.ctx.calc_charge_dens
        node = self.submission_pythonjob_calc(workchain)
        return ToContext(reduce_calc_charge_dens=node)

    def should_run_spin_dens(self):
        return "calc_spin_dens" in self.inputs.properties

    def run_spin_dens(self):
        """Submit a spin density calculation."""
        running = self.submission_pp_calc("calc_spin_dens")
        return ToContext(calc_spin_dens=running)

    def inspect_spin_dens(self):
        """Inspect the results of the spin density calculation."""
        calculation = self.ctx.calc_spin_dens

        if not calculation.is_finished_ok:
            self.report(
                f"Spin Density PpCalculation failed with exit status {calculation.exit_status}"
            )
            return self.exit_codes.ERROR_SPIN_DENS_FAILED

    def should_reduce_spin_dens(self):
        return self.inputs.parameters.get("reduce_cube_files")

    def reduce_spin_dens(self):
        workchain = self.ctx.calc_spin_dens
        node = self.submission_pythonjob_calc(workchain)
        return ToContext(reduce_calc_spin_dens=node)

    def should_run_potential(self):
        return "calc_potential" in self.inputs.properties

    def run_potential(self):
        """Submit a potential calculation."""
        running = self.submission_pp_calc("calc_potential")
        return ToContext(calc_potential=running)

    def inspect_potential(self):
        """Inspect the results of the potential calculation."""
        calculation = self.ctx.calc_potential

        if not calculation.is_finished_ok:
            self.report(
                f"Potential PpCalculation failed with exit status {calculation.exit_status}"
            )
            return self.exit_codes.ERROR_POTENTIAL_FAILED

    def should_reduce_potential(self):
        return self.inputs.parameters.get("reduce_cube_files")

    def reduce_potential(self):
        workchain = self.ctx.calc_potential
        node = self.submission_pythonjob_calc(workchain)
        return ToContext(reduce_calc_potential=node)

    def should_run_ldos_grid(self):
        return "calc_ldos_grid" in self.inputs.properties

    def run_ldos_grid(self):
        """Submit a LDOS Grid calculation."""
        running = self.submission_pp_calc("calc_ldos_grid")
        return ToContext(calc_ldos_grid=running)

    def inspect_ldos_grid(self):
        """Inspect the results of the LDOS Grid calculation."""
        calculation = self.ctx.calc_ldos_grid

        if not calculation.is_finished_ok:
            self.report(
                f"LDOS Grid PpCalculation failed with exit status {calculation.exit_status}"
            )
            return self.exit_codes.ERROR_LDOS_GRID_FAILED

    def should_reduce_ldos_grid(self):
        return self.inputs.parameters.get("reduce_cube_files")

    def reduce_ldos_grid(self):
        workchain = self.ctx.calc_ldos_grid
        node = self.submission_pythonjob_calc(workchain)
        return ToContext(reduce_calc_ldos_grid=node)

    def should_run_wfn(self):
        return "calc_wfn" in self.inputs.properties

    def run_wfn(self):
        for band in self.inputs.parameters["wfn"]["orbitals"]:
            if "kband(2)" in band:
                label = f"kp_{band['kpoint']}_kb_{band['kband(1)']}_{band['kband(2)']}"
            else:
                label = f"kp_{band['kpoint']}_kb_{band['kband(1)']}"

            inputs = AttributeDict(
                self.exposed_inputs(PpCalculation, namespace="pp_calc")
            )
            inputs.parent_folder = self.inputs.parent_folder
            inputs.parameters = get_parameters("wfn", band)
            lsign = self.inputs.parameters["wfn"].get("lsign", False)
            number_of_k_points = self.inputs.parameters["wfn"].get(
                "number_of_k_points", 1
            )
            lsda = self.inputs.parameters["wfn"].get("lsda", False)
            if lsign and band["kpoint"] == 1:
                inputs.parameters["INPUTPP"]["lsign"] = True
            elif lsign and lsda and band["kpoint"] == number_of_k_points + 1:
                inputs.parameters["INPUTPP"]["lsign"] = True

            if self.inputs.parameters["reduce_cube_files"]:
                inputs.metadata.options.parse_data_files = False
            inputs.metadata.label = label
            inputs.metadata.call_link_label = label
            future = self.submit(PpCalculation, **inputs)
            self.report(
                f"launching Wavefunction `PpCalculation` <PK={future.pk}> for {label}"
            )
            self.to_context(**{label: future})

    def inspect_wfn(self):
        """Inspect the results of the wavefunction calculations"""
        failed_runs = []
        for label, workchain in self.ctx.items():
            if label.startswith("kp_"):
                if not workchain.is_finished_ok:
                    self.report(
                        f"Wavefunction PpCalculation {label} failed with exit status {workchain.exit_status}"
                    )
                    failed_runs.append(label)
        if failed_runs:
            self.report("one or more workchains did not finish succesfully")
            return self.exit_codes.ERROR_WFN_FAILED

    def should_reduce_wfn(self):
        return self.inputs.parameters.get("reduce_cube_files")

    def reduce_wfn(self):
        filtered_workchains = {
            label: workchain
            for label, workchain in self.ctx.items()
            if label.startswith("kp_")
        }

        for label, workchain in filtered_workchains.items():
            node = self.submission_pythonjob_calc(workchain)
            self.to_context(**{f"reduce_{label}": node})

    def should_run_ildos(self):
        return "calc_ildos" in self.inputs.properties

    def run_ildos(self):
        """Submit an ILDOS calculation."""
        running = self.submission_pp_calc("calc_ildos")
        return ToContext(calc_ildos=running)

    def inspect_ildos(self):
        """Inspect the results of the ILDOS calculation."""
        calculation = self.ctx.calc_ildos

        if not calculation.is_finished_ok:
            self.report(
                f"ILDOS PpCalculation failed with exit status {calculation.exit_status}"
            )
            return self.exit_codes.ERROR_ILDOS_FAILED

    def should_reduce_ildos(self):
        return self.inputs.parameters.get("reduce_cube_files")

    def reduce_ildos(self):
        workchain = self.ctx.calc_ildos
        node = self.submission_pythonjob_calc(workchain)
        return ToContext(reduce_calc_ildos=node)

    def should_run_ildos_stm(self):
        return "calc_ildos_stm" in self.inputs.properties

    def run_ildos_stm(self):
        ildos_stm = self.inputs.parameters["ildos_stm"]
        stm_parameters = parse_stm_parameters(ildos_stm)

        remote_folder = self.ctx.calc_ildos.outputs.remote_folder
        if stm_parameters["heights"]:
            for height in stm_parameters.get("heights", []):
                height_label = str(height).replace(".", "_")
                z_axis = self.inputs.structure.cell_lengths[2]
                self.submit_critic2_calculation(
                    remote_folder, "ildos_stm", "height", height / z_axis, height_label
                )
        if stm_parameters["currents"]:
            for current in stm_parameters.get("currents", []):
                current_label = create_valid_link_label(current)
                self.submit_critic2_calculation(
                    remote_folder, "ildos_stm", "current", current, current_label
                )

    def inspect_ildos_stm(self):
        """Inspect the results of the ILDOS STM calculations."""
        failed_runs = []
        for label, workchain in self.ctx.items():
            if label.startswith("ildos_stm"):
                if not workchain.is_finished_ok:
                    self.report(
                        f"ILDOS STM Critic2Calculation {label} failed with exit status {workchain.exit_status}"
                    )
                    failed_runs.append(label)
        if failed_runs:
            self.report("one or more workchains did not finish succesfully")
            return self.exit_codes.ERROR_STM_FAILED

    def should_run_stm(self):
        return "calc_stm" in self.inputs.properties

    def run_stm(self):
        stm_parameters = parse_stm_parameters(self.inputs.parameters["stm"])

        for bias_index, bias in enumerate(stm_parameters["sample_bias"]):
            inputs = AttributeDict(
                self.exposed_inputs(PpCalculation, namespace="pp_calc")
            )
            inputs.parent_folder = self.inputs.parent_folder
            inputs.parameters = get_parameters("stm", {"sample_bias": bias})
            bias_ev = text2floatlist(self.inputs.parameters["stm"]["sample_bias"])[
                bias_index
            ]
            bias_label = create_valid_link_label(bias_ev)
            inputs.metadata.label = f"bias_{bias_label}"
            inputs.metadata.call_link_label = f"bias_{bias_label}"
            inputs.metadata.options.parse_data_files = False
            running = self.submit(PpCalculation, **inputs)
            self.report(f"launching STM PpCalculation<{running.pk}> bias_{bias_label}")
            self.to_context(**{f"bias_{bias_label}": running})

    def inspect_stm(self):
        """Inspect the results of the STM calculations."""
        failed_runs = []
        for label, workchain in self.ctx.items():
            if label.startswith("bias_"):
                if not workchain.is_finished_ok:
                    self.report(
                        f"Wavefunction PpCalculation {label} failed with exit status {workchain.exit_status}"
                    )
                    failed_runs.append(label)
        if failed_runs:
            self.report("one or more workchains did not finish succesfully")
            return self.exit_codes.ERROR_STM_FAILED

    def run_critic2(self):
        stm_parameters = parse_stm_parameters(self.inputs.parameters["stm"])

        for bias_index, bias in enumerate(stm_parameters["sample_bias"]):
            bias_ev = text2floatlist(self.inputs.parameters["stm"]["sample_bias"])[
                bias_index
            ]
            bias_label = create_valid_link_label(bias_ev)

            if stm_parameters["heights"]:
                for height_index, height in enumerate(stm_parameters["heights"]):
                    z_axis = self.inputs.structure.cell_lengths[2]
                    height_critic = height / z_axis

                    # for labeling with . in the name
                    height_label = str(height).replace(".", "_")

                    inputs = AttributeDict(
                        self.exposed_inputs(
                            Critic2Calculation, namespace="critic2_calc"
                        )
                    )
                    inputs.parent_folder = self.ctx[
                        f"bias_{bias_label}"
                    ].outputs.remote_folder
                    parameters = orm.Dict(
                        dict={"mode": "height", "value": height_critic}
                    )
                    inputs.parameters = parameters
                    inputs.metadata.label = (
                        f"stm_bias_{bias_label}_height_{height_label}"
                    )
                    inputs.metadata.call_link_label = (
                        f"stm_bias_{bias_label}_height_{height_label}"
                    )
                    running = self.submit(Critic2Calculation, **inputs)
                    self.report(
                        f"launching STM Critic2Calculation<{running.pk}> stm_bias_{bias_label}_height_{height_label}"
                    )
                    self.to_context(
                        **{f"stm_bias_{bias_label}_height_{height_label}": running}
                    )

            if stm_parameters["currents"]:
                for current_index, current in enumerate(stm_parameters["currents"]):
                    current_pA = text2floatlist(
                        self.inputs.parameters["stm"]["currents"]
                    )[current_index]

                    # for labeling with . in the name
                    current_label = create_valid_link_label(current_pA)

                    inputs = AttributeDict(
                        self.exposed_inputs(
                            Critic2Calculation, namespace="critic2_calc"
                        )
                    )
                    inputs.parent_folder = self.ctx[
                        f"bias_{bias_label}"
                    ].outputs.remote_folder
                    parameters = orm.Dict(dict={"mode": "current", "value": current})
                    inputs.parameters = parameters
                    inputs.metadata.label = (
                        f"stm_bias_{bias_label}_current_{current_label}"
                    )
                    inputs.metadata.call_link_label = (
                        f"stm_bias_{bias_label}_current_{current_label}"
                    )
                    running = self.submit(Critic2Calculation, **inputs)
                    self.report(
                        f"launching STM Critic2Calculation<{running.pk}> stm_bias_{bias_label}_current_{current_label}"
                    )
                    self.to_context(
                        **{f"stm_bias_{bias_label}_current_{current_label}": running}
                    )

    def inspect_critic2(self):
        """Inspect the results of the STM calculations."""
        failed_runs = []
        for label, workchain in self.ctx.items():
            if label.startswith("stm_"):
                if not workchain.is_finished_ok:
                    self.report(
                        f"STM Critic2Calculation {label} failed with exit status {workchain.exit_status}"
                    )
                    failed_runs.append(label)
        if failed_runs:
            self.report("one or more workchains did not finish succesfully")
            return self.exit_codes.ERROR_STM_FAILED

    def results(self):
        """Attach the results of the PPWorkChain to the outputs."""
        failed = False
        for prop in self.inputs.properties:
            if prop not in ["calc_wfn", "calc_stm", "calc_ldos_grid", "calc_ildos_stm"]:
                if self.ctx[f"{prop}"].is_finished_ok:
                    if self.inputs.parameters.get("reduce_cube_files"):
                        volumetric_data = self.ctx[
                            f"reduce_{prop}"
                        ].outputs.results.get("aiida_fileout")
                        array = orm.ArrayData()
                        array.set_array("data", np.array(volumetric_data))
                        array.store()
                        output = {}
                        output["output_data"] = array
                        output["remote_folder"] = self.ctx[
                            f"{prop}"
                        ].outputs.remote_folder
                        output["retrieved"] = self.ctx[f"{prop}"].outputs.retrieved
                        output["output_parameters"] = self.ctx[
                            f"{prop}"
                        ].outputs.output_parameters
                        self.out(f"{prop[5:]}", output)
                    else:
                        self.out_many(
                            self.exposed_outputs(
                                self.ctx[f"{prop}"],
                                PpCalculation,
                                namespace=f"{prop[5:]}",
                            )
                        )
                else:
                    self.report(f"{prop[5:]} calculation failed")
                    failed = True

            elif prop == "calc_ldos_grid":
                if self.ctx.calc_ldos_grid.is_finished_ok:
                    if self.inputs.parameters.get("reduce_cube_files"):
                        volumetric_data = self.ctx[
                            "reduce_calc_ldos_grid"
                        ].outputs.results

                        if "aiida_fileout" in volumetric_data:
                            array = orm.ArrayData()
                            array.set_array(
                                "data", np.array(volumetric_data["aiida_fileout"])
                            )
                            array.store()
                            output = {}
                            output["output_data"] = array
                            output["remote_folder"] = (
                                self.ctx.calc_ldos_grid.outputs.remote_folder
                            )
                            output["retrieved"] = (
                                self.ctx.calc_ldos_grid.outputs.retrieved
                            )
                            output["output_parameters"] = (
                                self.ctx.calc_ldos_grid.outputs.output_parameters
                            )
                            self.out("ldos_grid", output)

                        else:
                            output = {}
                            output["output_data_multiple"] = {}
                            output["retrieved"] = (
                                self.ctx.calc_ldos_grid.outputs.retrieved
                            )
                            output["output_parameters"] = (
                                self.ctx.calc_ldos_grid.outputs.output_parameters
                            )
                            output["remote_folder"] = (
                                self.ctx.calc_ldos_grid.outputs.remote_folder
                            )
                            for key, value in volumetric_data.items():
                                array = orm.ArrayData()
                                array.set_array("data", np.array(value))
                                array.store()
                                output["output_data_multiple"][key] = array

                            self.out("ldos_grid", output)
                    else:
                        self.out("ldos_grid", self.ctx.calc_ldos_grid.outputs)
                else:
                    self.report("LDOS Grid calculation failed")
                    failed = True

            elif prop == "calc_wfn":
                wfn_found = False
                wfn_outputs = {}

                for label, workchain in self.ctx.items():
                    if self.inputs.parameters.get("reduce_cube_files"):
                        if label.startswith("reduce_kp_"):
                            wfn_found = True
                            ref_label = label.split("reduce_")[1]
                            ref_work = self.ctx[ref_label]
                            volumetric_data = self.ctx[label].outputs.results

                            if "aiida_fileout" in volumetric_data:
                                array = orm.ArrayData()
                                array.set_array(
                                    "data", np.array(volumetric_data["aiida_fileout"])
                                )
                                array.store()
                                output = {}
                                output["output_data"] = array
                                output["remote_folder"] = ref_work.outputs.remote_folder
                                wfn_outputs[ref_label] = output
                            else:
                                output = {}
                                output["output_data_multiple"] = {}

                                output["remote_folder"] = ref_work.outputs.remote_folder
                                for key, value in volumetric_data.items():
                                    array = orm.ArrayData()
                                    array.set_array("data", np.array(value))
                                    array.store()
                                    output["output_data_multiple"][key] = array
                                wfn_outputs[ref_label] = output

                    else:
                        if label.startswith("kp_"):
                            wfn_found = True
                            if workchain.is_finished_ok:
                                wfn_outputs[label] = {}
                                process = getattr(self.ctx, label)
                                for key in process.outputs._get_keys():
                                    wfn_outputs[label][key] = getattr(
                                        process.outputs, key
                                    )
                            else:
                                self.report(f"{label} calculation failed")
                                failed = True

                self.out("wfn", wfn_outputs)

                if not wfn_found:
                    self.report(
                        "No workchains found for 'calc_wfn' with labels starting with 'wfn_'"
                    )

            elif prop in ("calc_stm", "calc_ildos_stm"):
                output_label = prop[5:]  # Removes "calc_" prefix
                prefix = f"{output_label}_"  # Prefix for filtering workchains

                found = False
                outputs = {}

                for label, workchain in self.ctx.items():
                    if label.startswith(prefix):
                        found = True
                        if workchain.is_finished_ok:
                            outputs[label] = {
                                key: getattr(workchain.outputs, key)
                                for key in workchain.outputs._get_keys()
                            }
                        else:
                            self.report(f"{label} calculation failed")
                            failed = True

                self.out(output_label, outputs)

                if not found:
                    self.report(
                        f"No workchains found for '{prop}' with labels starting with '{prefix}'"
                    )

        if failed:
            return self.exit_codes.ERROR_SUB_PROCESS_FAILED
        else:
            self.report("PPWorkChain completed successfully")
