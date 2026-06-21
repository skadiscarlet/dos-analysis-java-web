#!/usr/bin/env python3
"""Phase 2 自动化执行脚本"""

import subprocess
import json
import csv
from pathlib import Path
from datetime import datetime

# 配置
BASE_DIR = Path("/home/furina/new_tool/dos-analysis-web")
DATABASES = {
    "tomcat": BASE_DIR / "databases/tomcat-9.0-db",
    "spring-boot": BASE_DIR / "databases/spring-boot-2.7-db",
    "spring-boot-3": BASE_DIR / "databases/spring-boot-3-db",
    "jetty": BASE_DIR / "databases/jetty-11-db",
    "undertow": BASE_DIR / "databases/undertow-2-db",
    "jersey": BASE_DIR / "databases/jersey-3.1-db",
    "vertx": BASE_DIR / "databases/vertx-4-db",
    "micronaut": BASE_DIR / "databases/micronaut-3-db",
}

QUERY = BASE_DIR / "codeql/queries/phase2_source_discovery.ql"
RESULTS_DIR = BASE_DIR / "results/phase2"

def run_query(framework, db_path):
    """运行 CodeQL 查询"""
    print(f"==> 运行 {framework} 查询...")

    bqrs_path = RESULTS_DIR / f"{framework}_sources.bqrs"
    csv_path = RESULTS_DIR / f"{framework}_sources.csv"

    # 运行查询
    subprocess.run([
        "codeql", "query", "run",
        f"--database={db_path}",
        f"--output={bqrs_path}",
        str(QUERY),
    ], check=True)

    # 解码为 CSV
    subprocess.run([
        "codeql", "bqrs", "decode",
        f"--format=csv",
        f"--output={csv_path}",
        str(bqrs_path),
    ], check=True)

    print(f"✓ {framework} 查询完成: {csv_path}")
    return csv_path

def parse_csv_to_json(csv_path, framework):
    """解析 CSV 为结构化 JSON"""
    sources = []

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # 解析 CodeQL 输出（假设格式为单个字段包含所有信息）
            # 实际格式需要根据查询输出调整
            sources.append({
                "framework": framework,
                "raw": row
            })

    return sources

def aggregate_results():
    """聚合所有框架结果"""
    print("\n==> 聚合结果...")

    all_sources = []
    stats = {}

    for framework in DATABASES.keys():
        csv_path = RESULTS_DIR / f"{framework}_sources.csv"
        if not csv_path.exists():
            print(f"⚠ {framework} 结果不存在，跳过")
            continue

        sources = parse_csv_to_json(csv_path, framework)
        all_sources.extend(sources)
        stats[framework] = len(sources)
        print(f"  {framework}: {len(sources)} entries")

    # 保存聚合结果
    output = {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "total_entries": len(all_sources),
            "frameworks": list(stats.keys()),
            "stats": stats,
        },
        "sources": all_sources
    }

    output_path = RESULTS_DIR / "phase2_sources.json"
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2)

    print(f"\n✓ 聚合完成: {output_path}")
    print(f"总计: {len(all_sources)} entries")

    return output_path

def main():
    """主函数"""
    print("=== Phase 2 自动化分析 ===\n")

    # 创建结果目录
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # 运行所有查询
    for framework, db_path in DATABASES.items():
        if not db_path.exists():
            print(f"⚠ {framework} 数据库不存在，跳过: {db_path}")
            continue

        try:
            run_query(framework, db_path)
        except subprocess.CalledProcessError as e:
            print(f"✗ {framework} 查询失败: {e}")

    # 聚合结果
    aggregate_results()

    print("\n✓ Phase 2 自动化分析完成")

if __name__ == "__main__":
    main()
