#!/bin/sh
set -eu
TASK_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP_ROOT="${OKABEBOT_MAC_APP_DIR:-$HOME/Applications}/Little Lab.app"
mkdir -p "$APP_ROOT/Contents/MacOS"
swiftc "$TASK_ROOT/mac/Companion.swift" -o "$APP_ROOT/Contents/MacOS/LittleLab" -framework AppKit -framework WebKit -framework AVFoundation
cat > "$APP_ROOT/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>CFBundleExecutable</key><string>LittleLab</string><key>CFBundleIdentifier</key><string>local.okabebot.companion</string><key>CFBundleName</key><string>Little Lab</string><key>CFBundleVersion</key><string>1</string><key>LSUIElement</key><true/><key>NSMicrophoneUsageDescription</key><string>Hold the mic button to talk to your local companion.</string><key>NSLocalNetworkUsageDescription</key><string>Connect to your local companion controller.</string><key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict></dict></plist>
PLIST
codesign --force --sign "${OKABEBOT_MAC_SIGN_IDENTITY:--}" "$APP_ROOT"
open "$APP_ROOT"
