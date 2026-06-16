#!/bin/bash
set -e

FRAMEWORKS_DIR="/home/furina/new_tool/dos-analysis-web/frameworks"
DB_DIR="/home/furina/new_tool/dos-analysis-web/databases"

SOURCE_ROOT="$FRAMEWORKS_DIR/jetty-11.0.15"
DB_PATH="$DB_DIR/jetty-11-db"

if [ -d "$DB_PATH" ]; then
    echo "✓ Jetty 数据库已存在: $DB_PATH"
    exit 0
fi

echo "==> 构建 Jetty 11.0.15 CodeQL 数据库..."
echo "源码路径: $SOURCE_ROOT"
echo "数据库路径: $DB_PATH"

mkdir -p "$DB_DIR"

cd "$SOURCE_ROOT"

codeql database create "$DB_PATH" \
    --language=java \
    --source-root="$SOURCE_ROOT" \
    --command="mvn clean compile -DskipTests -Dmaven.javadoc.skip=true" \
    --overwrite

echo "✓ Jetty 数据库构建完成"
