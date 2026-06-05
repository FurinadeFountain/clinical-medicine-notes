#!/usr/bin/env python3
"""文本归一化：修复 OCR 部首伪影、特殊空格、标题分隔符。不改动原始文件，只产出工作副本。"""
from __future__ import annotations
import sys
import unicodedata
import re
from pathlib import Path

# CJK 部首补充区无 NFKC 映射的 9 字 → 规范 CJK
MANUAL = {
    "⻅": "见", "⻣": "骨", "⻛": "风", "⻢": "马", "⻓": "长",
    "⻩": "黄", "⻝": "食", "⻔": "门", "⻮": "齿",
}
# 字体缺字形/OCR 异体标点 → 规范字符
PUNCT = {
    "｡": "。", "､": "、", "｢": "「", "｣": "」",        # 半角→全角 CJK 标点
    "〜": "–", "～": "–", "~": "–",                      # 各类波浪号(范围) → en-dash
    "∼": "–",                                            # 数学波浪
    "―": "-", "﹣": "-",                                  # OCR 横线/小减号 → ASCII hyphen
    "⭐": "★", "️": "",                                  # emoji star → text star; drop VS16
    "½": "1/2", "⅔": "2/3",                              # 分数字符 → 可排版文本
}


def normalize_text(t: str) -> str:
    out: list[str] = []
    for ch in t:
        if ch in MANUAL:
            out.append(MANUAL[ch]); continue
        o = ord(ch)
        if (o < 0x20 and ch not in "\n\r\t") or 0x7F <= o <= 0x9F:  # 控制字符(OCR残留BELL等)
            continue
        if 0x2E80 <= o <= 0x2EFF or 0x2F00 <= o <= 0x2FDF:  # CJK 部首区 → NFKC
            out.append(unicodedata.normalize("NFKC", ch)); continue
        if ch in (" ", " ", " ", " "):  # 各类窄/不间断空格 → 普通空格
            out.append(" "); continue
        if ch == "­":  # soft hyphen 删除
            continue
        if ch in PUNCT:
            out.append(PUNCT[ch]); continue
        out.append(ch)
    return "".join(out)


def normalize_medical_symbols(t: str) -> str:
    """统一常见医学缩写的上下标/希腊字母形式。

    源 Markdown 中很多缩写只能写作 CO2、FiO2、HCO3、kg-1 等普通文本。
    这里在生成层做保守替换，不改变原始笔记。
    """
    t = normalize_text(t)

    literal = {
        "PETCO2": "PETCO₂",
        "ETCO2": "ETCO₂",
        "A-aDO2": "A-aDO₂",
        "AaDO2": "A-aDO₂",
        "PaCO2": "PaCO₂",
        "PaC02": "PaCO₂",
        "PaO2": "PaO₂",
        "Pa02": "PaO₂",
        "FiO2": "FiO₂",
        "SpO2": "SpO₂",
        "Sp02": "SpO₂",
        "SaO2": "SaO₂",
        "SvO2": "SvO₂",
        "ScvO2": "ScvO₂",
        "CaO2": "CaO₂",
        "CMRO2": "CMRO₂",
        "VO2max": "VO₂max",
        "N2O": "N₂O",
        "DO2": "DO₂",
        "VO2": "VO₂",
        "CO2": "CO₂",
        "O2": "O₂",
        "H2O": "H₂O",
        "HCO3": "HCO₃",
        "FEV1": "FEV₁",
        "Na+": "Na⁺",
        "K+": "K⁺",
        "Ca2+": "Ca²⁺",
        "Mg2+": "Mg²⁺",
        "Cl-": "Cl⁻",
        "Cl－": "Cl⁻",
        "H+": "H⁺",
        "kg-1": "kg⁻¹",
        "h-1": "h⁻¹",
        "min-1": "min⁻¹",
        "kg/m2": "kg/m²",
        "㎡": "m²",
        "cmH2O": "cmH₂O",
        "cmHz 0": "cmH₂O",
        "cmHz0": "cmH₂O",
        "mmHig": "mmHg",
        "alpha": "α",
        "Alpha": "α",
        "beta": "β",
        "Beta": "β",
        "gamma": "γ",
        "Gamma": "γ",
        "delta": "δ",
        "Delta": "Δ",
        "ug/kg/min": "μg/(kg·min)",
        "ug/kg": "μg/kg",
        "ug/ml": "μg/ml",
    }
    for old in sorted(literal, key=len, reverse=True):
        t = t.replace(old, literal[old])

    t = re.sub(r"(?<=\d)m2\b", "m²", t)
    t = re.sub(r"(?<=/|·)m2\b", "m²", t)
    return t


