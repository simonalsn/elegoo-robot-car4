set shell := ["bash", "-c"]

elegoo_software_url := "https://download.elegoo.com/02%20Robot%20Car%20Kits/02%20Smart%20Robot%20Car%20V4/ELEGOO%20Smart%20Robot%20Car%20Kit%20V4.0%202023.02.01.zip"
# Handle the %20 replacement by hardcoding the expected clean filename
elegoo_zip_file := "ELEGOO Smart Robot Car Kit V4.0 2023.02.01.zip"
elegoo_software_dir := "ELEGOO Smart Robot Car Kit V4.0 2023.02.01"

elegoo_path_to_main_code := elegoo_software_dir / "02 Manual & Main Code & APP/02 Main Program   (Arduino UNO)/TB6612 & MPU6050/SmartRobotCarV4.0_V1_20230201"
elegoo_path_to_camera_code := elegoo_software_dir / "02 Manual & Main Code & APP/04 Code of Carmer (ESP32)/ESP32-WROVER-Camera/ESP32_CameraServer_AP_20220120"

# Main targets

help:
    @echo
    @echo "Welcome to the configuration of the elegoo-robot-car4 project."
    @echo
    @echo "If you already have the '{{elegoo_zip_file}}' file,"
    @echo "then place it into the root of the project: this avoids some targets"
    @echo "to download it."
    @echo "Here below there is a brief explanation of the main targets."
    @echo "Explore the justfile for viewing all the possible targets."
    @echo
    @just --list

# TARGETS FOR BOARDS SOFTWARE
# ===========================

# Prepares the original ELEGOO software
get-elegoo-software:
    @if [ ! -e "{{elegoo_zip_file}}" ]; then \
        echo "Downloading ELEGOO software..."; \
        wget "{{elegoo_software_url}}" -O "{{elegoo_zip_file}}"; \
    fi
    @if [ ! -d "{{elegoo_software_dir}}" ]; then \
        unzip "{{elegoo_zip_file}}"; \
    fi

# Patches the software for the main board
main-patch: get-elegoo-software
    patch -d "{{elegoo_path_to_main_code}}" < elegoo-patches/tb6612_mpu6050.patch

# Reverts patching to the software for the main board
main-unpatch: get-elegoo-software
    patch -Rd "{{elegoo_path_to_main_code}}" < elegoo-patches/tb6612_mpu6050.patch

# Patches camera software in access-point (AP) mode
camera-patch: get-elegoo-software
    patch -d "{{elegoo_path_to_camera_code}}" < elegoo-patches/esp32.patch

# Reverts patcing to the camera software in access-point (AP) mode
camera-unpatch: get-elegoo-software
    patch -Rd "{{elegoo_path_to_camera_code}}" < elegoo-patches/esp32.patch

# Patches camera software so that it can connect to a router
camera-to-router-patch: get-elegoo-software
    patch -d "{{elegoo_path_to_camera_code}}" < elegoo-patches/esp32-with-conn-to-router.patch

# Reverts patching to camera software for the connection to router case
camera-to-router-unpatch: get-elegoo-software
    patch -Rd "{{elegoo_path_to_camera_code}}" < elegoo-patches/esp32-with-conn-to-router.patch

# get the official ELEGOO software and patches it so that the robot connects to a router.
config: main-patch camera-to-router-patch
    @echo -n "Network SSID: "; \
    read SSID; \
    echo -n "Password: "; \
    read PASSWORD; \
    sed -e "s/\[ROUTER_SSID\]/${SSID}/" \
        -e "s/\[ROUTER_PASSWORD\]/${PASSWORD}/" \
        "{{elegoo_path_to_camera_code}}/CameraWebServer_AP.h.source" > \
        "{{elegoo_path_to_camera_code}}/CameraWebServer_AP.h"

# similar to config, but keeps the robot in access-point (AP) mode.
config-ap: main-patch camera-patch

# removes the ELEGOO software directory. It does not erase the ELEGOO software zip file.
reset-elegoo:
    rm -fr "{{elegoo_software_dir}}"

# removes any downloaded, patched or generated file.
clean-elegoo: reset-elegoo
    rm -fr "{{elegoo_zip_file}}"

# TARGETS FOR PYTHON SOFTWARE
# ===========================

# Checks if uv is installed.
check-uv:
    @if [ -z $(which uv) ]; then \
        echo "uv could not be found. Install it first: https://docs.astral.sh/uv/getting-started/installation/"; \
        exit 2; \
    fi

# Runs a linter on the whole sources
lint: check-uv
    uvx ruff check --fix src
    uvx ruff check --fix tests
    uvx rumdl check .

# Runs a formatter on the whole sources
format: check-uv
    uvx ruff format src
    uvx ruff format tests
    uvx rumdl fmt .

# Runs all the tests for Python code and produces a code coverage report.
test:
    uv run pytest --cov=src --cov-branch --cov-report=html --cov-report=term-missing --cov-fail-under=95 --cov-precision=1 tests/

# Equivalent to running lint, format and test.
checklist: lint format test

# Configures the project for development.
init-dev: check-uv
    @echo "Creating dev .venv"
    uv sync --group dev --group test
    uvx prek install -f --hook-type pre-commit --hook-type pre-push

# Configures the project with dependencies for running and testing the code.
init-test: check-uv
    @echo "Creating test .venv"
    uv sync --no-dev --group test

# Initializes the project with dependencies for running in production.
init: check-uv
    @echo "Creating production .venv"
    uv sync --no-dev --no-group test

init-optional: check-uv
    uv sync --no-dev --group test --all-extras

# Updates all prek git hooks to their latest version.
update-hooks: check-uv
    @echo "Updating prek git hooks"
    uvx prek auto-update

# Forces a prek run on all files and not only on changed files.
prek-all-files: check-uv
    @echo "Running prek hooks on all files"
    uvx prek run --all-files

# Tags the current commit with the version number taken from the pyproject.toml file.
tag: check-uv
    @echo "Tagging commit with the current version"
    git tag "`uv version --short`"

# Publishes the package to PyPI. You must have initialized the project with the init goal, otherwise you deploy dev dependencies!
publish: check-uv
    @echo "Build and publish to PyPI"
    uv build
    uv publish

# Entirely cleans the (Python) project.
clean:
    @echo "Cleaning project ..."
    @rm -fr .venv *.lock htmlcov
    @echo "Cleaning finished."
