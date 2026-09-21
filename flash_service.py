import os
from abc import ABC, abstractmethod


class FlashProgrammer(ABC):
    @abstractmethod
    def flash(self, file_path: str, source_address: int, destination_address: int):
        pass


class SimulationFlashProgrammer(FlashProgrammer):
    def flash(self, file_path: str, source_address: int, destination_address: int):
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError("Firmware file does not exist.")

        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            raise ValueError("Firmware file is empty.")

        return {
            "mode": "Simulation Mode",
            "message": "Simulation mode is active. No hardware was programmed.",
            "source_address": source_address,
            "destination_address": destination_address,
            "file_size": file_size,
        }


class ConcreteFlashProgrammer(FlashProgrammer):
    def __init__(self, driver=None):
        self.driver = driver

    def flash(self, file_path: str, source_address: int, destination_address: int):
        if self.driver is None:
            raise ValueError(
                "No programmer hardware detected. Connect a J-Link/ST-LINK/OpenOCD programmer and try again."
            )
        return self.driver.flash(file_path, source_address, destination_address)


def flash_firmware(core_config):
    """Flash the firmware described by core_config, synchronously, in one call.

    core_config shape:
        {
          "core0": {
            "ssbl": {"file", "start_address", "end_address"},
            "application": {"file", "start_address", "end_address"},
          },
          "core1": {
            "application": {"file", "start_address", "end_address"},
          },
        }

    Runs to completion within a single request/response (no background thread,
    no in-memory job store) so it works on stateless serverless platforms.
    Always returns a result dict rather than raising, recording the stage and
    percent reached so the caller can still show where a failure happened.
    """

    programmer = ConcreteFlashProgrammer()
    results = {"core0": {}, "core1": {}}

    core0 = core_config.get("core0", {})
    core1 = core_config.get("core1", {})

    stage, percent = "Preparing", 0
    try:
        stage, percent = "Connecting to J-Link", 10
        stage, percent = "Erasing", 20

        ssbl = core0.get("ssbl")
        if ssbl:
            stage, percent = "Flashing Core 0 SSBL", 35
            results["core0"]["ssbl"] = programmer.flash(ssbl["file"], ssbl["start_address"], ssbl["end_address"])
            stage, percent = "Verifying Core 0 SSBL", 45

        core0_application = core0.get("application")
        if core0_application:
            stage, percent = "Flashing Core 0 Application", 60
            results["core0"]["application"] = programmer.flash(
                core0_application["file"], core0_application["start_address"], core0_application["end_address"]
            )
            stage, percent = "Verifying Core 0 Application", 70

        core1_application = core1.get("application")
        if core1_application:
            stage, percent = "Flashing Core 1 Application", 85
            results["core1"]["application"] = programmer.flash(
                core1_application["file"], core1_application["start_address"], core1_application["end_address"]
            )
            stage, percent = "Verifying Core 1 Application", 95

        stage, percent = "Completed", 100

        return {
            "status": "success",
            "stage": stage,
            "percent": percent,
            "mode": "Hardware Mode",
            "details": results,
            "message": "Flash completed successfully.",
        }
    except Exception as exc:
        return {
            "status": "failed",
            "stage": stage,
            "percent": percent,
            "error": str(exc),
        }
