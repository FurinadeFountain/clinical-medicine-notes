#!/usr/bin/env python3
"""医学课程整合.tex → 纯净 Markdown 转换器。
针对本项目自定义命令做逆向映射；产出 GitHub(GFM) 可渲染 md：标题、列表、GFM 表、$...$ 数学。
按 卷(volpart)/章(coursechapter) 拆分为多文件。
"""
from __future__ import annotations
import re
from pathlib import Path

SRC = Path("/Volumes/SamsungT9/CoWork/医学课程内容整理/00-LaTeX输出/医学课程整合/医学课程整合.tex")

# ---------- 数学保护 ----------
def protect_math(t, store):
    def repl_disp(m):
        store.append(("$$", m.group(1).strip())); return f"\x00M{len(store)-1}\x00"
    def repl_inl(m):
        store.append(("$", m.group(1).strip())); return f"\x00M{len(store)-1}\x00"
    t = re.sub(r"\\\[(.+?)\\\]", repl_disp, t, flags=re.S)
    t = re.sub(r"\\\((.+?)\\\)", repl_inl, t, flags=re.S)
    return t

def restore_math(t, store):
    def repl(m):
        kind, body = store[int(m.group(1))]
        if kind == "$$":
            return f"\n\n$$\n{body}\n$$\n\n"
        return f"${body}$"
    return re.sub(r"\x00M(\d+)\x00", repl, t)

# ---------- 行内命令 ----------
def inline(t):
    # 保护字面花括号
    t = t.replace("\\{", "\x00LB\x00").replace("\\}", "\x00RB\x00")
    # 样式标题 {\sffamily\bfseries\color{x} TEXT} -> **TEXT**
    t = re.sub(r"\{(?:\\(?:sffamily|bfseries|small|footnotesize|scriptsize|centering)\s*)*\\color\{[^}]*\}\s*([^{}]+)\}", r"**\1**", t)
    # 全局去颜色/字体声明
    t = re.sub(r"\\color\{[^}]*\}", "", t)
    t = t.replace("\\&", "&").replace("\\%", "%").replace("\\#", "#").replace("\\_", "_").replace("\\$", "$")
    t = t.replace("\\textbackslash", "\\")
    t = re.sub(r"\\textgreater\{?\}?", ">", t)
    t = re.sub(r"\\textless\{?\}?", "<", t)
    t = re.sub(r"\\textquotesingle\s*", "'", t)
    t = t.replace("{[}", "[").replace("{]}", "]")
    t = re.sub(r"\\textendash\{?\}?", "–", t)
    t = re.sub(r"\\textemdash\{?\}?", "—", t)
    t = re.sub(r"\\textperthousand\{?\}?", "‰", t)
    t = re.sub(r"\\textbullet\{?\}?", "•", t)
    t = re.sub(r"\\textdegree\{?\}?", "°", t)
    # 强调/上下标 (允许一层嵌套)
    def grp(name, fmt):
        nonlocal t
        pat = re.compile(r"\\" + name + r"\{((?:[^{}]|\{[^{}]*\})*)\}")
        prev = None
        while prev != t:
            prev = t; t = pat.sub(lambda m: fmt.format(m.group(1)), t)
    grp("textbf", "**{0}**")
    grp("textit", "*{0}*")
    grp("emph", "*{0}*")
    grp("textsubscript", "<sub>{0}</sub>")
    grp("textsuperscript", "<sup>{0}</sup>")
    grp("texttt", "`{0}`")
    grp("mbox", "{0}")
    # texorpdfstring{A}{B} -> A
    t = re.sub(r"\\texorpdfstring\{((?:[^{}]|\{[^{}]*\})*)\}\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", t)
    # 颜色/字体包裹 {\sffamily\bfseries\color{x} TEXT} -> **TEXT**
    t = re.sub(r"\{\\(?:sffamily|bfseries|small|footnotesize|centering|color\{[^}]*\})[\\a-zA-Z\s]*\s+([^{}]*)\}",
               r"**\1**", t)
    # 残留简单字体声明
    t = re.sub(r"\\(?:sffamily|bfseries|itshape|footnotesize|small|normalsize|centering|tightlist|par|smallskip|medskip|bigskip|noindent|nobreak|onecolumn|twocolumn|thispagestyle\{[^}]*\}|appendix)\b", "", t)
    t = re.sub(r"\\addvspace\{[^}]*\}", "", t)
    t = re.sub(r"\\hspace\*?\{[^}]*\}", " ", t)
    t = re.sub(r"\\vspace\*?\{[^}]*\}", "", t)
    # 连字符/省略号
    t = t.replace("---", "—").replace("--", "–")
    t = re.sub(r"\\dots|\\ldots|\\cdots", "…", t)
    t = re.sub(r"\\,|\\;|\\:|\\!", "", t)   # 数学外残留细空格(罕见)
    t = t.replace("~", " ")
    # 残留 \命令{..} 兜底：去命令留参数
    t = re.sub(r"\\[a-zA-Z]+\*?\{((?:[^{}]|\{[^{}]*\})*)\}", r"\1", t)
    t = re.sub(r"\\[a-zA-Z]+", "", t)
    # 清残留分组花括号(数学已占位保护), 再还原字面括号
    t = t.replace("{", "").replace("}", "")
    t = t.replace("\x00LB\x00", "{").replace("\x00RB\x00", "}")
    return t

