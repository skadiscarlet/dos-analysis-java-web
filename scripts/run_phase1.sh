#!/bin/bash
# Phase 1: 候选特征查询
# 在 Tomcat 和 Spring Boot CodeQL 数据库上运行 phase1_candidates.ql

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RESULTS_DIR="$PROJECT_ROOT/results/phase1"
QUERY="$PROJECT_ROOT/codeql/queries/phase1_candidates.ql"

# 数据库路径
TOMCAT_DB="$PROJECT_ROOT/databases/tomcat-9.0-db"
SPRINGBOOT_DB="$PROJECT_ROOT/databases/spring-boot-2.7-db"
SPRINGBOOT3_DB="$PROJECT_ROOT/databases/spring-boot-3-db"

mkdir -p "$RESULTS_DIR"

echo "======================================"
echo "Phase 1: 候选特征查询"
echo "======================================"
echo ""

# 函数：运行查询
run_query() {
  local framework=$1
  local db_path=$2
  local output_prefix="$RESULTS_DIR/${framework}"

  echo ">>> 处理 $framework..."

  # 检查数据库是否存在和就绪
  if [ ! -d "$db_path" ]; then
    echo "    [跳过] 数据库不存在: $db_path"
    return
  fi

  if [ ! -f "$db_path/codeql-database.yml" ]; then
    echo "    [跳过] 数据库配置文件缺失"
    return
  fi

  # 检查是否 finalised
  if ! grep -q "finalised: true" "$db_path/codeql-database.yml" 2>/dev/null; then
    echo "    [跳过] 数据库尚未完成构建 (finalised: false)"
    return
  fi

  echo "    运行查询..."
  codeql query run \
    --database="$db_path" \
    --threads=0 \
    --ram=8192 \
    --output="${output_prefix}_candidates.bqrs" \
    "$QUERY"

  echo "    解码 BQRS 结果..."
  codeql bqrs decode \
    --format=csv \
    --output="${output_prefix}_candidates.csv" \
    "${output_prefix}_candidates.bqrs"

  # 统计候选数量
  local count=$(tail -n +2 "${output_prefix}_candidates.csv" | wc -l)
  echo "    ✓ 找到 $count 个候选"
  echo ""
}

# 运行 Tomcat
run_query "tomcat" "$TOMCAT_DB"

# 运行 Spring Boot
run_query "spring-boot" "$SPRINGBOOT_DB"
run_query "spring-boot-3" "$SPRINGBOOT3_DB"

echo "======================================"
echo "Phase 1 完成"
echo "======================================"
echo "结果位置: $RESULTS_DIR"
echo ""
