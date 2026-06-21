#!/bin/bash
set -e

FRAMEWORKS_DIR="/home/furina/new_tool/dos-analysis-web/frameworks"
mkdir -p "$FRAMEWORKS_DIR"
cd "$FRAMEWORKS_DIR"

echo "==> 下载 Jetty 11.0.15..."
if [ ! -d "jetty-11.0.15" ]; then
    git clone --depth 1 --branch jetty-11.0.15 \
        https://github.com/eclipse/jetty.project.git jetty-11.0.15
    echo "✓ Jetty 11.0.15 下载完成"
else
    echo "✓ Jetty 11.0.15 已存在"
fi

echo "==> 下载 Undertow 2.3.7..."
if [ ! -d "undertow-2.3.7" ]; then
    git clone --depth 1 --branch 2.3.7.Final \
        https://github.com/undertow-io/undertow.git undertow-2.3.7
    echo "✓ Undertow 2.3.7 下载完成"
else
    echo "✓ Undertow 2.3.7 已存在"
fi

echo "==> 下载 Spring Boot 3.5.15..."
if [ ! -d "spring-boot-3.5.15" ]; then
    git clone --depth 1 --branch v3.5.15 \
        https://github.com/spring-projects/spring-boot.git spring-boot-3.5.15
    echo "✓ Spring Boot 3.5.15 下载完成"
else
    echo "✓ Spring Boot 3.5.15 已存在"
fi

echo "==> 下载 Vert.x 4.5.28 core..."
if [ ! -d "vert.x-4.5.28" ]; then
    git clone --depth 1 --branch 4.5.28 \
        https://github.com/eclipse-vertx/vert.x.git vert.x-4.5.28
    echo "✓ Vert.x 4.5.28 core 下载完成"
else
    echo "✓ Vert.x 4.5.28 core 已存在"
fi

echo "==> 下载 Vert.x Web 4.5.28..."
if [ ! -d "vertx-web-4.5.28" ]; then
    git clone --depth 1 --branch 4.5.28 \
        https://github.com/vert-x3/vertx-web.git vertx-web-4.5.28
    echo "✓ Vert.x Web 4.5.28 下载完成"
else
    echo "✓ Vert.x Web 4.5.28 已存在"
fi

echo "==> 下载 Micronaut Core 3.10.8..."
if [ ! -d "micronaut-core-3.10.8" ]; then
    git clone --depth 1 --branch v3.10.8 \
        https://github.com/micronaut-projects/micronaut-core.git micronaut-core-3.10.8
    echo "✓ Micronaut Core 3.10.8 下载完成"
else
    echo "✓ Micronaut Core 3.10.8 已存在"
fi

echo "==> 所有框架下载完成"
