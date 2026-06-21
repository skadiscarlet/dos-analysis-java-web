#!/bin/bash
# Compile the Spring Boot 3 core module while CodeQL traces javac invocations.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="$PROJECT_ROOT/frameworks/spring-boot-3.5.15"

export GRADLE_USER_HOME="$PROJECT_ROOT/.build-cache/gradle"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk}"
export PATH="$JAVA_HOME/bin:$PATH"

import_gradle_wrapper_cache() {
  local dist_name="$1"
  local home_dists="/home/furina/.gradle/wrapper/dists"
  local source_dist="$home_dists/$dist_name"
  local target_dist="$GRADLE_USER_HOME/wrapper/dists/$dist_name"

  if [ -d "$target_dist" ] && find "$target_dist" -mindepth 2 -maxdepth 2 -type d -name 'gradle-*' | grep -q .; then
    return
  fi
  if [ -d "$source_dist" ]; then
    mkdir -p "$(dirname "$target_dist")"
    mkdir -p "$target_dist"
    cp -a "$source_dist"/. "$target_dist"/.
  fi
}

import_gradle_module_cache() {
  local source_modules="/home/furina/.gradle/caches/modules-2"
  local target_modules="$GRADLE_USER_HOME/caches/modules-2"
  local import_marker="$target_modules/.codex-imported-from-home"

  if [ -f "$import_marker" ]; then
    return
  fi
  if [ -d "$source_modules/files-2.1" ]; then
    mkdir -p "$(dirname "$target_modules")"
    mkdir -p "$target_modules"
    cp -a "$source_modules"/. "$target_modules"/.
    touch "$import_marker"
  fi
}

mkdir -p "$GRADLE_USER_HOME"
import_gradle_wrapper_cache "gradle-8.14.5-bin"
import_gradle_module_cache
cd "$SOURCE_ROOT"

sed -i 's/^networkTimeout=.*/networkTimeout=120000/' gradle/wrapper/gradle-wrapper.properties

./gradlew \
  --no-daemon \
  --max-workers="${GRADLE_MAX_WORKERS:-4}" \
  --no-build-cache \
  -x test \
  :spring-boot-project:spring-boot:clean \
  :spring-boot-project:spring-boot:compileJava
