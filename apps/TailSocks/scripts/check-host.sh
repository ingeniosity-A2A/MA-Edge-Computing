#!/usr/bin/env bash
set -u
printf '%s\n' '=== Host ==='
uname -a
printf '\n%s\n' '=== Required tools ==='
for tool in git java go adb sdkmanager; do
  if command -v "$tool" >/dev/null 2>&1; then
    printf '%-12s %s\n' "$tool" "$(command -v "$tool")"
  else
    printf '%-12s MISSING\n' "$tool"
  fi
done
printf '\nJAVA_HOME=%s\nANDROID_HOME=%s\nANDROID_SDK_ROOT=%s\nANDROID_NDK_HOME=%s\n' \
  "${JAVA_HOME:-<unset>}" "${ANDROID_HOME:-<unset>}" "${ANDROID_SDK_ROOT:-<unset>}" "${ANDROID_NDK_HOME:-<unset>}"
if command -v java >/dev/null 2>&1; then java -version 2>&1; fi
if command -v go >/dev/null 2>&1; then go version; fi
if command -v adb >/dev/null 2>&1; then adb devices -l; fi
