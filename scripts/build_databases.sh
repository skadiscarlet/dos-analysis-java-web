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

usage() {
    echo "Usage: $0 <framework1> [framework2 ...]"
    echo "Available frameworks: tomcat, spring-boot"
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

# 处理命令行参数
for framework in "$@"; do
    case "$framework" in
        tomcat)
            build_tomcat
            ;;
        spring-boot)
            build_spring_boot
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
