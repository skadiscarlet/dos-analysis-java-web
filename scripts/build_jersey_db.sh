#!/bin/bash
set -euo pipefail

FRAMEWORKS_DIR="/home/furina/new_tool/dos-analysis-web/frameworks"
DB_DIR="/home/furina/new_tool/dos-analysis-web/databases"
CODEQL_BIN="${CODEQL_BIN:-/usr/bin/codeql}"
THREADS="${THREADS:-16}"
RAM_MB="${RAM_MB:-20480}"

SOURCE_ROOT="$FRAMEWORKS_DIR/jersey-3.1.3"
ANALYSIS_ROOT="$FRAMEWORKS_DIR/jersey-3.1.3-analysis-sources"
DB_PATH="$DB_DIR/jersey-3.1-db"
FORCE=0

if [ "${1:-}" = "--force" ]; then
    FORCE=1
fi

if [ -d "$DB_PATH" ] && [ "$FORCE" -ne 1 ]; then
    echo "✓ Jersey 数据库已存在: $DB_PATH"
    echo "  如需重建以覆盖 buildless 源码抽取，请运行: $0 --force"
    exit 0
fi

echo "==> 构建 Jersey 3.1.3 CodeQL 数据库..."
echo "源码路径: $SOURCE_ROOT"
echo "分析源码视图: $ANALYSIS_ROOT"
echo "数据库路径: $DB_PATH"
echo "模式: buildless source extraction (focused Jersey modules)"

mkdir -p "$DB_DIR"
rm -rf "$ANALYSIS_ROOT"
mkdir -p "$ANALYSIS_ROOT"

copy_module_sources() {
    local module="$1"
    local source_dir="$SOURCE_ROOT/$module/src/main/java"
    local target_dir="$ANALYSIS_ROOT/$module/src/main/java"
    if [ -d "$source_dir" ]; then
        mkdir -p "$(dirname "$target_dir")"
        cp -a "$source_dir" "$target_dir"
    else
        echo "WARN: module source not found: $source_dir"
    fi
}

copy_module_sources "core-common"
copy_module_sources "core-client"
copy_module_sources "core-server"
copy_module_sources "media/multipart"
copy_module_sources "security/oauth1-signature"
copy_module_sources "security/oauth1-client"
copy_module_sources "security/oauth1-server"

cd "$ANALYSIS_ROOT"

# Jersey 全仓 Maven trace 在部分环境会跳过 media/multipart 等模块；聚焦源码视图的 buildless
# 抽取更适合第二部分的 provider/parser/source-discovery 查询，也避免全仓依赖解析拖慢复现。
"$CODEQL_BIN" database create "$DB_PATH" \
    --language=java \
    --source-root="$ANALYSIS_ROOT" \
    --build-mode=none \
    --threads="$THREADS" \
    --ram="$RAM_MB" \
    --overwrite

echo "✓ Jersey 数据库构建完成"
