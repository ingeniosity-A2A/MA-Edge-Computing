#!/usr/bin/env sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
WRAPPER_DIR="$ROOT/gradle/wrapper"
JAR="$WRAPPER_DIR/gradle-wrapper.jar"
mkdir -p "$WRAPPER_DIR"
if [ ! -s "$JAR" ]; then
  TMP="$JAR.tmp"
  curl --fail --location --silent --show-error \
    "https://raw.githubusercontent.com/gradle/gradle/v8.13.0/gradle/wrapper/gradle-wrapper.jar" \
    --output "$TMP"
  test -s "$TMP"
  mv "$TMP" "$JAR"
fi
chmod +x "$ROOT/gradlew"
printf 'Gradle wrapper ready: '
"$ROOT/gradlew" --version
