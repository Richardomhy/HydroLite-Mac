#!/usr/bin/env bash

if [[ -n "${HYDROLITE_XCODE_DEVELOPER_DIR:-}" ]]; then
  export DEVELOPER_DIR="$HYDROLITE_XCODE_DEVELOPER_DIR"
elif [[ -d /Applications/Xcode.app/Contents/Developer ]]; then
  export DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer
elif [[ -d /Applications/Xcode-beta.app/Contents/Developer ]]; then
  export DEVELOPER_DIR=/Applications/Xcode-beta.app/Contents/Developer
fi

/usr/bin/xcodebuild -version >/dev/null 2>&1 || {
  echo "full_xcode_unavailable: install Xcode or set HYDROLITE_XCODE_DEVELOPER_DIR" >&2
  return 69 2>/dev/null || exit 69
}
