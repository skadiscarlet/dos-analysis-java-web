#!/usr/bin/env python3
"""Phase 2 准确率验证脚本"""

import json
import random
from pathlib import Path
from datetime import datetime

BASE_DIR = Path("/home/furina/new_tool/dos-analysis-web")
RESULTS_DIR = BASE_DIR / "results/phase2"
SAMPLE_SIZE = 25  # 每个框架采样 25 个

def load_results():
    """加载 Phase 2 识别结果"""
    with open(RESULTS_DIR / "phase2_sources.json") as f:
        return json.load(f)

def sample_per_framework(sources, size=SAMPLE_SIZE):
    """每个框架随机采样"""
    by_framework = {}
    for src in sources:
        fw = src["framework"]
        if fw not in by_framework:
            by_framework[fw] = []
        by_framework[fw].append(src)

    samples = {}
    for fw, entries in by_framework.items():
        sample_count = min(size, len(entries))
        samples[fw] = random.sample(entries, sample_count)
        print(f"  {fw}: 采样 {sample_count}/{len(entries)}")

    return samples

def generate_review_list(samples):
    """生成待审查清单"""
    review_file = RESULTS_DIR / "phase2_manual_review.jsonl"

    with open(review_file, 'w') as f:
        for fw, entries in samples.items():
            for i, entry in enumerate(entries):
                f.write(json.dumps({
                    "id": f"{fw}_{i+1}",
                    "framework": fw,
                    "entry": entry,
                    "verdict": None,  # 待人工填写: "TP" | "FP"
                    "note": ""
                }, ensure_ascii=False) + "\n")

    print(f"\n✓ 生成待审查清单: {review_file}")
    print(f"  总计: {sum(len(e) for e in samples.values())} 个样本")
    print("\n请人工审查每个 entry，标记 verdict 为 TP/FP")
    print("审查完成后运行: python3 scripts/validate_phase2.py --calculate")

def calculate_metrics():
    """计算准确率（审查完成后）"""
    review_file = RESULTS_DIR / "phase2_manual_review.jsonl"

    if not review_file.exists():
        print("✗ 待审查清单不存在，请先运行采样")
        return False

    verdicts = []
    with open(review_file) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("verdict"):
                verdicts.append(entry)

    if not verdicts:
        print("✗ 尚未完成审查，请标记 verdict 字段")
        return False

    # 按框架统计
    by_framework = {}
    for v in verdicts:
        fw = v["framework"]
        if fw not in by_framework:
            by_framework[fw] = {"TP": 0, "FP": 0}

        verdict = v["verdict"].upper()
        if verdict in ["TP", "FP"]:
            by_framework[fw][verdict] += 1

    # 生成报告
    print("\n=== Phase 2 准确率评估 ===\n")
    print(f"{'Framework':<15} {'Precision':<12} {'TP/Total':<10}")
    print("-" * 40)

    overall_tp = 0
    overall_total = 0

    for fw, counts in sorted(by_framework.items()):
        total = counts["TP"] + counts["FP"]
        precision = counts["TP"] / total if total > 0 else 0
        overall_tp += counts["TP"]
        overall_total += total

        print(f"{fw:<15} {precision:>6.1%}       {counts['TP']}/{total}")

    print("-" * 40)
    overall_precision = overall_tp / overall_total if overall_total > 0 else 0
    print(f"{'Overall':<15} {overall_precision:>6.1%}       {overall_tp}/{overall_total}")

    # 保存结果
    result = {
        "generated_at": datetime.now().isoformat(),
        "by_framework": by_framework,
        "overall": {
            "tp": overall_tp,
            "total": overall_total,
            "precision": overall_precision
        },
        "pass": overall_precision >= 0.9
    }

    result_file = RESULTS_DIR / "phase2_validation.json"
    with open(result_file, 'w') as f:
        json.dump(result, f, indent=2)

    print(f"\n✓ 验证结果保存到: {result_file}")

    if result["pass"]:
        print("\n✓ 准确率达标 (>= 90%)")
    else:
        print("\n✗ 准确率未达标 (< 90%)")

    return result["pass"]

def main():
    """主函数"""
    import sys

    if "--calculate" in sys.argv:
        # 计算准确率
        calculate_metrics()
    else:
        # 采样
        print("=== Phase 2 采样验证 ===\n")

        data = load_results()
        sources = data["sources"]

        print(f"总计: {len(sources)} entries\n")
        print(f"采样策略: 每框架 {SAMPLE_SIZE} 个\n")

        samples = sample_per_framework(sources)
        generate_review_list(samples)

if __name__ == "__main__":
    main()
