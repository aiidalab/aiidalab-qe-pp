"""AiiDAlab QE plugin for post-processing (PP)."""

from aiidalab_qe.plugins import QeAppPlugin


class PpPlugin(QeAppPlugin):
    @property
    def outline(self) -> str:
        return "Post-processing (PP)"

    def configuration(self):
        from aiidalab_qe_pp.app.model import PpConfigurationSettingsModel
        from aiidalab_qe_pp.app.setting import PpConfigurationSettingPanel

        return {
            "panel": PpConfigurationSettingPanel,
            "model": PpConfigurationSettingsModel,
        }

    def resources(self):
        from aiidalab_qe_pp.app.code import (
            PpResourceSettingsModel,
            PpResourceSettingsPanel,
        )

        return {
            "panel": PpResourceSettingsPanel,
            "model": PpResourceSettingsModel,
        }

    def result(self):
        from aiidalab_qe_pp.app.result.model import PpResultsModel
        from aiidalab_qe_pp.app.result.result import PpResultsPanel

        return {
            "panel": PpResultsPanel,
            "model": PpResultsModel,
        }

    def workchain(self):
        from aiidalab_qe_pp.app.workchain import workchain_and_builder

        return workchain_and_builder
