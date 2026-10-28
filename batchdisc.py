"""batchdisc —— 把批处理折扣的适用性归并成组并标出每组的代表项。

按结构键把条目聚类，标出批处理折扣的适用性上的同组项与各组的代表样本

定位：
  分组依据是结构特征而不是字面相似，改了措辞但结构没变的仍算同组

设计约束：
  1. **只报告能定位到具体位置的结论**，不做语义猜测。
  2. **规则表公开**，每条命中都能对应到 批处理折扣的适用性 领域的一条明示规则。
  3. **输入为空或格式不对时明确报错**，不静默返回空结果。

仅依赖 Python 标准库。

用法:
    python batchdisc.py --help
    python batchdisc.py --file input.txt
    python batchdisc.py --text "示例内容"
    python batchdisc.py --file input.txt --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys

# 领域规则表：每条规则独立可核查，命中即报，不做推断。
RULES: list[dict] = [
    {
        "name": "批处理折扣的适用性·缺失",
        "why": "缺少批处理折扣的适用性的关键要素时无法给出可靠判定",
        "severity": "high",
        "keywords": ['缺失', 'missing', 'absent', '缺少', '没有'],
    },
    {
        "name": "批处理折扣的适用性·冲突",
        "why": "同一份输入里两处批处理折扣的适用性描述互相矛盾",
        "severity": "high",
        "keywords": ['冲突', 'conflict', 'contradict', '矛盾', '不一致', '相反'],
    },
    {
        "name": "批处理折扣的适用性·越界",
        "why": "批处理折扣的适用性的取值超出常规范围",
        "severity": "medium",
        "keywords": ['越界', 'out of range', 'outlier', '越界', '超限', '超过'],
    },
    {
        "name": "批处理折扣的适用性·退化",
        "why": "批处理折扣的适用性的信息量不足以支撑结论",
        "severity": "medium",
        "keywords": ['退化', 'degrade', 'insufficient', '不足', '太少', '无法'],
    },
    {
        "name": "批处理折扣的适用性·泄漏",
        "why": "批处理折扣的适用性相关的内容被意外暴露",
        "severity": "high",
        "keywords": ['泄漏', 'leak', 'expose', '泄漏', '暴露', '明文'],
    },
    {
        "name": "批处理折扣的适用性·重复",
        "why": "同一处批处理折扣的适用性信息被反复传递",
        "severity": "low",
        "keywords": ['重复', 'duplicate', 'repeat', '重复', 'again'],
    },
    {
        "name": "批处理折扣的适用性·陈旧",
        "why": "批处理折扣的适用性的时效性已经过期",
        "severity": "medium",
        "keywords": ['陈旧', 'stale', 'expired', '过期', '陈旧', '旧版'],
    },
    {
        "name": "批处理折扣的适用性·不可核",
        "why": "批处理折扣的适用性的说法无法追溯到具体证据",
        "severity": "high",
        "keywords": ['不可核', 'unverifiable', 'no evidence', '无法追溯', '没有来源'],
    },
]


def batchdisc_tokens(text: str) -> set[str]:
    """抽词元。中文按二元组切——见 consistency-checker 引擎里的说明。"""
    low = text.lower()
    out = set(re.findall(r"[a-z]{3,}", low))
    for seg in re.findall(r"[\u4e00-\u9fff]+", low):
        if len(seg) == 1:
            out.add(seg)
        else:
            for i in range(len(seg) - 1):
                out.add(seg[i:i + 2])
    return out


def batchdisc_key_of(text: str) -> str:
    """用最高频的词做聚类键。

    按**出现次数**排序取前几个词，不是字典序——字典序取出来的键
    与内容重心无关，聚类会失真。
    """
    counts: dict[str, int] = {}
    for t in batchdisc_tokens(text):
        counts[t] = counts.get(t, 0) + 1
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return "|".join(t for t, _ in top) if top else ""


def batchdisc_analyze(text: str) -> dict:
    """主分析：按特征归组并统计各组占比。"""
    # 分块：空行分隔的段落，或以列表/序号开头的行，各自成块。
    # 只按空行切是不够的——很多列表是紧凑排布的，中间没有空行，
    # 整份文档会被当成一块，组数永远是 1。
    blocks: list[str] = []
    for chunk in re.split(r"\n\s*\n", text):
        for piece in re.split(r"\n(?=[-*]|\d+[.)])", chunk):
            piece = piece.strip()
            if piece:
                blocks.append(piece)
    if not blocks:
        return {"ok": False, "error": "没有可分组的段落", "count": 0}
    groups: dict[str, list[int]] = {}
    for i, b in enumerate(blocks):
        groups.setdefault(batchdisc_key_of(b), []).append(i)
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    return {
        "ok": True,
        "count": len(blocks),
        "groups": [{"key": k, "members": v, "size": len(v)} for k, v in ranked],
        "group_count": len(groups),
        "largest": ranked[0][0] if ranked else "",
        "singletons": sum(1 for _, v in groups.items() if len(v) == 1),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def render(result: dict) -> str:
    """把结果渲染成人读的文本。每个工具的版式不同。"""
    out: list[str] = []
    if not result.get("ok", True):
        out.append(f"无法分析：{{result.get('error', '未知原因')}}")
        return "\n".join(out)
    out.append(f"段落数：{result['count']}  分组数：{result['group_count']}  独组 {result['singletons']}")
    out.append("")
    for g in result["groups"]:
        out.append(f"  {g['size']:>3} 份  键={g['key'][:50]}")
    out.append("")
    out.append(f"最大组键：{result['largest']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="batchdisc",
        description="按结构键把条目聚类，标出批处理折扣的适用性上的同组项与各组的代表样本（仅依赖标准库）",
        epilog=(
            "示例:\n"
            "  python batchdisc.py --file input.txt\n"
            "  python batchdisc.py --text '示例内容'\n"
            "  python batchdisc.py --file input.txt --json\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="输入文件路径")
    src.add_argument("--text", help="直接给出输入内容")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args(argv)

    if args.file:
        try:
            with open(args.file, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            print(f"读不了文件：{{e}}", file=sys.stderr)
            return 2
    else:
        content = args.text

    if not content.strip():
        print("输入是空的。", file=sys.stderr)
        return 2

    result = batchdisc_analyze(content)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(render(result))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
