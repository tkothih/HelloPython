#!/usr/bin/env python3
import hashlib
import json
import logging
import os
import re
import subprocess  # nosec
import sys
import tempfile
import venv
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import List, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("build")


this_dir = Path(__file__).parent
this_file = Path(__file__).name
package_manager = "poetry>=1.6.1"


class Runnable(ABC):
    @abstractmethod
    def run(self) -> int:
        """Run stage"""

    @abstractmethod
    def get_name(self) -> str:
        """Get stage name"""

    @abstractmethod
    def get_inputs(self) -> List[Path]:
        """Get stage dependencies"""

    @abstractmethod
    def get_outputs(self) -> List[Path]:
        """Get stage outputs"""


class RunInfoStatus(Enum):
    MATCH = (False, "Nothing changed. Previous execution info matches.")
    NO_INFO = (True, "No previous execution info found.")
    FILE_NOT_FOUND = (True, "File not found.")
    FILE_CHANGED = (True, "File has changed.")

    def __init__(self, should_run: bool, message: str) -> None:
        self.should_run = should_run
        self.message = message


class Executor:
    """Accepts Runnable objects and executes them.
    It create a file with the same name as the runnable's name
    and stores the inputs and outputs with their hashes.
    If the file exists, it checks the hashes of the inputs and outputs
    and if they match, it skips the execution."""

    RUN_INFO_FILE_EXTENSION = ".deps.json"

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir

    @staticmethod
    def get_file_hash(path: Path) -> str:
        with open(path, "rb") as file:
            bytes = file.read()
            readable_hash = hashlib.sha256(bytes).hexdigest()
            return readable_hash

    def store_run_info(self, runnable: Runnable) -> None:
        file_info = {
            "inputs": {
                str(path): self.get_file_hash(path) for path in runnable.get_inputs()
            },
            "outputs": {
                str(path): self.get_file_hash(path) for path in runnable.get_outputs()
            },
        }

        run_info_path = self.get_runnable_run_info_file(runnable)
        run_info_path.parent.mkdir(parents=True, exist_ok=True)
        with run_info_path.open("w") as f:
            # pretty print the json file
            json.dump(file_info, f, indent=4)

    def get_runnable_run_info_file(self, runnable: Runnable) -> Path:
        return self.cache_dir / f"{runnable.get_name()}{self.RUN_INFO_FILE_EXTENSION}"

    def previous_run_info_matches(self, runnable: Runnable) -> RunInfoStatus:
        run_info_path = self.get_runnable_run_info_file(runnable)
        if not run_info_path.exists():
            return RunInfoStatus.NO_INFO

        with run_info_path.open() as f:
            previous_info = json.load(f)

        for file_type in ["inputs", "outputs"]:
            for path_str, previous_hash in previous_info[file_type].items():
                path = Path(path_str)
                if not path.exists():
                    return RunInfoStatus.FILE_NOT_FOUND
                elif self.get_file_hash(path) != previous_hash:
                    return RunInfoStatus.FILE_CHANGED
        return RunInfoStatus.MATCH

    def execute(self, runnable: Runnable) -> int:
        run_info_status = self.previous_run_info_matches(runnable)
        if run_info_status.should_run:
            logger.info(
                f"Runnable '{runnable.get_name()}' must run. {run_info_status.message}"
            )
            exit_code = runnable.run()
            self.store_run_info(runnable)
            return exit_code
        logger.info(
            f"Runnable '{runnable.get_name()}' execution skipped. {run_info_status.message}"
        )

        return 0


class UserNotificationException(Exception):
    pass


class SubprocessExecutor:
    def __init__(
        self,
        command: List[str | Path],
        cwd: Optional[Path] = None,
        capture_output: bool = True,
    ):
        self.command = " ".join([str(cmd) for cmd in command])
        self.current_working_directory = cwd
        self.capture_output = capture_output

    def execute(self) -> None:
        result = None
        try:
            current_dir = (self.current_working_directory or Path.cwd()).as_posix()
            logger.info(f"Running command: {self.command} in {current_dir}")
            # print all virtual environment variables
            logger.debug(json.dumps(dict(os.environ), indent=4))
            result = subprocess.run(
                self.command.split(),
                cwd=current_dir,
                capture_output=self.capture_output,
                text=True,  # to get stdout and stderr as strings instead of bytes
            )  # nosec
            result.check_returncode()
        except subprocess.CalledProcessError as e:
            raise UserNotificationException(
                f"Command '{self.command}' failed with:\n"
                f"{result.stdout if result else ''}\n"
                f"{result.stderr if result else e}"
            )


