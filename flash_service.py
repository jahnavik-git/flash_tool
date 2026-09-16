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


class ConcreteFlashProgrammer(SimulationFlashProgrammer):
    def __init__(self, driver=None):
        self.driver = driver

    def flash(self, file_path: str, source_address: int, destination_address: int):
        if self.driver is not None:
            return self.driver.flash(file_path, source_address, destination_address)
        return super().flash(file_path, source_address, destination_address)


def flash_firmware(
    ssbl_file,
    application_file,
    ssbl_source,
    ssbl_destination,
    application_source,
    application_destination,
):
    programmer = ConcreteFlashProgrammer()

    ssbl_result = programmer.flash(ssbl_file, ssbl_source, ssbl_destination)
    application_result = programmer.flash(application_file, application_source, application_destination)

    return {
        "status": "success",
        "mode": "Simulation Mode",
        "details": {
            "ssbl": ssbl_result,
            "application": application_result,
        },
        "message": "Flash completed successfully in Simulation Mode.",
    }
