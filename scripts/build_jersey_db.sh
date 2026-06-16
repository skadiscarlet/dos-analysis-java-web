#!/bin/bash
set -e

FRAMEWORKS_DIR="/home/furina/new_tool/dos-analysis-web/frameworks"
DB_DIR="/home/furina/new_tool/dos-analysis-web/databases"

SOURCE_ROOT="$FRAMEWORKS_DIR/jersey-3.1.3"
DB_PATH="$DB_DIR/jersey-3.1-db"

if [ -d "$DB_PATH" ]; then
    echo "✓ Jersey 数据库已存在: $DB_PATH"
    exit 0
fi

echo "==> 构建 Jersey 3.1.3 CodeQL 数据库..."
echo "源码路径: $SOURCE_ROOT"
echo "数据库路径: $DB_PATH"

mkdir -p "$DB_DIR"

cd "$SOURCE_ROOT"

# 使用容错模式构建
codeql database create "$DB_PATH" \
    --language=java \
    --source-root="$SOURCE_ROOT" \
    --command="mvn compile -DskipTests -Dmaven.javadoc.skip=true -fn" \
    --overwrite

echo "✓ Jersey 数据库构建完成"
