#!/bin/bash
set -e

FRAMEWORKS_DIR="/home/furina/new_tool/dos-analysis-web/frameworks"
DB_DIR="/home/furina/new_tool/dos-analysis-web/databases"

SOURCE_ROOT="$FRAMEWORKS_DIR/undertow-2.3.7"
DB_PATH="$DB_DIR/undertow-2-db"

if [ -d "$DB_PATH" ]; then
    echo "✓ Undertow 数据库已存在: $DB_PATH"
    exit 0
fi

echo "==> 构建 Undertow 2.3.7 CodeQL 数据库..."
echo "源码路径: $SOURCE_ROOT"
echo "数据库路径: $DB_PATH"

mkdir -p "$DB_DIR"

cd "$SOURCE_ROOT"

# 使用容错模式并覆盖编译器插件版本
codeql database create "$DB_PATH" \
    --language=java \
    --source-root="$SOURCE_ROOT" \
    --command="mvn compile -DskipTests -Dmaven.javadoc.skip=true -Drat.skip=true -Dmaven.compiler.plugin.version=3.11.0 -fn" \
    --overwrite

echo "✓ Undertow 数据库构建完成"
