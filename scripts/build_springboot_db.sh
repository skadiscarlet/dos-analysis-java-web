#!/bin/bash
set -e

FRAMEWORKS_DIR="/home/furina/new_tool/dos-analysis-web/frameworks"
DB_DIR="/home/furina/new_tool/dos-analysis-web/databases"

SOURCE_ROOT="$FRAMEWORKS_DIR/spring-boot"
DB_PATH="$DB_DIR/spring-boot-2.7-db"

if [ -d "$DB_PATH" ]; then
    echo "✓ Spring Boot 数据库已存在: $DB_PATH"
    exit 0
fi

echo "==> 构建 Spring Boot 2.7 CodeQL 数据库..."
echo "源码路径: $SOURCE_ROOT"
echo "数据库路径: $DB_PATH"

mkdir -p "$DB_DIR"

cd "$SOURCE_ROOT"

# 清理之前的构建
./gradlew clean --no-daemon

# 使用容错模式构建，只编译主代码
codeql database create "$DB_PATH" \
    --language=java \
    --source-root="$SOURCE_ROOT" \
    --command="./gradlew :spring-boot-project:spring-boot:compileJava :spring-boot-project:spring-boot-autoconfigure:compileJava :spring-boot-project:spring-web:compileJava --no-daemon -x test" \
    --overwrite

echo "✓ Spring Boot 数据库构建完成"
