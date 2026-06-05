#!/usr/bin/env python3
"""Build the text-only integrated course LaTeX draft.

Local bitmap images and PDF attachments are intentionally omitted in the first
pass. Every Markdown attachment reference is recorded in an audit file so
simple, high-value figures can later be redrawn as TikZ/vector material.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT_ROOT = ROOT.parent
REPO = OUT_ROOT.parent
ANES_ROOT = OUT_ROOT / "麻醉专科"
ANES_BUILD = ANES_ROOT / "build"
SRC_BASIC = REPO / "01-源笔记" / "基础"
SRC_CLINICAL = REPO / "01-源笔记" / "临床"
SRC_PRACTICE = REPO / "01-源笔记" / "实践技能"

sys.path.insert(0, str(ANES_BUILD))
from normalize import (  # noqa: E402
    drop_empty_headings,
    normalize_headings,
    normalize_text,
    normalize_top_level_ordered_lists,
    tighten_lists,
)
import convert  # noqa: E402

PYTHON = os.environ.get("COURSE_BUILD_PYTHON", sys.executable)


@dataclass(frozen=True)
class SourceDoc:
    title: str
    filename: str
    source_dir: Path
    group: str

    @property
    def path(self) -> Path:
        return self.source_dir / self.filename


BASIC_DOCS = [
    SourceDoc("基础理论合集（除外生物化学）", "基础理论合集（除外生物化学）.md", SRC_BASIC, "basic"),
    SourceDoc("生物化学", "生物化学.md", SRC_BASIC, "basic"),
    SourceDoc("简明统计学与流行病学", "简明统计学与流行病学.md", SRC_BASIC, "basic"),
]


CLINICAL_SYSTEMS = [
    SourceDoc("外科总论", "外科总论.md", SRC_CLINICAL, "clinical"),
    SourceDoc("呼吸系统", "呼吸系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("循环系统", "循环系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("消化系统", "消化系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("泌尿系统", "泌尿系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("女性生殖系统", "女性生殖系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("血液系统", "血液系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("内分泌系统", "内分泌系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("精神和神经系统", "精神和神经系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("运动系统", "运动系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("风湿免疫系统", "风湿免疫系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("儿科系统", "儿科系统.md", SRC_CLINICAL, "clinical"),
    SourceDoc("传染病与性传播疾病", "传染病与性传播疾病.md", SRC_CLINICAL, "clinical"),
    SourceDoc("理化因素所致疾病", "理化因素所致疾病.md", SRC_CLINICAL, "clinical"),
]

CLINICAL_TOPICS = [
    SourceDoc("106个疾病诊断公式", "106个疾病诊断公式.md", SRC_CLINICAL, "clinical"),
    SourceDoc("临床系统整合总结与速记", "临床系统整合总结与速记.md", SRC_CLINICAL, "clinical"),
    SourceDoc("神经病学期末梳理", "神经病学·期末梳理.md", SRC_CLINICAL, "clinical"),
    SourceDoc("卒中精讲：诊疗思路及用药方案", "卒中精讲：诊疗思路及用药方案.md", SRC_CLINICAL, "clinical"),
    SourceDoc("错题分析", "错题分析.md", SRC_CLINICAL, "clinical"),
]

PRACTICE_DOCS = [
    SourceDoc("实践技能考察概述", "实践技能考察概述.md", SRC_PRACTICE, "practice"),
    SourceDoc("本科临床水平测试概述", "本科临床水平测试概述.md", SRC_PRACTICE, "practice"),
    SourceDoc("临床水平测试：实践技能", "临床水平测试：实践技能.md", SRC_PRACTICE, "practice"),
    SourceDoc("第二站：体格检查", "第二站：体格检查.md", SRC_PRACTICE, "practice"),
    SourceDoc("第三站：基本操作", "第三站：基本操作.md", SRC_PRACTICE, "practice"),
    SourceDoc("水平测试第三站：心肺腹体格检查", "水平测试第三站：心肺腹体格检查.md", SRC_PRACTICE, "practice"),
    SourceDoc("水平测试第四站：其他体格检查", "水平测试第四站：其他体格检查.md", SRC_PRACTICE, "practice"),
    SourceDoc("水平测试第五站：心肺复苏", "水平测试第五站：心肺复苏.md", SRC_PRACTICE, "practice"),
    SourceDoc("水平测试第六站：其他基本操作", "水平测试第六站：其他基本操作.md", SRC_PRACTICE, "practice"),
]

ANESTHESIA_CHAPTERS = [
    ("临床麻醉学", "临床麻醉学.tex"),
    ("疼痛诊疗学", "疼痛_merged.tex"),
    ("危重病医学", "危重病医学.tex"),
]

HEADING_RE = re.compile(r"^(#{1,6})(\s+.+)$")
SECTION_RE = re.compile(r"^[ \t]*\\section\{", re.MULTILINE)
SUBSECTION_RE = re.compile(r"^[ \t]*\\subsection\{", re.MULTILINE)
SUBSUBSECTION_RE = re.compile(r"^[ \t]*\\subsubsection\{", re.MULTILINE)
PARAGRAPH_RE = re.compile(r"^[ \t]*\\paragraph\{", re.MULTILINE)
COURSE_DIV_RE = re.compile(r"^\\(?:anesdiv|coursediv)\s*\n?", re.MULTILINE)
LOCAL_ATTACHMENT_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}
PRACTICE_D_HEADINGS = {
    "D1": "D1：血压、浅表淋巴结及神经系统检查",
    "D2": "D2：眼、甲状腺、胸部标志及反射检查",
    "D3": "D3：瞳孔、气管、脊柱及脑膜刺激征检查",
    "D4": "D4：眼集合反射、颈前淋巴结、甲状腺及上肢检查",
    "D5": "D5：手部、乳房、腹部体表标志及反射检查",
}
EXTRA_TEXT_REPLACEMENTS = {
    "⅔": "2/3",
    "½": "1/2",
    "⭐️": "★",
    "⭐": "★",
    "️": "",
    "﹣": "-",
    "―": "-",
    "𧿹": "拇",
}
LATEX_GREEK_COMMAND_REPAIRS = {
    r"\α": r"\alpha",
    r"\β": r"\beta",
    r"\γ": r"\gamma",
    r"\δ": r"\delta",
    r"\Δ": r"\Delta",
    r"\μ": r"\mu",
    r"\σ": r"\sigma",
    r"\ν": r"\nu",
    r"\ρ": r"\rho",
    r"\χ": r"\chi",
    r"\λ": r"\lambda",
    r"\π": r"\pi",
    r"\ω": r"\omega",
}
FINAL_TEX_REPLACEMENTS = {
    "5'→3`外切酶": "5'→3'外切酶",
    "V1-V2呈rsR`M形波": "V1-V2呈rsR'型（M形）波",
    "总分 15`，最低 3'": "总分 15，最低 3",
}


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def normalize_extra_text(t: str) -> str:
    for old, new in EXTRA_TEXT_REPLACEMENTS.items():
        t = t.replace(old, new)
    return t


def protect_math_percent(tex: str) -> str:
    out: list[str] = []
    in_display_math = False
    for line in tex.split("\n"):
        math_line = in_display_math or r"\(" in line or r"\[" in line
        if math_line and "%" in line:
            line = re.sub(r"(?<!\\)%", r"\\%", line)
        if r"\[" in line and r"\]" not in line:
            in_display_math = True
        if in_display_math and r"\]" in line:
            in_display_math = False
        out.append(line)
    return "\n".join(out)


def sanitize_generated_tex(tex: str) -> str:
    tex = normalize_extra_text(tex)
    for broken, repaired in LATEX_GREEK_COMMAND_REPAIRS.items():
        tex = tex.replace(broken, repaired)
    tex = re.sub(r"(?m)^\\item\s+[–-]\s*$\n?", "", tex)
    tex = protect_math_percent(tex)
    return tex


def sanitize_final_tex(tex: str) -> str:
    for old, new in FINAL_TEX_REPLACEMENTS.items():
        tex = tex.replace(old, new)
    return tex


def normalize_clinical_heading_depth(text: str) -> str:
    """Make the shallowest headings after the title become top-level sections."""
    lines = text.split("\n")
    heading_indices = [i for i, ln in enumerate(lines) if HEADING_RE.match(ln)]
    if len(heading_indices) < 2:
        return text

    first = heading_indices[0]
    content_levels: list[int] = []
    for i in heading_indices[1:]:
        m = HEADING_RE.match(lines[i])
        if m:
            content_levels.append(len(m.group(1)))
    if not content_levels:
        return text

    shift = min(content_levels) - 1
    if shift <= 0:
        return text

    for i in heading_indices:
        if i == first:
            continue
        m = HEADING_RE.match(lines[i])
        if not m:
            continue
        new_level = max(1, len(m.group(1)) - shift)
        lines[i] = "#" * new_level + m.group(2)
    return "\n".join(lines)


def clean_markdown_target(raw_target: str) -> str:
    target = unquote(raw_target.strip())
    # Drop optional Markdown title after the path: ![](a.png "title")
    if '"' in target:
        target = target.split('"', 1)[0].strip()
    if "'" in target:
        target = target.split("'", 1)[0].strip()
    return target


@dataclass(frozen=True)
class MarkdownRef:
    start: int
    end: int
    label: str
    target: str
    is_image: bool


def iter_markdown_refs(line: str) -> list[MarkdownRef]:
    """Parse Markdown image/link targets, including paths with parentheses."""
    refs: list[MarkdownRef] = []
    i = 0
    n = len(line)
    while i < n:
        bracket = line.find("[", i)
        if bracket < 0:
            break
        is_image = bracket > 0 and line[bracket - 1] == "!"
        start = bracket - 1 if is_image else bracket
        if start > 0 and line[start - 1] == "\\":
            i = bracket + 1
            continue
        close_label = line.find("](", bracket)
        if close_label < 0:
            break
        label = line[bracket + 1:close_label]
        pos = close_label + 2
        depth = 1
        while pos < n and depth:
            ch = line[pos]
            if ch == "\\":
                pos += 2
                continue
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            pos += 1
        if depth:
            i = close_label + 2
            continue
        target = line[close_label + 2:pos - 1]
        refs.append(MarkdownRef(start, pos, label, target, is_image))
        i = pos
    return refs


def is_local_attachment(raw_target: str) -> bool:
    target = clean_markdown_target(raw_target)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target):
        return False
    suffix = Path(target).suffix.lower()
    return ".assets/" in target or suffix in LOCAL_ATTACHMENT_SUFFIXES


def scan_attachments(doc: SourceDoc) -> list[dict[str, str | int]]:
    src = doc.path
    records: list[dict[str, str | int]] = []
    for lineno, line in enumerate(src.read_text(encoding="utf-8").splitlines(), start=1):
        for ref in iter_markdown_refs(line):
            if not is_local_attachment(ref.target):
                continue
            target = clean_markdown_target(ref.target)
            abs_target = (src.parent / target).resolve()
            records.append(
                {
                    "source_title": doc.title,
                    "source_file": str(src.relative_to(REPO)),
                    "line": lineno,
                    "kind": "图片" if ref.is_image else "附件",
                    "alt": ref.label,
                    "target": target,
                    "exists": "yes" if abs_target.exists() else "no",
                    "action": (
                        "首版省略；后续仅在可用 TikZ/tabularray 矢量重绘时纳入"
                        if ref.is_image else
                        "首版省略；保留文字笔记，PDF/位图附件后续按需重绘或摘录"
                    ),
                }
            )
    return records


def _attachment_residual_is_empty(residual: str) -> bool:
    residual = residual.strip()
    if not residual:
        return True
    residual = re.sub(r"^[-*+]\s*", "", residual).strip()
    residual = residual.strip("：:，,；;。.!！?？（）()[]【】")
    return residual in {"", "附件", "图片", "图", "PDF", "pdf", "见", "详见", "参见"}


def strip_local_attachment_refs(text: str) -> str:
    """Drop local attachment links before pandoc conversion.

    External knowledge links are retained. Local PDF/image attachment links are
    audited separately and should not clutter the text-only draft as literal
    ``Document.pdf`` hyperlinks.
    """
    out: list[str] = []
    for line in text.split("\n"):
        refs = iter_markdown_refs(line)
        if not refs:
            out.append(line)
            continue

        pieces: list[str] = []
        cursor = 0
        removed = False
        for ref in refs:
            pieces.append(line[cursor:ref.start])
            if is_local_attachment(ref.target):
                removed = True
            else:
                pieces.append(line[ref.start:ref.end])
            cursor = ref.end
        pieces.append(line[cursor:])
        cleaned = "".join(pieces).rstrip()
        if removed and _attachment_residual_is_empty(cleaned):
            continue
        out.append(cleaned)
    return "\n".join(out)


def normalize_practice_headings(text: str) -> str:
    """Clean source-specific OSCE heading marks without changing raw notes."""
    lines = text.split("\n")
    heading = re.compile(r"^(#{1,6})(\s+)(.+?)\s*$")
    for i, line in enumerate(lines):
        m = heading.match(line)
        if not m:
            continue
        title = m.group(3).replace("**", "")
        title = title.replace("*", "")
        title = re.sub(r"\s+", " ", title).strip()
        title = PRACTICE_D_HEADINGS.get(title, title)
        lines[i] = f"{m.group(1)}{m.group(2)}{title}"
    return "\n".join(lines)


def normalize_practice_score_marks(text: str) -> str:
    """Convert OSCE scoring marks like （7.5‘） or （7+11+3=21’） to Chinese text."""
    score = re.compile(r"[（(]\s*([^）)\n]{0,40}\d[^）)\n]{0,40}?)\s*[`'‘’′]\s*[）)]")
    return score.sub(lambda m: f"（{m.group(1).strip()}分）", text)


def normalize_doc(doc: SourceDoc) -> str:
    text = doc.path.read_text(encoding="utf-8")
    text = strip_local_attachment_refs(text)
    text = normalize_text(text)
    text = normalize_extra_text(text)
    if doc.group == "practice":
        text = normalize_practice_score_marks(text)
        text = normalize_practice_headings(text)
    text = normalize_headings(text)
    text = drop_empty_headings(text)
    text = tighten_lists(text)
    text = normalize_clinical_heading_depth(text)
    text = normalize_top_level_ordered_lists(text)
    return text


def run_pandoc(src: Path, dst: Path) -> None:
    subprocess.run(
        ["pandoc", str(src), "-f", "gfm-strikeout", "-t", "latex", "--wrap=none",
         "--syntax-highlighting=none", "-o", str(dst)],
        check=True,
    )


def tidy_surgery_burn(body: str) -> str:
    """外科总论·烧伤：中国九分法要点(+省略图位) → figBurnRule 面板(要点双栏+占比表)；
    严重性分度表 → 就地内联 strip，避免全宽浮动孤占一页。"""
    body = re.sub(
        r"\\subsection\{1\. 烧伤面积计算：中国九分法\}.*?% \[未映射图片已删除\]\n",
        "\\\\figBurnRule\n",
        body, count=1, flags=re.DOTALL)
    body = re.sub(
        r"\\begin\{table\*\}\[t\]\\centering\\sffamily\\small\n(\\begin\{mtbl\}.*?特重.*?\\end\{mtbl\})\n\\end\{table\*\}",
        r"\\begin{strip}\\centering\\sffamily\\small\n\1\n\\end{strip}",
        body, count=1, flags=re.DOTALL)
    return body


def convert_doc(doc: SourceDoc) -> None:
    norm_path = HERE / "norm" / doc.group / doc.filename
    raw_path = HERE / "raw" / doc.group / f"{doc.title}.tex"
    body_path = doc_body_path(doc)
    _write(norm_path, normalize_doc(doc))
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    run_pandoc(norm_path, raw_path)
    body = convert.postprocess(raw_path.read_text(encoding="utf-8"), {})
    if doc.title == "外科总论":
        body = tidy_surgery_burn(body)
    body = sanitize_generated_tex(body)
    _write(body_path, body)
    print(f"{doc.group} converted: {doc.title}")


def doc_body_path(doc: SourceDoc) -> Path:
    return HERE / "body" / doc.group / f"{doc.title}.tex"


def course_sections(tex: str) -> str:
    tex = COURSE_DIV_RE.sub("", tex)
    tex = SECTION_RE.sub(r"\\coursesection{", tex)
    tex = SUBSECTION_RE.sub(r"\\coursesubsection{", tex)
    tex = SUBSUBSECTION_RE.sub(r"\\coursesubsubsection{", tex)
    tex = PARAGRAPH_RE.sub(r"\\courseparagraph{", tex)
    return tex


def rd(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_attachment_audit(records: list[dict[str, str | int]]) -> None:
    by_source: dict[str, int] = {}
    for r in records:
        by_source[str(r["source_title"])] = by_source.get(str(r["source_title"]), 0) + 1

    lines = [
        "# 图片附件待处理清单",
        "",
        "首版整合 PDF 不纳入任何本地位图或 PDF 附件。以下引用均已从正文省略；后续只将能可靠重绘为 TikZ、tabularray 或其他 LaTeX 矢量元素的图片，或能转写为文字/表格的 PDF 附件纳入正文。",
        "",
        "## 按来源统计",
        "",
    ]
    for title, count in sorted(by_source.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append(f"- {title}: {count} 处")
    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| 来源 | 行号 | 类型 | 路径 | 文件存在 | 首版处理 |",
            "|---|---:|---|---|---|---|",
        ]
    )
    for r in records:
        target = str(r["target"]).replace("|", r"\|")
        action = str(r["action"]).replace("|", r"\|")
        lines.append(
            f"| {r['source_file']} | {r['line']} | {r['kind']} | `{target}` | {r['exists']} | {action} |"
        )
    text = "\n".join(lines) + "\n"
    _write(ROOT / "图片附件待处理清单.md", text)
    _write(ROOT / "临床图片待矢量化清单.md", text)
    print(f"attachment audit: {len(records)} references -> {ROOT / '图片附件待处理清单.md'}")


def ensure_anesthesia_bodies() -> None:
    missing = [
        ANES_BUILD / "body" / filename
        for _, filename in ANESTHESIA_CHAPTERS
        if not (ANES_BUILD / "body" / filename).exists()
    ]
    missing += [
        p
        for p in (ANES_BUILD / "body" / "题库.tex", ANES_BUILD / "body" / "附录_修订日记.tex")
        if not p.exists()
    ]
    if missing:
        raise FileNotFoundError("Missing anesthesia build bodies: " + ", ".join(str(p) for p in missing))


HEAD = r"""% !TEX program = xelatex
% ============================================================
%  医学课程笔记整合（基础医学 + 临床医学 + 实践技能 + 麻醉专科）
%  编译：xelatex 医学课程整合.tex （两遍，生成目录与页码）
%  首版策略：Markdown 文字纳入；本地位图/PDF 附件待矢量化或转写后择要纳入
%  附件策略：正文不得包含位图；可纳入的图必须由 TikZ / 表格等矢量方式重绘
% ============================================================
\documentclass[a4paper,10pt,twocolumn,oneside,openany,fontset=mac,UTF8]{ctexbook}

