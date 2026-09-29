# ELEGOO V4 bring-up: Python environment for the unchanged upstream client.
{ pkgs ? import <nixpkgs> { } }:

pkgs.mkShell {
  packages = with pkgs; [
    python312
    uv
    just
    arduino-cli
    esptool
    avrdude
    poppler-utils
    unzip
    wget
    gnumake
    patch
  ];

  # Native libraries used by the OpenCV, pygame and scientific Python wheels.
  LD_LIBRARY_PATH = pkgs.lib.makeLibraryPath (with pkgs; [
    stdenv.cc.cc.lib
    zlib
    glib
    libGL
    libxkbcommon
    wayland
    SDL2
    alsa-lib
    libpulseaudio
    libx11
    libxext
    libxcursor
    libxi
    libxrandr
    libxrender
    libxcb
  ]);

  shellHook = ''
    export ELEGOO_PROJECT_ROOT=${pkgs.lib.escapeShellArg (toString ./.)}
    export UV_CACHE_DIR="$ELEGOO_PROJECT_ROOT/.cache/uv"
    export UV_PYTHON=${pkgs.python312}/bin/python3.12
    export UV_PYTHON_DOWNLOADS=never
    export PYTHONNOUSERSITE=1
    export ARDUINO_DIRECTORIES_DATA="$ELEGOO_PROJECT_ROOT/.cache/arduino/data"
    export ARDUINO_DIRECTORIES_DOWNLOADS="$ELEGOO_PROJECT_ROOT/.cache/arduino/downloads"
    export ARDUINO_DIRECTORIES_USER="$ELEGOO_PROJECT_ROOT/.cache/arduino/user"

    car-setup() {
      uv sync --project "$ELEGOO_PROJECT_ROOT/upstream" \
        --python "$UV_PYTHON" --no-dev --group test || return
      source "$ELEGOO_PROJECT_ROOT/upstream/.venv/bin/activate"
    }

    if [ -f "$ELEGOO_PROJECT_ROOT/upstream/.venv/bin/activate" ]; then
      source "$ELEGOO_PROJECT_ROOT/upstream/.venv/bin/activate"
    fi
    echo 'ELEGOO V4 shell. Run car-setup to install/sync the upstream Python environment.'
  '';
}
