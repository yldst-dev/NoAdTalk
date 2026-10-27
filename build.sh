#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
build_dir=$(mktemp -d "${TMPDIR:-/tmp}/no-ad-talk-package.XXXXXXXX")
trap 'rm -rf -- "$build_dir"' EXIT
package_dir="$build_dir/NoAdTalk"
mkdir -p "$package_dir"
cp NoAdTalk.command README.md LICENSE build.sh test.sh "$package_dir/"
cp -R Scripts tests docs "$package_dir/"
mkdir -p dist
find "$package_dir" -name __pycache__ -type d -prune -exec rm -r {} +
ditto -c -k --norsrc --noextattr --keepParent "$package_dir" dist/NoAdTalk.zip
