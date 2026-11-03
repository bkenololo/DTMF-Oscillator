#!/bin/sh
# Local installation only. Does not require administrator privileges.
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
build_root="$project_root/.ngspice-build"
mkdir -p "$build_root"
tar -xzf "$project_root/vendor/ngspice-47.tar.gz" -C "$build_root"
mkdir -p "$build_root/objects"
cd "$build_root/objects"
../ngspice-47/configure \
  --prefix="$project_root/tools/ngspice" \
  --with-x=no --with-readline=no --enable-xspice \
  --disable-openmp --disable-debug
make -j4
make install
"$project_root/tools/ngspice/bin/ngspice" --version