class VirtualEnvironment(ABC):
    def __init__(self, venv_dir: Path) -> None:
        self.venv_dir = venv_dir

    def create(self, clear: bool = False) -> None:
        """
        Create a new virtual environment. This should configure the virtual environment such that
        subsequent calls to `pip` and `run` operate within this environment.
        """
        try:
            venv.create(self.venv_dir, with_pip=True, clear=clear)
        except PermissionError as e:
            if "python.exe" in str(e):
                raise UserNotificationException(
                    f"Failed to create virtual environment in {self.venv_dir}.\n"
                    f"Virtual environment python.exe is still running. Please kill all instances and run again.\n"
                    f"Error: {e}"
                )
            raise UserNotificationException(
                f"Failed to create virtual environment in {self.venv_dir}.\n"
                f"Please make sure you have the necessary permissions.\n"
                f"Error: {e}"
            )

    def pip(self, args: List[str]) -> None:
        """
        Execute a pip command within the virtual environment. This method should behave as if the
        user had activated the virtual environment and run `pip` from the command line.

        Args:
            *args: Command-line arguments to pip. For example, `pip('install', 'requests')` should
                   behave similarly to `pip install requests` at the command line.
        """

    def run(self, args: List[str], capture_output: bool = True) -> None:
        """
        Run an arbitrary command within the virtual environment. This method should behave as if the
        user had activated the virtual environment and run the given command from the command line.

        Args:
            *args: Command-line arguments. For example, `run('python', 'setup.py', 'install')`
                   should behave similarly to `python setup.py install` at the command line.
        """


class WindowsVirtualEnvironment(VirtualEnvironment):
    def __init__(self, venv_dir: Path) -> None:
        super().__init__(venv_dir)
        self.activate_script = self.venv_dir.joinpath("Scripts/activate")

    def pip(self, args: List[str]) -> None:
        pip_path = self.venv_dir.joinpath("Scripts/pip").as_posix()
        SubprocessExecutor([pip_path, *args], this_dir).execute()

    def run(self, args: List[str], capture_output: bool = True) -> None:
        SubprocessExecutor(
            [f"cmd /c {self.activate_script.as_posix()} && ", *args],
            this_dir,
            capture_output,
        ).execute()


class UnixVirtualEnvironment(VirtualEnvironment):
    def __init__(self, venv_dir: Path) -> None:
        super().__init__(venv_dir)
        self.activate_script = self.venv_dir.joinpath("bin/activate")

    def pip(self, args: List[str]) -> None:
        pip_path = self.venv_dir.joinpath("bin/pip").as_posix()
        SubprocessExecutor([pip_path, *args]).execute()

    def run(self, args: List[str], capture_output: bool = True) -> None:
        # Create a temporary shell script
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".sh") as f:
            f.write("#!/bin/bash\n")  # Add a shebang line
            f.write(
                f"source {self.activate_script.as_posix()}\n"
            )  # Write the activate command
            f.write(" ".join(args))  # Write the provided command
            temp_script_path = f.name  # Get the path of the temporary script

        # Make the temporary script executable
        SubprocessExecutor(["chmod", "+x", temp_script_path]).execute()
        # Run the temporary script
        SubprocessExecutor(
            [f"{Path(temp_script_path).as_posix()}"], this_dir, capture_output
        ).execute()
        # Delete the temporary script
        os.remove(temp_script_path)


class CreateVirtualEnvironment(Runnable):
    def __init__(
        self,
    ) -> None:
        self.root_dir = this_dir
        self.venv_dir = self.root_dir / ".venv"
        self.virtual_env = self.instantiate_os_specific_venv()

    @property
    def package_manager_name(self) -> str:
        match = re.match(r"^([a-zA-Z0-9_-]+)", package_manager)

        if match:
            return match.group(1)
        else:
            raise UserNotificationException(
                f"Could not extract the package manager name from {package_manager}"
            )

    def run(self) -> int:
        logger.info("Running project build script")
        self.virtual_env.create(clear=self.venv_dir.exists())
        self.virtual_env.pip(["install", package_manager])
        self.virtual_env.run([self.package_manager_name, "install"])
        return 0

    def instantiate_os_specific_venv(self) -> VirtualEnvironment:
        if sys.platform.startswith("win32"):
            return WindowsVirtualEnvironment(self.venv_dir)
        elif sys.platform.startswith("linux") or sys.platform.startswith("darwin"):
            return UnixVirtualEnvironment(self.venv_dir)
        else:
            raise UserNotificationException(
                f"Unsupported operating system: {sys.platform}"
            )

    def get_name(self) -> str:
        return "create-virtual-environment"

    def get_inputs(self) -> List[Path]:
        return [
            self.root_dir / file
            for file in ["poetry.lock", "poetry.toml", "pyproject.toml", this_file]
        ]

    def get_outputs(self) -> List[Path]:
        return []


def print_environment_info() -> None:
    str_bar = "".join(["-" for _ in range(80)])
    logger.debug(str_bar)
    logger.debug("Environment: \n" + json.dumps(dict(os.environ), indent=4))
    logger.info(str_bar)
    logger.info(f"Arguments: {sys.argv[1:]}")
    logger.info(str_bar)


def main() -> int:
    try:
        # print_environment_info()
        build = CreateVirtualEnvironment()
        Executor(build.venv_dir).execute(build)
        # In case there is a yanga.yml file and the script was called with arguments,
        # run 'yanga build' with all input arguments
        args = sys.argv[1:]
        if this_dir.joinpath("yanga.yaml").exists() and len(args) > 0:
            build.virtual_env.run(["yanga", "build"] + args, False)
    except UserNotificationException as e:
        logger.error(e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

if __name__ == "__test_main__":
    """This is used to execute the build script from a test and
    it shall not call sys.exit()"""
    main()
