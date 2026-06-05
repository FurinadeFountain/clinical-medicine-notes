#!/usr/bin/env python3
"""pandoc 原始 LaTeX → 定制正文片段。
处理：图片→矢量命令、删首个\\section(章名)、特殊块→\\noteblock/supplbox、
嵌套quote扁平、HR美化、清理pandoc自动\\label。"""
from __future__ import annotations
import re
import sys
from pathlib import Path
from normalize import normalize_medical_symbols

NOTE_BLOCKS = {"名词解释", "问答题", "简答题", "课后思考题", "课后思考题解答",
               "病例题摘要", "对比总结", "难点集萃"}

HEADING_RE = re.compile(r"^\\(chapter|section|subsection|subsubsection)\{(.*)\}\s*$")
IMG_RE = re.compile(r"\\pandocbounded\{\\includegraphics\[[^\]]*\]\{([^}]*)\}\}")
HR_RE = re.compile(r"\\begin\{center\}\\rule\{[0-9.]+\\linewidth\}\{[0-9.]+pt\}\\end\{center\}")
LT_RE = re.compile(
    r"(?:\{\\def\\LTcaptype\{none\}[^\n]*\n)?"
    r"\\begin\{longtable\}\[\]\{([^}]*)\}(.*?)\\end\{longtable\}(?:\s*\n?\})?",
    re.DOTALL)


def _lt_to_mtbl(m: re.Match) -> str:
    """pandoc longtable → 统一 mtbl 样式（消除 none-counter 错误并统一表样）。"""
    body = m.group(2)
    b = body.replace("\\noalign{}", "")
    hm = re.search(r"\\toprule(.*?)\\midrule", b, re.DOTALL)
    header = (hm.group(1) if hm else "").strip()
    dm = re.search(r"\\endlastfoot(.*)$", b, re.DOTALL)
    data = (dm.group(1) if dm else "").strip()
    for tok in ("\\endhead", "\\endfirsthead", "\\endlastfoot",
                "\\toprule", "\\midrule", "\\bottomrule"):
        header = header.replace(tok, "")
        data = data.replace(tok, "")
    header, data = header.strip(), data.strip()
    # 列数按各行实际单元格数(以 & 计)的最大值确定(pandoc colspec 常不符)
    rows = [r for r in (header + "\n" + data).split("\\\\") if r.strip()]
    ncol = max((r.count("&") + 1 for r in rows), default=2)
    colspec = "".join("X[l]" for _ in range(ncol))   # X 列自动分配宽度并换行,防溢出
    return (
        "\\begin{table*}[t]\\centering\\sffamily\\small\n"
        "\\begin{mtbl}{width=\\linewidth, colspec={" + colspec + "}, row{1}={bg=headtint,font=\\bfseries}}\n"
        "\\toprule\n" + header.strip() + "\n\\midrule\n" + data.strip()
        + "\n\\bottomrule\n\\end{mtbl}\n\\end{table*}"
    )


def _esc(s: str) -> str:
    """转义 LaTeX 特殊字符(用于把 verbatim 内容还原为正文)。"""
    s = s.replace("\\", "")
    for a, b in (("&", r"\&"), ("%", r"\%"), ("#", r"\#"), ("_", r"\_"), ("$", r"\$"),
                 ("{", r"\{"), ("}", r"\}"), ("<", r"\textless{}"), (">", r"\textgreater{}"),
                 ("^", r"\^{}"), ("~", r"\textasciitilde{}")):
        s = s.replace(a, b)
    return s


def _verbatim_to_list(m: re.Match) -> str:
    """pandoc 把缩进过深的列表误判为 verbatim(等宽不断行致溢出) → 还原为 itemize。"""
    items: list[str] = []
    for ln in m.group(1).split("\n"):
        s = ln.rstrip()
        if not s.strip():
            continue
        mi = re.match(r"^\s*[-*]\s+(.*)", s)
        if mi:
            items.append(_esc(mi.group(1)))
        elif items:
            items[-1] += _esc(s.strip())
        else:
            items.append(_esc(s.strip()))
    return "\\begin{itemize}\n" + "\n".join(f"  \\item {it}" for it in items) + "\n\\end{itemize}"


VERB_RE = re.compile(r"\\begin\{verbatim\}\n?(.*?)\n?\\end\{verbatim\}", re.DOTALL)