def normalize_headings(t: str) -> str:
    """标题行的半角分隔符 ' | ' → 全角 ' ｜ '，与版式一致。"""
    lines = t.split("\n")
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#"):
            ln = ln.replace("**", "")          # 标题不应含加粗标记
            if "|" in ln:
                ln = ln.replace(" | ", " ｜ ").replace(" |", " ｜").replace("| ", "｜ ")
            lines[i] = ln
    return "\n".join(lines)


def drop_empty_headings(t: str) -> str:
    """Remove Markdown headings that contain no title text.

    These usually come from accidental lone ``#`` lines in source notes. Pandoc
    converts them to empty LaTeX section commands, which then leave blank
    ornaments in the PDF and empty entries in the table of contents.
    """
    return "\n".join(
        ln for ln in t.split("\n")
        if not re.match(r"^\s*#{1,6}\s*$", ln)
    )


_LIST_ITEM_RE = re.compile(r"^\s*([-*+]|\d+[.)])\s")
_INDENT_CONT_RE = re.compile(r"^\s{2,}\S")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _is_list_line(line: str) -> bool:
    return bool(_LIST_ITEM_RE.match(line) or _INDENT_CONT_RE.match(line))


def tighten_lists(t: str) -> str:
    """删除列表内部的空行(条目之间、条目与缩进续行之间)，使 Pandoc 输出紧凑、
    连续编号的单一列表，避免松散列表(行距突变)与被空行打断后的重新编号(层级乱)。
    仅当空行前后的非空行都是列表行时删除；列表与段落/标题间的空行保留。
    fenced code 块内的空行不动。"""
    lines = t.split("\n")
    out: list[str] = []
    prev_nonblank = ""
    in_fence = False
    n = len(lines)
    for i, ln in enumerate(lines):
        if _FENCE_RE.match(ln):
            in_fence = not in_fence
            prev_nonblank = ln
            out.append(ln)
            continue
        if (not in_fence) and ln.strip() == "":
            nxt = ""
            for j in range(i + 1, n):
                if lines[j].strip():
                    nxt = lines[j]
                    break
            if _is_list_line(prev_nonblank) and _is_list_line(nxt):
                continue  # 丢弃列表内部空行
        elif ln.strip():
            prev_nonblank = ln
        out.append(ln)
    return "\n".join(out)


def normalize_top_level_ordered_lists(t: str) -> str:
    """顺延同一标题块内的顶层有序列表编号。

    原始 Markdown 常用重复的 ``1.`` 作为自动编号占位；当列表项之间夹有
    普通段落、表格或无序列表时，Pandoc 会拆成多个 enumerate 环境并从 1
    重新开始，PDF 中就会出现同一小节内多个“1.”。这里只处理第 0 缩进
    的有序列表，保留缩进列表的层级。
    """
    lines = t.split("\n")
    expected = 1
    in_fence = False
    fence_marker = ""
    heading_re = re.compile(r"^#{1,6}\s+")
    item_re = re.compile(r"^(\d+)(\.\s+)")
    fence_re = re.compile(r"^\s*(```|~~~)")

    for i, ln in enumerate(lines):
        fence = fence_re.match(ln)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = ""
            continue
        if in_fence:
            continue

        if heading_re.match(ln):
            expected = 1
            continue

        item = item_re.match(ln)
        if not item:
            continue

        actual = int(item.group(1))
        if actual != expected:
            lines[i] = f"{expected}{item.group(2)}{ln[item.end():]}"
        expected += 1

    return "\n".join(lines)


def main() -> None:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    text = src.read_text(encoding="utf-8")
    text = normalize_text(text)
    text = normalize_headings(text)
    text = normalize_top_level_ordered_lists(text)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print(f"normalized: {src.name} -> {dst}")


if __name__ == "__main__":
    main()
