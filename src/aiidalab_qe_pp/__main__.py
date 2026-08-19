from aiida.common.exceptions import NotExistent
import subprocess
from aiida.orm import load_code
from aiida import load_profile
import click
from pathlib import Path
import shutil
import os

"""
Automatic installation of Python code for python3@localhost.

Since Critic2 must be installed, we need to verify we have
gfortran and cmake. If not, we need to install them.
And then we install Critic2.

"""

# Define the default path for critic2 installation
CRITIC_PATH_DEFAULT = Path("/home/jovyan")
critic2_dir = CRITIC_PATH_DEFAULT / "critic2"
critic_executable = critic2_dir / "build" / "src" / "critic2"


@click.group()
def cli():
    pass


@cli.command(help="Setup all executables and aiida codes in one go.")
def post_install():
    click.echo("Starting full installation...")

    click.echo("Setting up python3@localhost...")
    load_profile()
    try:
        load_code("python3@localhost")
    except NotExistent:
        # Use shutil.which to find the path of the phonopy executable
        python_path = shutil.which("python3")
        if not python_path:
            raise FileNotFoundError("python3 code is not found in PATH")
        # Construct the command as a list of arguments
        command = [
            "verdi",
            "code",
            "create",
            "core.code.installed",
            "--non-interactive",
            "--label",
            "python3",
            "--default-calc-job-plugin",
            "pythonjob.pythonjob",
            "--computer",
            "localhost",
            "--filepath-executable",
            python_path,
        ]

        # Use subprocess.run to run the command
        subprocess.run(command, check=True)
    else:
        print("Code python3@localhost is already installed! Nothing to do here.")

    click.echo("Setting up gfortran...")
    try:
        subprocess.run(["gfortran", "--version"], stdout=subprocess.PIPE, check=True)
    except FileNotFoundError:
        # Installing fortran via mamba
        subprocess.run(["mamba", "install", "gfortran", "-y"], check=True)
    else:
        print("gfortran is already installed! Nothing to do here.")

    click.echo("Setting up cmake...")
    try:
        subprocess.run(["cmake", "--version"], stdout=subprocess.PIPE, check=True)
    except FileNotFoundError:
        # Installing cmake via mamba
        subprocess.run(["mamba", "install", "cmake", "-y"], check=True)
    else:
        print("cmake is already installed! Nothing to do here.")

    click.echo("Setting up critic2...")
    if critic_executable.exists():
        print("Critic2 is already installed! Nothing to do here.")
    else:
        # Install critic2 in path from Repo git clone https://github.com/aoterodelaroza/critic2.git
        repo_url = "https://github.com/aoterodelaroza/critic2.git"
        try:
            subprocess.run(
                ["git", "clone", repo_url, str(CRITIC_PATH_DEFAULT / "critic2")],
                check=True,
            )
            print("Repository cloned successfully.")
        except subprocess.CalledProcessError as e:
            print(f"Error cloning the repository: {e}")

        # Create the build directory
        build_dir = critic2_dir / "build"
        build_dir.mkdir(parents=True, exist_ok=True)
        try:
            print("Running cmake and make to build critic2...")
            subprocess.run(["cmake", ".."], cwd=build_dir, check=True)
            subprocess.run(
                ["make", f"-j{os.cpu_count() or 1}"], cwd=build_dir, check=True
            )
            print("Critic2 installation complete!")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error during the installation process: {e}")

    click.echo("Setting up aiida critic2 code...")
    load_profile()
    try:
        load_code("critic2@localhost")
    except NotExistent:
        # Use shutil.which to find the path of the critic2 executable
        critic_path = str(critic_executable)

        # Construct the command as a list of arguments
        command = [
            "verdi",
            "code",
            "create",
            "core.code.installed",
            "--non-interactive",
            "--label",
            "critic2",
            "--default-calc-job-plugin",
            "critic2",
            "--computer",
            "localhost",
            "--filepath-executable",
            critic_path,
        ]

        # Use subprocess.run to run the command
        subprocess.run(command, check=True)
    else:
        print("Code critic2@localhost is already installed! Nothing to do here.")


if __name__ == "__main__":
    cli()
