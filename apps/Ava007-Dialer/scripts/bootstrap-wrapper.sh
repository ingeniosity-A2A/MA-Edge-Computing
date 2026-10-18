#!/usr/bin/env bash
# Restores the Gradle wrapper launcher state that the GitHub API could not seed:
# the binary gradle-wrapper.jar and the executable bits.
#
#   ./scripts/bootstrap-wrapper.sh
set -euo pipefail

cd "$(dirname "$0")/.."

JAR=gradle/wrapper/gradle-wrapper.jar
VERSION="$(sed -n 's/^distributionUrl=.*gradle-\([0-9.]*\)-bin\.zip.*/\1/p' \
  gradle/wrapper/gradle-wrapper.properties)"
VERSION="${VERSION:-8.11.1}"

if [ -s "$JAR" ]; then
  echo "$JAR already present"
else
  echo "Fetching $JAR for Gradle $VERSION"
  curl -fsSL -o "$JAR" \
    "https://raw.githubusercontent.com/gradle/gradle/v$VERSION/gradle/wrapper/gradle-wrapper.jar"
fi

chmod +x gradlew scripts/set-key.sh scripts/bootstrap-wrapper.sh

if [ ! -x "${JAVA_HOME:-}/bin/java" ] && ! command -v java >/dev/null 2>&1; then
  echo "warning: no java found; install JDK 17 before building" >&2
fi

echo "Ready: run ./gradlew :app:assembleDebug"