# ---------- 表格 ----------
def conv_table(body):
    # 去 booktabs 线与 tabularray 内部命令行
    body = re.sub(r"\\(toprule|midrule|bottomrule|hline|cmidrule\([^)]*\)\{[^}]*\}|cmidrule\{[^}]*\}|SetCell\{[^}]*\}|SetRow\{[^}]*\})", "", body)
    rows_raw = [r.strip() for r in body.split("\\\\") if r.strip()]
    rows = []
    for r in rows_raw:
        if "&" not in r:  # 跳过无单元格的样式/残留行
            continue
        cells = [inline(c.strip()) for c in r.split("&")]
        rows.append(cells)
    if not rows:
        return ""
    ncol = max(len(r) for r in rows)
    rows = [r + [""] * (ncol - len(r)) for r in rows]
    out = []
    out.append("| " + " | ".join(rows[0]) + " |")
    out.append("|" + "|".join(["---"] * ncol) + "|")
    for r in rows[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)

def extract_tables(t, store):
    # 括号配平解析 spec(可含嵌套{}), 再捕获到 \end
    pat = re.compile(r"\\begin\{(longtblr|tblr|mtbl)\}")
    out = []; i = 0
    while True:
        m = pat.search(t, i)
        if not m:
            out.append(t[i:]); break
        out.append(t[i:m.start()])
        j = m.end()
        while j < len(t) and t[j] in " \n\t": j += 1
        # 消费配平的 {spec}
        depth = 0; k = j
        while k < len(t):
            if t[k] == "{": depth += 1
            elif t[k] == "}":
                depth -= 1
                if depth == 0: k += 1; break
            k += 1
        endm = re.search(r"\\end\{" + m.group(1) + r"\}", t[k:])
        inner = t[k:k + endm.start()]
        store.append(("TBL", conv_table(inner)))
        out.append(f"\n\n\x00T{len(store)-1}\x00\n\n")
        i = k + endm.end()
    return "".join(out)

def restore_tables(t, store):
    return re.sub(r"\x00T(\d+)\x00", lambda m: store[int(m.group(1))][1], t)

