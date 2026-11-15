# -*- coding: utf-8 -*-
"""文档边界校验：开发过程记录.md 与 系统使用说明.md 内容边界互斥性检查。

校验维度（逐模块输出明细，任一维度失败退出码为 1）：
1. 词汇边界
   - 系统使用说明：不得包含开发过程 / 技术实现 / 版本变更词汇
     （BUG-xx、PR、PASS/FAIL、回归、tests/、seed、v1.x、Selenium、E2E、根因……）
   - 开发过程记录：不得包含面向终端用户的操作指引结构
     （嵌入截图、步骤链 → toast、菜单入口指引、字段级操作指引、mermaid 示意图……）
2. 内容重复边界：两份文档不得出现归一化空白后 ≥20 字符的完全相同内容行
3. 模块定位校验：使用说明仅允许「概述/功能/环境配置/操作流程/常见问题」类模块；
   开发记录仅允许「需求/版本/阶段/资产/边界」类模块

用法：python tests/doc_boundary_check.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USAGE = ROOT / "系统使用说明.md"
DEVLOG = ROOT / "开发过程记录.md"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ---------------------------------------------------------------- 词汇边界
# 系统使用说明黑名单：(正则, 违规类别)
USAGE_BLACKLIST = [
    (r"BUG-\d+", "BUG 修复记录"),
    (r"\bPR\b", "PR 提交信息"),
    (r"\bPASS\b|\bFAIL\b", "测试结果表述"),
    (r"回归", "回归测试叙述"),
    (r"test-evidence", "测试证据目录"),
    (r"tests[/\\]", "测试脚本路径"),
    (r"backend[/\\]|frontend[/\\]", "源码路径"),
    (r"\bseed\b", "seed 实现细节"),
    (r"v1\.\d", "版本号"),
    (r"Selenium|headless", "自动化测试工具"),
    (r"\be2e\b|E2E", "端到端测试"),
    (r"交付报告|维护日志|修复计划", "已归档过程文档"),
    (r"根因|traceback", "缺陷定位细节"),
    (r"\bPRD\b|AC-\d+|FIX-\d+", "需求/验收/修复编号"),
    (r"state_machine|schema_postgresql", "技术实现细节"),
    (r"pytest", "测试依赖"),
    (r"专项检测", "测试活动"),
    (r"docs[/\\]migrations|docker exec", "数据库运维命令"),
]
# 使用说明豁免：含以下关键字的行跳过词汇校验（用户必需的启动/安装命令）
USAGE_WHITELIST_KEYS = ["python run.py", "requirements.txt"]

# 开发过程记录黑名单：终端用户操作指引的结构性信号
DEV_BLACKLIST = [
    (r"^!\[", "嵌入界面截图"),
    (r"→\s*toast|toast「", "步骤链预期文案（→ toast）"),
    (r"入口[：:]\s*「", "菜单入口指引"),
    (r"登录后默认进入|左侧菜单依次", "页面/菜单引导描述"),
    (r"字段级操作|预期页面表现|（含示例值）", "字段级操作指引要素"),
    (r"#{1,6}\s*.*(操作步骤|操作指南|使用方法|图文操作)", "操作指引类标题"),
    (r"```mermaid", "面向用户的流程示意图"),
    (r"请(填写|选择|点击|输入|前往)", "祈使语气操作指引"),
]

# ---------------------------------------------------------------- 模块定位
# 使用说明允许的模块主题（标题关键词，命中其一即定位合规）
USAGE_MODULE_OK = re.compile(r"系统概述|功能模块|环境配置|操作流程|常见问题|排查|系统使用说明|大宗矿产")
# 开发记录允许的模块主题
DEV_MODULE_OK = re.compile(r"需求对接|立项|版本轨迹|阶段|测试资产|证据|边界|开发过程记录")

HEADING = re.compile(r"^(#{1,3})\s+(.*)$")


def split_modules(text):
    """按 1~3 级标题切分模块，返回 [(标题, [行...]), ...]，文档头归入模块「(文档头)」。

    fenced code block（``` 围栏）内的行一律视为正文内容，不参与标题判定
    （避免把 PowerShell/Python 注释行误判为 markdown 标题）。
    """
    modules, cur_title, cur_lines = [], "(文档头)", []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            cur_lines.append(line)
            continue
        m = None if in_fence else HEADING.match(line)
        if m and len(m.group(1)) <= 3:
            if cur_lines or cur_title != "(文档头)":
                modules.append((cur_title, cur_lines))
            cur_title, cur_lines = m.group(2).strip(), []
        else:
            cur_lines.append(line)
    if cur_lines or cur_title != "(文档头)":
        modules.append((cur_title, cur_lines))
    return modules


def word_hits(lines, blacklist, whitelist_keys=()):
    """返回 [(行号, 类别, 行内容截断)]；含豁免关键字的行跳过。"""
    hits = []
    for i, line in enumerate(lines, 1):
        if any(k in line for k in whitelist_keys):
            continue
        for pattern, category in blacklist:
            if re.search(pattern, line):
                hits.append((i, category, line.strip()[:60]))
                break
    return hits


def duplicate_lines(text_a, text_b, min_len=20):
    """两份文档间归一化后 ≥min_len 的完全相同内容行。"""
    def norm_lines(text):
        return [re.sub(r"\s+", "", ln) for ln in text.splitlines()
                if len(re.sub(r"\s+", "", ln)) >= min_len]
    set_b = set(norm_lines(text_b))
    dup = []
    for i, ln in enumerate(norm_lines(text_a), 1):
        if ln in set_b:
            dup.append(ln[:60])
    return dup


def module_report(name, modules, module_ok, blacklist, whitelist_keys=()):
    """逐模块校验：词汇命中 + 模块定位。返回 (违规数, 行列表)。

    模块定位规则：`x.y` 编号的子模块标题继承其父章的定位结论，
    仅对章级标题（含文档标题）做主题关键词校验。
    """
    rows, total, parent_ok = [], 0, True
    for title, lines in modules:
        is_sub = bool(re.match(r"^\d+\.\d+", title))
        located = parent_ok if is_sub else (bool(module_ok.search(title)) or title == "(文档头)")
        if not is_sub:
            parent_ok = located
        hits = word_hits(lines, blacklist, whitelist_keys)
        status = "OK" if (not hits and located) else "违规"
        total += len(hits) + (0 if located else 1)
        detail = "; ".join(f"L{n} {cat}: {txt}" for n, cat, txt in hits) or "-"
        if not located:
            detail = (detail + "; " if detail != "-" else "") + f"模块定位不明: {title}"
        rows.append((title, len(hits), located, status, detail))
    print(f"\n### {name} 逐模块校验（共 {len(modules)} 个模块）")
    print(f"| 模块 | 词汇命中 | 定位 | 判定 | 明细 |")
    print(f"|---|---|---|---|---|")
    for title, n, located, status, detail in rows:
        print(f"| {title} | {n} | {'合规' if located else '不明'} | {status} | {detail} |")
    return total


def main():
    if not USAGE.exists() or not DEVLOG.exists():
        print("缺少待校验文档:", USAGE if not USAGE.exists() else "", DEVLOG if not DEVLOG.exists() else "")
        return 1
    usage_text = USAGE.read_text(encoding="utf-8")
    dev_text = DEVLOG.read_text(encoding="utf-8")

    print("=" * 72)
    print("文档边界校验：开发过程记录.md × 系统使用说明.md")
    print("=" * 72)

    # 1. 逐模块词汇 + 定位校验
    usage_modules = split_modules(usage_text)
    dev_modules = split_modules(dev_text)
    bad = module_report("系统使用说明.md（应仅含终端用户操作指引）",
                        usage_modules, USAGE_MODULE_OK, USAGE_BLACKLIST, USAGE_WHITELIST_KEYS)
    bad += module_report("开发过程记录.md（应仅含开发过程档案）",
                         dev_modules, DEV_MODULE_OK, DEV_BLACKLIST)

    # 2. 重复内容边界
    dup1 = duplicate_lines(usage_text, dev_text)
    dup2 = duplicate_lines(dev_text, usage_text)
    dup = dup1 + dup2
    print(f"\n### 内容重复边界（≥20 字符归一化行交叉比对）")
    if dup:
        bad += len(dup)
        for d in dict.fromkeys(dup):
            print(f"  [重复] {d}")
        print(f"  重复行数：{len(dup)}")
    else:
        print("  两份文档无任何重复内容行 ✓")

    # 3. 汇总结论
    print("\n" + "=" * 72)
    if bad == 0:
        print("结论：PASS —— 两份文档边界清晰、无交叉重叠，符合交付标准。")
        return 0
    print(f"结论：FAIL —— 共发现 {bad} 处边界违规，请按明细修正后重跑。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
