#!/bin/bash
# Compile Vert.x core plus the Web modules under one CodeQL trace command.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRAMEWORKS_DIR="$PROJECT_ROOT/frameworks"
M2_REPO="$PROJECT_ROOT/.build-cache/m2/repository"
MAVEN_REPOS="central::default::https://repo.maven.apache.org/maven2,aliyunmaven::default::https://maven.aliyun.com/repository/public"

export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk}"
export PATH="$JAVA_HOME/bin:$PATH"
export MAVEN_OPTS="${MAVEN_OPTS:-} -Dmaven.repo.local=$M2_REPO"

mkdir -p "$M2_REPO"

cd "$FRAMEWORKS_DIR/vert.x-4.5.28"
mvn \
  -Dmaven.repo.local="$M2_REPO" \
  -DremoteRepositories="$MAVEN_REPOS" \
  -DskipTests \
  -DskipITs \
  -Dmaven.javadoc.skip=true \
  compile

cd "$FRAMEWORKS_DIR/vertx-web-4.5.28"
mvn \
  -Dmaven.repo.local="$M2_REPO" \
  -DremoteRepositories="$MAVEN_REPOS" \
  -DskipTests \
  -DskipITs \
  -Dmaven.javadoc.skip=true \
  -pl vertx-web-common,vertx-web,vertx-web-client \
  -am \
  compile
