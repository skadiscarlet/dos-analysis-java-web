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

echo "==> 所有框架下载完成"
