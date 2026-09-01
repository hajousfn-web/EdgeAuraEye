#!/usr/bin/env sh

set -eu

APP_HOME=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
CLASSPATH=$APP_HOME/gradle/wrapper/gradle-wrapper.jar

if [ ! -f "$CLASSPATH" ]; then
  echo "ERROR: Missing gradle-wrapper.jar at $CLASSPATH" >&2
  echo "Please generate the wrapper in Android Studio or run: gradle wrapper" >&2
  exit 1
fi

JAVACMD=${JAVA_HOME}/bin/java
if [ -z "${JAVA_HOME:-}" ]; then
  JAVACMD=java
fi

exec "$JAVACMD" ${JAVA_OPTS:-} -classpath "$CLASSPATH" org.gradle.wrapper.GradleWrapperMain "$@"