# ---------- 列表 ----------
def conv_lists(t):
    lines = t.split("\n")
    out = []
    stack = []  # [{'type':'ul'|'ol'|'ch','count':int}]
    buf = None
    def flush():
        nonlocal buf
        if buf is not None:
            depth = max(0, len(stack) - 1); ind = "  " * depth
            lvl = stack[-1] if stack else None
            text = " ".join(p.strip() for p in buf if p.strip())
            if lvl and lvl['type'] == 'ch':
                lvl['count'] += 1; mark = chr(ord('A') + lvl['count'] - 1) + "."
            elif lvl and lvl['type'] == 'ol':
                mark = "1."
            else:
                mark = "-"
            out.append(f"{ind}{mark} {text}".rstrip())
            buf = None
    for line in lines:
        s = line.strip()
        mb = re.match(r"\\begin\{(itemize|enumerate|choices)\}", s)
        me = re.match(r"\\end\{(itemize|enumerate|choices)\}", s)
        if mb:
            flush()
            typ = {'enumerate': 'ol', 'choices': 'ch', 'itemize': 'ul'}[mb.group(1)]
            stack.append({'type': typ, 'count': 0}); continue
        if me:
            flush()
            if stack: stack.pop()
            out.append(""); continue
        if s.startswith("\\item"):
            flush(); buf = [s[len("\\item"):].strip()]; continue
        if buf is not None:
            if s == "":
                continue
            buf.append(s); continue
        out.append(line)
    flush()
    return "\n".join(out)

# ---------- 题库 ----------
def conv_qbank(t):
    t = re.sub(r"\\qitem\{([^{}]*)\}\{((?:[^{}]|\{[^{}]*\})*)\}", r"\n\n**\1.** \2\n", t)
    t = re.sub(r"\\ans\{((?:[^{}]|\{[^{}]*\})*)\}", r"\n\n> **答案：\1**\n", t)
    t = re.sub(r"\\qreview\{((?:[^{}]|\{[^{}]*\})*)\}", r"\n> 疑点：\1\n", t)
    return t

# ---------- 标题 ----------
HEAD = {
    "coursechapter": "# ", "coursesection": "## ", "coursesubsection": "### ",
    "coursesubsubsection": "#### ", "courseparagraph": "##### ", "coursegroup": "### ",
}
def conv_headings(t):
    for cmd, h in HEAD.items():
        t = re.sub(r"\\" + cmd + r"\{((?:[^{}]|\{[^{}]*\})*)\}", lambda m, h=h: f"\n{h}{m.group(1)}\n", t)
    t = re.sub(r"\\coursediv\b", "\n---\n", t)
    t = re.sub(r"\\courseornament\b", "", t)
    return t