"""

TITLE = r"""
\begin{document}
\begin{titlepage}\centering\vspace*{4.5cm}
{\sffamily\bfseries\fontsize{40}{48}\selectfont\color{headchap} 医学课程笔记整合}\\[1.2cm]
{\sffamily\Large\color{headtealD} 临床执业医师 · 课程笔记整理}\\[0.4cm]
{\sffamily\normalsize\color{black!60} 基础医学 ｜ 临床医学 ｜ 实践技能 ｜ 麻醉专科}\par
\vfill {\small\color{black!50} 首版：Markdown 文字整合；本地图片/PDF 附件待矢量化或转写后择要纳入}\par\vspace*{1cm}
\end{titlepage}

\frontmatter
\onecolumn
\tableofcontents
\mainmatter

\volpart{基础医学}
%BASIC%

\volpart{临床医学}
%CLINICAL_SYSTEMS%

\volpart{临床专题与速记}
%CLINICAL_TOPICS%

\volpart{实践技能}
%PRACTICE%

\volpart{麻醉专科}
%ANESTHESIA%

\appendix
\volpart{附录甲 · 选择题库}
%QBANK%

\volpart{附录乙 · 修订日记}
\onecolumn
%CHANGELOG%

\end{document}
"""


def assemble() -> None:
    ensure_anesthesia_bodies()
    doc = HEAD + rd(ROOT / "preamble.tex") + "\n" + rd(ROOT / "figures.tex") + "\n"
    body = TITLE

    basic_parts: list[str] = []
    for source in BASIC_DOCS:
        basic_parts.append(
            f"\\coursechapter{{{source.title}}}\n"
            + course_sections(rd(doc_body_path(source)))
        )
    body = body.replace("%BASIC%", "\n\n".join(basic_parts))

    clinical_system_parts: list[str] = []
    for source in CLINICAL_SYSTEMS:
        clinical_system_parts.append(
            f"\\coursechapter{{{source.title}}}\n"
            + course_sections(rd(doc_body_path(source)))
        )
    body = body.replace("%CLINICAL_SYSTEMS%", "\n\n".join(clinical_system_parts))

    topic_parts: list[str] = []
    for source in CLINICAL_TOPICS:
        topic_parts.append(
            f"\\coursechapter{{{source.title}}}\n"
            + course_sections(rd(doc_body_path(source)))
        )
    body = body.replace("%CLINICAL_TOPICS%", "\n\n".join(topic_parts))

    practice_parts: list[str] = []
    for source in PRACTICE_DOCS:
        practice_parts.append(
            f"\\coursechapter{{{source.title}}}\n"
            + course_sections(rd(doc_body_path(source)))
        )
    body = body.replace("%PRACTICE%", "\n\n".join(practice_parts))

    anesthesia_parts: list[str] = []
    for title, filename in ANESTHESIA_CHAPTERS:
        anesthesia_parts.append(
            f"\\coursechapter{{{title}}}\n"
            + course_sections(rd(ANES_BUILD / "body" / filename))
        )
    body = body.replace("%ANESTHESIA%", "\n\n".join(anesthesia_parts))
    body = body.replace("%QBANK%", rd(ANES_BUILD / "body" / "题库.tex"))
    body = body.replace("%CHANGELOG%", rd(ANES_BUILD / "body" / "附录_修订日记.tex"))

    out = ROOT / "医学课程整合.tex"
    doc += body
    doc = sanitize_final_tex(doc)
    _write(out, doc)
    print(f"assembled: {out} ({len(doc)} chars, {doc.count(chr(10))} lines)")


def main() -> None:
    for generated in ("norm", "raw", "body"):
        shutil.rmtree(HERE / generated, ignore_errors=True)
    for sub in (
        "norm/basic",
        "norm/clinical",
        "norm/practice",
        "raw/basic",
        "raw/clinical",
        "raw/practice",
        "body/basic",
        "body/clinical",
        "body/practice",
    ):
        (HERE / sub).mkdir(parents=True, exist_ok=True)

    all_sources = BASIC_DOCS + CLINICAL_SYSTEMS + CLINICAL_TOPICS + PRACTICE_DOCS
    attachment_records: list[dict[str, str | int]] = []
    for source in all_sources:
        attachment_records.extend(scan_attachments(source))
        convert_doc(source)

    write_attachment_audit(attachment_records)
    assemble()


if __name__ == "__main__":
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    os.environ.update(env)
    main()