def postprocess(tex: str, image_map: dict[str, str]) -> str:
    # 0) longtable → mtbl
    tex = LT_RE.sub(_lt_to_mtbl, tex)
    # 1) 图片 → 矢量命令（按文件名）
    tex = IMG_RE.sub(lambda m: image_map.get(m.group(1).split("/")[-1], "% [未映射图片已删除]"), tex)
    # 2) 清理 pandoc 自动标签
    tex = re.sub(r"\\label\{[^}]*\}", "", tex)
    # 2b) verbatim(误判代码块) → itemize
    tex = VERB_RE.sub(_verbatim_to_list, tex)
    # 3) HR → 分隔符
    tex = HR_RE.sub(r"\\anesdiv", tex)
    # 3b) 残留 markdown 加粗(pandoc 因 CJK 标点未闭合的 **...**) → \textbf
    for _ in range(5):
        tex, n = re.subn(r"\*\*([^*\n]{1,120}?)\*\*", r"\\textbf{\1}", tex)
        if not n:
            break
    # 残余孤立 ** 清除(不成对的标记噪声)
    tex = tex.replace("**", "")

    lines = tex.split("\n")
    out: list[str] = []
    first_section_dropped = False
    in_suppl = False
    qdepth = 0

    def close_suppl():
        nonlocal in_suppl
        if in_suppl:
            out.append("\\end{supplbox}")
            in_suppl = False

    for ln in lines:
        s = ln.rstrip()
        # 引用块扁平化
        if s.strip() == r"\begin{quote}":
            qdepth += 1
            if qdepth == 1:
                out.append(r"\begin{quote}")
            continue
        if s.strip() == r"\end{quote}":
            if qdepth == 1:
                out.append(r"\end{quote}")
            qdepth = max(0, qdepth - 1)
            continue

        m = HEADING_RE.match(s)
        if m:
            level, title = m.group(1), m.group(2).strip()
            # 删除第一个 \section（章名，章由组装层提供）
            if level == "section" and not first_section_dropped:
                first_section_dropped = True
                continue
            # 遇到任何标题/块，先关闭未结束的 supplbox
            base = title.split("：")[0].split(":")[0].strip()
            if base.startswith("补充内容") or title.startswith("补充内容"):
                close_suppl()
                out.append(r"\begin{supplbox}")
                in_suppl = True
                continue
            if title in NOTE_BLOCKS or base in NOTE_BLOCKS:
                close_suppl()
                out.append(f"\\noteblock{{{title}}}")
                continue
            # 普通标题：先关 supplbox
            close_suppl()
            out.append(s)
            continue

        out.append(ln)

    close_suppl()
    res = "\n".join(out)
    res = normalize_medical_symbols(res)
    # 给所有列表强制 \tightlist(统一紧凑行距;补 pandoc 因子内容判为松散而漏掉的)
    res = re.sub(r"(\\begin\{itemize\}\n)(?!\s*\\tightlist)", r"\1\\tightlist\n", res)
    res = re.sub(
        r"(\\begin\{enumerate\}\n(?:\s*\\def\\labelenum[^\n]*\n)?(?:\s*\\setcounter\{enum[^\n]*\n)?)(?!\s*\\tightlist)",
        r"\1\\tightlist\n", res)
    # 收尾：去除多余空行
    res = re.sub(r"\n{3,}", "\n\n", res)
    return res


IMAGE_MAPS = {
    "临床麻醉学": {
        "Image.png": r"\figChildPugh", "Image (2).png": r"\figDLT",
        "Image (3).png": r"\figNMT", "Image (4).png": r"\figCPB",
        "Image (5).png": r"\figBPClass", "Image (6).png": r"\figBPRisk",
        "Image (7).png": r"\figBPPrognosis", "Image (8).png": r"\figGCS",
        "Image (9).png": r"\figApgar", "Image.jpeg": r"\figBurnRule",
    },
    "疼痛诊疗学": {"Image.png": r"\figLumbarRoot"},
    "疼痛治疗学": {},
    "危重病医学": {},
}


def main() -> None:
    name = sys.argv[1]
    raw = Path(f"raw/{name}.tex").read_text(encoding="utf-8")
    body = postprocess(raw, IMAGE_MAPS.get(name, {}))
    outp = Path(f"body/{name}.tex")
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(body, encoding="utf-8")
    n_note = body.count(r"\noteblock")
    n_suppl = body.count(r"\begin{supplbox}")
    n_fig = sum(body.count(c) for c in IMAGE_MAPS.get(name, {}).values())
    print(f"{name}: noteblock={n_note} supplbox={n_suppl} figs={n_fig} -> {outp}")


if __name__ == "__main__":
    main()