# ---------- 杂项环境 ----------
def strip_envs(t):
    # tikzpicture/figure -> 占位说明 (先处理, 含其内部 scope 等)
    t = re.sub(r"\\begin\{figure\*?\}(?:\[[^\]]*\])?.*?\\end\{figure\*?\}", "\n\n*（图示，见 PDF 版）*\n\n", t, flags=re.S)
    t = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", "\n\n*（图示，见 PDF 版）*\n\n", t, flags=re.S)
    # supplbox(知识选读) -> blockquote
    t = re.sub(r"\\begin\{supplbox\}(?:\[[^\]]*\])?(.*?)\\end\{supplbox\}",
               lambda m: "\n> **【选读】**\n" + "\n".join("> " + ln.strip() for ln in m.group(1).strip().split("\n") if ln.strip()) + "\n",
               t, flags=re.S)
    # 浮动/容器环境壳 -> 去壳留内容
    t = re.sub(r"\\begin\{(?:table\*?|center|strip|minipage(?:\}\{[^}]*\})?|list\}\{[^}]*\}\{[^}]*\})\}?(?:\[[^\]]*\])?(?:\{[^}]*\})?", "", t)
    t = re.sub(r"\\begin\{(?:table\*?|center|strip|minipage|list)\}(?:\[[^\]]*\])?(?:\{[^}]*\})*", "", t)
    t = re.sub(r"\\end\{(?:table\*?|center|strip|minipage|list)\}", "", t)
    t = re.sub(r"\\(?:toprule|midrule|bottomrule)\b", "", t)
    # quote -> blockquote
    def quote_repl(m):
        inner = m.group(1).strip()
        return "\n" + "\n".join("> " + ln if ln.strip() else ">" for ln in inner.split("\n")) + "\n"
    t = re.sub(r"\\begin\{quote\}(.*?)\\end\{quote\}", quote_repl, t, flags=re.S)
    # tcolorbox -> blockquote (note)
    t = re.sub(r"\\begin\{tcolorbox\}(?:\[[^\]]*\])?(.*?)\\end\{tcolorbox\}",
               lambda m: "\n> [!NOTE]\n" + "\n".join("> " + ln.strip() for ln in m.group(1).strip().split("\n") if ln.strip()) + "\n",
               t, flags=re.S)
    # noteblock{...}
    t = re.sub(r"\\noteblock\{((?:[^{}]|\{[^{}]*\})*)\}", lambda m: f"\n> {m.group(1)}\n", t, flags=re.S)
    # 去 def/label/setcounter/nmbar 等
    t = re.sub(r"\\def\\labelenum[a-z]+\{(?:[^{}]|\{[^{}]*\})*\}", "", t)
    t = re.sub(r"\\arabic\{[^}]*\}|\\roman\{[^}]*\}|\\alph\{[^}]*\}", "", t)
    t = re.sub(r"\\setcounter\{[^}]*\}\{[^}]*\}", "", t)
    t = re.sub(r"\\nmbar\{[^}]*\}", "", t)
    t = re.sub(r"\\(?:painsection|disciplinechapter)\{((?:[^{}]|\{[^{}]*\})*)\}", r"\n### \1\n", t)
    return t

def cleanup(t):
    t = re.sub("…{2,}", "…", t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip() + "\n"

def convert_chapter(tex):
    store_m, store_t = [], []
    t = tex
    t = protect_math(t, store_m)
    t = extract_tables(t, store_t)
    t = strip_envs(t)
    t = conv_qbank(t)
    t = conv_headings(t)
    t = conv_lists(t)
    t = inline(t)
    t = restore_tables(t, store_t)
    t = restore_math(t, store_m)
    t = cleanup(t)
    return t

def main():
    raw = SRC.read_text(encoding="utf-8")
    body = raw.split("\\begin{document}", 1)[1].split("\\end{document}", 1)[0]
    # 拆分: 记录每个 volpart / coursechapter 位置
    toks = []
    for m in re.finditer(r"\\(volpart|coursechapter)\{((?:[^{}]|\{[^{}]*\})*)\}", body):
        toks.append((m.start(), m.group(1), m.group(2)))
    chapters = []  # (vol, title, text)
    curvol = "未分卷"
    for i, (pos, kind, title) in enumerate(toks):
        end = toks[i + 1][0] if i + 1 < len(toks) else len(body)
        seg = body[pos:end]
        if kind == "volpart":
            curvol = title
            seg2 = re.sub(r"^\\volpart\{[^}]*\}", "", seg, count=1)
            if len(seg2.strip()) > 200:  # 附录(题库/修订日记)直接承载内容
                chapters.append((title, title, seg2))
            continue
        seg = re.sub(r"^\\coursechapter\{[^}]*\}", "", seg, count=1)
        chapters.append((curvol, title, seg))
    print(f"卷/章解析: {len(chapters)} 章")
    return chapters, convert_chapter

if __name__ == "__main__":
    chapters, conv = main()
    # 测试: 简明统计学
    for vol, title, seg in chapters:
        if title == "简明统计学与流行病学":
            md = conv(seg)
            Path("/tmp/test_stat.md").write_text(f"<!-- {vol} -->\n\n" + md, encoding="utf-8")
            print("已写 /tmp/test_stat.md  长度", len(md))
            break
