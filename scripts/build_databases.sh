#!/bin/bash
# Build CodeQL databases for Java Web frameworks

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

FRAMEWORKS_DIR="$PROJECT_ROOT/frameworks"
DB_DIR="$PROJECT_ROOT/databases"

# 读取配置
CODEQL_BIN="/usr/bin/codeql"
THREADS=16
RAM_MB=20480
BUILD_CACHE_DIR="$PROJECT_ROOT/.build-cache"

usage() {
    echo "Usage: $0 <framework1> [framework2 ...]"
    echo "Available frameworks: tomcat, spring-boot, spring-boot-3, vertx, micronaut"
    exit 1
}

if [ $# -eq 0 ]; then
    usage
fi

build_tomcat() {
    echo "=========================================="
    echo "Building Tomcat 9.0.x database"
    echo "=========================================="

    cd "$FRAMEWORKS_DIR"

    if [ ! -d "tomcat" ]; then
        echo "[1/3] Cloning Tomcat repository..."
        git clone --depth 1 --branch 9.0.x https://github.com/apache/tomcat.git
    else
        echo "[1/3] Tomcat repository already exists"
    fi

    cd tomcat

    echo "[2/3] Building Tomcat..."
    ant clean compile || echo "Build may have warnings, continuing..."

    echo "[3/3] Creating CodeQL database..."
    "$CODEQL_BIN" database create "$DB_DIR/tomcat-9.0-db" \
        --language=java \
        --source-root=. \
        --threads=$THREADS \
        --ram=$RAM_MB \
        --overwrite

    echo "✓ Tomcat database created at $DB_DIR/tomcat-9.0-db"
}

build_spring_boot() {
    echo "=========================================="
    echo "Building Spring Boot 2.7.x database"
    echo "=========================================="

    cd "$FRAMEWORKS_DIR"

    if [ ! -d "spring-boot" ]; then
        echo "[1/3] Cloning Spring Boot repository..."
        git clone --depth 1 --branch 2.7.x https://github.com/spring-projects/spring-boot.git
    else
        echo "[1/3] Spring Boot repository already exists"
    fi

    cd spring-boot

    echo "[2/3] Skipping build (using buildless database)..."

    echo "[3/3] Creating CodeQL database (buildless mode with --build-mode=none)..."
    "$CODEQL_BIN" database create "$DB_DIR/spring-boot-2.7-db" \
        --language=java \
        --source-root=. \
        --build-mode=none \
        --threads=$THREADS \
        --ram=$RAM_MB \
        --overwrite

    echo "✓ Spring Boot database created at $DB_DIR/spring-boot-2.7-db"
}

build_spring_boot_3() {
    echo "=========================================="
    echo "Building Spring Boot 3.5.15 database"
    echo "=========================================="

    cd "$FRAMEWORKS_DIR"

    if [ ! -d "spring-boot-3.5.15" ]; then
        echo "[1/3] Cloning Spring Boot 3.5.15 repository..."
        git clone --depth 1 --branch v3.5.15 https://github.com/spring-projects/spring-boot.git spring-boot-3.5.15
    else
        echo "[1/3] Spring Boot 3.5.15 repository already exists"
    fi

    echo "[2/3] Preparing local build cache..."
    mkdir -p "$BUILD_CACHE_DIR/gradle" "$DB_DIR"

    echo "[3/3] Creating CodeQL database with Gradle build extraction..."
    "$CODEQL_BIN" database create "$DB_DIR/spring-boot-3-db" \
        --language=java \
        --source-root="$FRAMEWORKS_DIR/spring-boot-3.5.15" \
        --command="bash $PROJECT_ROOT/scripts/codeql_build_spring_boot_3.sh" \
        --threads=$THREADS \
        --ram=$RAM_MB \
        --overwrite

    echo "✓ Spring Boot 3 database created at $DB_DIR/spring-boot-3-db"
}

build_vertx() {
    echo "=========================================="
    echo "Building Vert.x 4.5.28 database"
    echo "=========================================="

    cd "$FRAMEWORKS_DIR"

    if [ ! -d "vert.x-4.5.28" ]; then
        echo "[1/4] Cloning Vert.x core 4.5.28 repository..."
        git clone --depth 1 --branch 4.5.28 https://github.com/eclipse-vertx/vert.x.git vert.x-4.5.28
    else
        echo "[1/4] Vert.x core 4.5.28 repository already exists"
    fi

    if [ ! -d "vertx-web-4.5.28" ]; then
        echo "[2/4] Cloning Vert.x Web 4.5.28 repository..."
        git clone --depth 1 --branch 4.5.28 https://github.com/vert-x3/vertx-web.git vertx-web-4.5.28
    else
        echo "[2/4] Vert.x Web 4.5.28 repository already exists"
    fi

    echo "[3/4] Preparing local Maven cache..."
    mkdir -p "$BUILD_CACHE_DIR/m2/repository" "$DB_DIR"

    echo "[4/4] Creating CodeQL database with Maven build extraction..."
    "$CODEQL_BIN" database create "$DB_DIR/vertx-4-db" \
        --language=java \
        --source-root="$FRAMEWORKS_DIR" \
        --command="bash $PROJECT_ROOT/scripts/codeql_build_vertx_4.sh" \
        --threads=$THREADS \
        --ram=$RAM_MB \
        --overwrite

    echo "✓ Vert.x database created at $DB_DIR/vertx-4-db"
}

build_micronaut() {
    echo "=========================================="
    echo "Building Micronaut Core 3.10.8 database"
    echo "=========================================="

    cd "$FRAMEWORKS_DIR"

    if [ ! -d "micronaut-core-3.10.8" ]; then
        echo "[1/3] Cloning Micronaut Core 3.10.8 repository..."
        git clone --depth 1 --branch v3.10.8 https://github.com/micronaut-projects/micronaut-core.git micronaut-core-3.10.8
    else
        echo "[1/3] Micronaut Core 3.10.8 repository already exists"
    fi

    cd micronaut-core-3.10.8

    echo "[2/3] Preparing local build cache..."
    mkdir -p "$BUILD_CACHE_DIR/gradle" "$DB_DIR"

    echo "[3/3] Creating CodeQL database with Gradle build extraction..."
    "$CODEQL_BIN" database create "$DB_DIR/micronaut-3-db" \
        --language=java \
        --source-root="$FRAMEWORKS_DIR/micronaut-core-3.10.8" \
        --command="bash $PROJECT_ROOT/scripts/codeql_build_micronaut_3.sh" \
        --threads=$THREADS \
        --ram=$RAM_MB \
        --overwrite

    echo "✓ Micronaut database created at $DB_DIR/micronaut-3-db"
}

# 处理命令行参数
for framework in "$@"; do
    case "$framework" in
        tomcat)
            build_tomcat
            ;;
        spring-boot)
            build_spring_boot
            ;;
        spring-boot-3)
            build_spring_boot_3
            ;;
        vertx)
            build_vertx
            ;;
        micronaut)
            build_micronaut
            ;;
        *)
            echo "Error: Unknown framework '$framework'"
            usage
            ;;
    esac
done

echo ""
echo "=========================================="
echo "All databases built successfully!"
echo "=========================================="
