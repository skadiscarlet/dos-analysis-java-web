#!/usr/bin/env python3
"""
Phase 1 结果分析脚本
"""

import csv
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime


def load_candidates(csv_path: Path) -> list[dict]:
    """从 CSV 加载候选"""
    candidates = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')
        for row in reader:
            candidates.append(row)
    return candidates


def analyze_candidates(candidates: list[dict]) -> dict:
    """分析候选统计信息"""
    stats = {
        'total': len(candidates),
        'unique_entries': len(set(c.get('entry', '') for c in candidates)),
        'unique_writers': len(set(c.get('write', '') for c in candidates)),
        'top_entry_classes': defaultdict(int),
        'top_writer_methods': defaultdict(int),
    }

    for c in candidates:
        entry = c.get('col3', '')  # entry class
        writer = c.get('write', '')  # writer method

        if entry:
            stats['top_entry_classes'][entry] += 1
        if writer:
            stats['top_writer_methods'][writer] += 1

    # 取 top 10
    stats['top_entry_classes'] = dict(
        sorted(stats['top_entry_classes'].items(), key=lambda x: x[1], reverse=True)[:10]
    )
    stats['top_writer_methods'] = dict(
        sorted(stats['top_writer_methods'].items(), key=lambda x: x[1], reverse=True)[:10]
    )

    return stats


def generate_report(framework_stats: dict[str, dict], output_path: Path):
    """生成 Phase 1 报告"""

    lines = [
        "# Phase 1 分析报告",
        "",
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 1. 总体统计",
        "",
        "| Framework | 候选数 | 独立入口 | 独立写操作 |",
        "|-----------|--------|----------|------------|",
    ]

    total_candidates = 0
    for fw, stats in framework_stats.items():
        lines.append(
            f"| {fw} | {stats['total']} | {stats['unique_entries']} | {stats['unique_writers']} |"
        )
        total_candidates += stats['total']

    lines.extend([
        f"| **总计** | **{total_candidates}** | - | - |",
        "",
        "## 2. 分框架详情",
        "",
    ])

    for fw, stats in framework_stats.items():
        lines.extend([
            f"### {fw}",
            "",
            f"- 总候选数: {stats['total']}",
            f"- 独立入口: {stats['unique_entries']}",
            f"- 独立写操作: {stats['unique_writers']}",
            "",
        ])

        if stats['top_entry_classes']:
            lines.extend([
                "**Top 入口类:**",
                "",
            ])
            for cls, count in stats['top_entry_classes'].items():
                lines.append(f"- `{cls}`: {count}")
            lines.append("")

        if stats['top_writer_methods']:
            lines.extend([
                "**Top 写操作:**",
                "",
            ])
            for method, count in stats['top_writer_methods'].items():
                lines.append(f"- `{method}`: {count}")
            lines.append("")

    lines.extend([
        "## 3. 验收标准",
        "",
        "### ✓ 已满足",
        "",
        "- [x] CodeQL 查询成功运行",
        "- [x] 生成结构化 CSV 输出",
        "- [x] 包含入口点和写操作信息",
        "",
        "### ⚠ 待确认",
        "",
    ])

    if total_candidates == 0:
        lines.extend([
            "- [ ] 候选数量为 0，需要检查:",
            "  - 数据库是否正确构建",
            "  - 查询逻辑是否适配目标框架",
            "  - Entry/Writer 定义是否过于严格",
            "",
        ])
    elif total_candidates < 10:
        lines.extend([
            f"- [ ] 候选数量较少 ({total_candidates})，建议:",
            "  - 检查 Entry 定义是否覆盖常见 Web 入口",
            "  - 检查 Writer 定义是否覆盖状态写入模式",
            "  - 考虑放宽部分过滤条件",
            "",
        ])
    else:
        lines.extend([
            f"- [x] 候选数量合理 ({total_candidates})",
            "",
        ])

    lines.extend([
        "## 4. 结论",
        "",
    ])

    if total_candidates == 0:
        lines.extend([
            "Phase 1 产出为空，需要诊断根因后重新运行。",
            "",
            "**建议行动:**",
            "1. 检查数据库构建日志",
            "2. 验证查询在简化数据集上的行为",
            "3. 调整 Entry/Writer 定义",
            "",
        ])
    elif total_candidates < 10:
        lines.extend([
            "Phase 1 产出候选较少，建议优化后进入 Phase 2。",
            "",
            "**建议行动:**",
            "1. 人工复核现有候选质量",
            "2. 根据复核结果调整查询",
            "3. 重新运行 Phase 1",
            "",
        ])
    else:
        lines.extend([
            "Phase 1 成功产出候选集，可进入 Phase 2 精细分析。",
            "",
            "**下一步:**",
            "1. 人工抽样复核候选质量",
            "2. 准备 Phase 2 特征提取查询",
            "3. 设计排序和筛选策略",
            "",
        ])

    # 写入报告
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    print(f"报告已生成: {output_path}")


def main():
    base_dir = Path(__file__).parent.parent
    results_dir = base_dir / 'results' / 'phase1'

    framework_stats = {}

    # 分析 Tomcat
    tomcat_csv = results_dir / 'tomcat_candidates.csv'
    if tomcat_csv.exists():
        print(f"分析 Tomcat 结果: {tomcat_csv}")
        candidates = load_candidates(tomcat_csv)
        stats = analyze_candidates(candidates)
        framework_stats['Tomcat'] = stats
        print(f"  - 总候选数: {stats['total']}")
        print(f"  - 独立入口: {stats['unique_entries']}")
        print(f"  - 独立写操作: {stats['unique_writers']}")
    else:
        print(f"⚠ Tomcat 结果不存在: {tomcat_csv}")

    # 分析 Spring Boot
    spring_csv = results_dir / 'springboot_candidates.csv'
    if spring_csv.exists():
        print(f"分析 Spring Boot 结果: {spring_csv}")
        candidates = load_candidates(spring_csv)
        stats = analyze_candidates(candidates)
        framework_stats['Spring Boot'] = stats
        print(f"  - 总候选数: {stats['total']}")
        print(f"  - 独立入口: {stats['unique_entries']}")
        print(f"  - 独立写操作: {stats['unique_writers']}")
    else:
        print(f"⚠ Spring Boot 结果暂未生成（数据库构建中）")

    # 生成报告
    if framework_stats:
        report_path = base_dir / 'results' / 'phase1_report.md'
        generate_report(framework_stats, report_path)
        print(f"\n✓ Phase 1 分析完成")
    else:
        print("\n✗ 无可用结果，跳过报告生成")


if __name__ == '__main__':
    main()
