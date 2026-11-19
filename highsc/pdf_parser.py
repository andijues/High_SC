from __future__ import annotations

import collections
import re
import shutil
from pathlib import Path

import pymupdf as fitz


CAPTION = re.compile(r"^(?:(?:Fig(?:ure)?\.?|Table|TABLE)\s*(?:[IVXLC]+|\d+)[.:\s])")
SECTION = re.compile(r"^(?:[IVXLC]+\.|\d+(?:\.\d+)*\.?)[ \t]+[A-Z]")
SUBSECTION = re.compile(r"^[A-Z]\.[ \t]+[A-Z]")
PREFIXES = {"pre", "post", "intra", "inter", "multi", "single", "non", "self", "cross", "llm", "agent", "long", "short", "task", "tool", "model", "fine", "rule", "evidence", "context", "closed", "step", "end", "real", "two", "three", "open", "deepseek", "api", "high", "low"}


def normalize(text: str) -> str:
    def join(m):
        left, right = m.group(1), m.group(2)
        return left + ("-" if left.lower() in PREFIXES else "") + right
    text = text.replace("\u00ad", "").replace("\ufb01", "fi").replace("\ufb02", "fl")
    return " ".join(re.sub(r"(\w+)-\s*\n\s*(\w+)", join, text).split())


def block_text(block):
    return normalize("\n".join("".join(s["text"] for s in line["spans"]) for line in block.get("lines", [])))


def body_font(pages):
    counts = collections.Counter()
    for page in pages:
        for b in page["blocks"]:
            for line in b.get("lines", []):
                for s in line["spans"]:
                    if 7 <= s["size"] <= 16:
                        counts[round(s["size"], 1)] += len(s["text"])
    return counts.most_common(1)[0][0] if counts else 10


def order_blocks(blocks, width):
    left = [b for b in blocks if b["bbox"][0] < width * .3 and b["bbox"][2] < width * .56]
    right = [b for b in blocks if b["bbox"][0] > width * .43]
    if len(left) < 2 or len(right) < 2:
        return sorted(blocks, key=lambda b: (b["bbox"][1], b["bbox"][0]))
    wide = [b for b in blocks if b["bbox"][0] < width * .3 and b["bbox"][2] > width * .7]
    result, rest = [], list(blocks)
    for wide_b in sorted(wide, key=lambda b: b["bbox"][1]):
        before = [b for b in rest if b is not wide_b and b["bbox"][3] <= wide_b["bbox"][1] + 2]
        result.extend(sorted(before, key=lambda b: (b["bbox"][0] > width*.43, b["bbox"][1])))
        result.append(wide_b)
        used = {id(b) for b in before + [wide_b]}
        rest = [b for b in rest if id(b) not in used]
    result.extend(sorted(rest, key=lambda b: (b["bbox"][0] > width*.43, b["bbox"][1])))
    return result


def parse_pdf(pdf_path: Path, output: Path, ocr=False) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    assets_dir = output / "assets"
    assets_dir.mkdir(exist_ok=True)
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        raise ValueError('无法读取 PDF，请确认文件完整、未损坏且没有加密限制') from None
    if doc.needs_pass:
        raise ValueError("PDF 有密码保护，请先解锁后再导入")
    if not 1 <= len(doc) <= 250:
        raise ValueError("当前支持 1-250 页 PDF，请拆分过长文件")
    pages, warnings, repeated = [], [], collections.Counter()
    for i, page in enumerate(doc):
        if len(page.get_text().strip()) < 50:
            if not ocr:
                warnings.append(f"第 {i+1} 页文字很少，可能为扫描页；未启用 OCR")
            else:
                if not shutil.which("tesseract"):
                    raise ValueError("启用 OCR 需要先安装 Tesseract 并加入 PATH")
                tp = page.get_textpage_ocr(language="eng", dpi=200)
                d = page.get_text("dict", textpage=tp)
                pages.append(d)
                continue
        d = page.get_text("dict", flags=fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES)
        pages.append(d)
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            if b["bbox"][1] < page.rect.height*.07 or b["bbox"][1] > page.rect.height*.94:
                repeated[re.sub(r"\d+", "#", block_text(b))] += 1
    font = body_font(pages)
    sections, paragraphs, assets, references = [], [], [], []
    title_parts, section_id, reference_mode, subheading = [], None, False, ""
    pending_heading = False
    for pi, (page, d) in enumerate(zip(doc, pages)):
        width, height = page.rect.width, page.rect.height
        blocks = [b for b in d["blocks"] if b.get("type") == 0 and b.get("lines")]
        for b in blocks:
            b["text"] = block_text(b)
            spans = [s for l in b["lines"] for s in l["spans"]]
            b["size"] = max((s["size"] for s in spans), default=font)
            b["mean_size"] = sum(s["size"] * len(s["text"]) for s in spans) / max(1, sum(len(s["text"]) for s in spans))
        usable = []
        for b in blocks:
            t, box = b["text"], b["bbox"]
            if not t or re.fullmatch(r"\d+", t):
                continue
            if box[0] < width*.075 and box[2] < width*.08:
                continue
            repeated_key = re.sub(r"\d+", "#", t)
            if repeated[repeated_key] >= max(2, len(doc)*.25) and (box[1] < height*.08 or box[1] > height*.93):
                continue
            if pi == 0 and b["size"] >= font*1.55 and box[1] < height*.3:
                title_parts.append(t)
                continue
            usable.append(b)
        def is_caption(b):
            if not CAPTION.match(b['text']):return False
            # Body paragraphs such as "Table III demonstrates ..." are not captions.
            return b['mean_size']<font*.94 or bool(re.match(r'^(?:Fig(?:ure)?\.?|Table)\s*(?:[IVXLC]+|\d+)[.:]',b['text']))
        captions = [b for b in usable if is_caption(b)]
        first_body_candidates=[b['bbox'][1] for b in usable if re.match(r'^Abstract\b|^Introduction$',b['text'],re.I) or SECTION.match(b['text'])]
        first_body_y=min(first_body_candidates) if first_body_candidates else height*.12
        tables = []
        # Detection is optional: source-page crops preserve unusual tables as well.
        if any(re.match(r"^(?:Table|TABLE)", b["text"]) for b in captions):
            try:
                tables = [fitz.Rect(t.bbox) for t in page.find_tables().tables]
            except Exception:
                warnings.append(f"第 {pi+1} 页表格结构检测未成功，保留原页图像以便核对")
        body_candidates = [b for b in usable if not is_caption(b) and ((b["mean_size"] >= font*.94 and len(b["text"]) > 45) or SECTION.match(b['text']) or SUBSECTION.match(b['text']))]
        regions = []
        for cap in captions:
            cb = fitz.Rect(cap["bbox"])
            full = cb.width > width*.65
            left = width*.075 if full or cb.x0 < width*.43 else width*.505
            right = width*.925 if full or cb.x0 > width*.43 else width*.495
            same = lambda b: b["bbox"][0] < right and b["bbox"][2] > left + 20
            is_table = bool(re.match(r"^(?:Table|TABLE)", cap["text"]))
            if is_table:
                matches = [t for t in tables if t.y0 >= cb.y0 and t.y0-cb.y1 < height*.24 and t.x0 < right and t.x1 > left]
                if matches:
                    table = min(matches, key=lambda t: t.y0)
                    bottom = table.y1 + 6
                    footnotes = [b for b in usable if same(b) and table.y1 <= b["bbox"][1] <= table.y1+28 and b["mean_size"] < font*.94 and re.match(r'^(?:Note\.|Term\.=|Sec\.=|Reas\.=)',b['text'])]
                    if footnotes:
                        bottom = max(bottom, max(b["bbox"][3] for b in footnotes)+4)
                    right = max(right, table.x1+2)
                else:
                    following = [b["bbox"][1] for b in body_candidates if same(b) and b["bbox"][1] > cb.y1+3]
                    next_caps = [b["bbox"][1]-8 for b in captions if same(b) and b["bbox"][1] > cb.y1+3]
                    bottom = min(following + next_caps + [height*.95])-5
                following_headings=[b['bbox'][1]-5 for b in body_candidates if same(b) and b['bbox'][1]>cb.y1+3]
                if following_headings:bottom=min(bottom,min(following_headings))
                top = cb.y0-4
            else:
                above = [b["bbox"][3] for b in body_candidates if same(b) and b["bbox"][3] < cb.y0-4]
                prev_caps = [b["bbox"][3] for b in captions if same(b) and b["bbox"][3] < cb.y0-4]
                prior_regions=[r.y1 for r,_ in regions if r.y1<cb.y0-4 and r.x0<right and r.x1>left]
                top = max(above + prev_caps + prior_regions + [height*.065])+5
                bottom = cb.y1+4
            rect = fitz.Rect(max(0,left-2), max(0,top), min(width,right+2), min(height,bottom))
            if rect.height < 28:
                warnings.append(f"第 {pi+1} 页 {cap['text'][:25]} 裁切范围较小，建议核对原页")
                continue
            aid = f"asset-{len(assets)+1:03}"
            png = page.get_pixmap(matrix=fitz.Matrix(2,2), clip=rect, alpha=False)
            png.save(assets_dir / f"{aid}.png")
            label = re.match(r"^((?:Fig(?:ure)?\.?|Table|TABLE)\s*(?:[IVXLC]+|\d+))", cap["text"])[1]
            asset = {"id":aid,"kind":"table" if is_table else "figure","label":label,"en":cap["text"],"source_text":normalize(page.get_text(clip=rect,sort=True))[:14000],"page":pi+1,"rect":list(rect),"image":f"assets/{aid}.png","after":"","zh":"","function":"","logic":"","critique":"","tone":"method"}
            assets.append(asset)
            regions.append((rect, asset))
        for b in order_blocks(usable, width):
            t, box = b["text"], fitz.Rect(b["bbox"])
            if is_caption(b):
                if paragraphs:
                    for _, a in regions:
                        if a["en"] == t: a["after"] = paragraphs[-1]["id"]
                continue
            if any(r.contains(box.tl) and r.contains(box.br) for r, _ in regions):
                continue
            if re.fullmatch(r"REFERENCES|BIBLIOGRAPHY|References|Bibliography", t.strip()):
                reference_mode = True
                continue
            if reference_mode:
                references.append(t)
                continue
            if b['size']<font*.94 and b['mean_size']<font*.88:
                continue
            if pi == 0 and (box.y0 < first_body_y-2 or re.match(r"^(?:Corresponding author|This work was funded|Index Terms|Keywords|ACCEPTED BY|arXiv:)",t)):
                continue
            if re.fullmatch(r'Abstract|Introduction',t,re.I):
                section_id=f's{len(sections):02}'
                sections.append({'id':section_id,'en':t,'zh':'摘要' if t.lower()=='abstract' else '引言','logic':''})
                continue
            if pending_heading and not SECTION.match(t) and not SUBSECTION.match(t) and len(t)<120:
                letters=[c for c in t if c.isalpha()]
                if letters and sum(c.isupper() for c in letters)/len(letters)>.9:
                    sections[-1]['en']+=' '+t
                    continue
            pending_heading=False
            # Split headings that PDF producers merge into a body-text block.
            lines = [normalize("".join(s["text"] for s in l["spans"])) for l in b["lines"]]
            heading_lines = []
            for line in lines:
                letters = [c for c in line if c.isalpha()]
                upper = sum(c.isupper() for c in letters)/max(1,len(letters))
                if (heading_lines or SECTION.match(line)) and upper > .88 and len(line)<120:
                    heading_lines.append(line)
                else:
                    break
            if heading_lines:
                title = " ".join(heading_lines).removesuffix(" W")
                section_id = f"s{len(sections):02}"
                sections.append({"id":section_id,"en":title,"zh":"","logic":""})
                pending_heading=True
                t = normalize("\n".join(lines[len(heading_lines):]))
                subheading = ""
                if t == "W": t = ""
                if not t: continue
            if SUBSECTION.match(t) and len(t)<180 and len(lines)<=3:
                subheading = t
                continue
            is_abstract = bool(re.match(r"^Abstract\s*[—–:-]", t, re.I))
            if is_abstract:
                section_id="s00" if not sections else f"s{len(sections):02}"
                sections.append({"id":section_id,"en":"Abstract","zh":"摘要","logic":""})
                t=re.sub(r"^Abstract\s*[—–:-]\s*", "", t, flags=re.I)
            if section_id is None:
                section_id="s00";sections.append({"id":section_id,"en":"Main Text","zh":"正文","logic":""})
            if t.startswith("ITH the advent"): t="W"+t
            if not re.search(r"[A-Za-z]{3}",t) or len(t)<12: continue
            prev=paragraphs[-1] if paragraphs else None
            continued = prev and prev["section_id"]==section_id and not subheading and (t[0].islower() or not re.search(r'[.!?:;”"\)]$',prev["en"]))
            if continued:
                prev["en"]=normalize(prev["en"]+ ("\n" if prev["en"].endswith("-") else " ")+t)
                if pi+1 not in prev["pages"]:prev["pages"].append(pi+1)
                prev["source_boxes"].append({"page":pi+1,"rect":list(box)})
                continue
            paragraphs.append({"id":f"p{len(paragraphs)+1:04}","section_id":section_id,"subheading":subheading,"en":t,"pages":[pi+1],"source_boxes":[{"page":pi+1,"rect":list(box)}]})
            subheading=""
    if sum(len(p["en"]) for p in paragraphs)<100:
        raise ValueError("没有提取到足够正文。扫描件请启用 OCR，或换用带文字层的英文 PDF")
    # Every asset has an anchor even when a caption precedes the first paragraph.
    for a in assets:
        if not a["after"]:
            candidates=[p for p in paragraphs if p["pages"][0]<=a["page"]]
            a["after"]=(candidates[-1] if candidates else paragraphs[0])["id"]
    ref_text=" ".join(references)
    split=re.split(r"\[(\d{1,3})\]",ref_text)
    refs=[{"number":int(split[i]),"text":split[i+1].strip()} for i in range(1,len(split),2)]
    if not refs and ref_text:refs=[{"number":i+1,"text":t} for i,t in enumerate(references)]
    if not refs:warnings.append("未自动识别参考文献编号，内嵌原始 PDF 可供核对")
    if not assets:warnings.append("未识别到带 Fig./Table 图题的图表，导出仍包含完整原始 PDF")
    title=normalize(" ".join(title_parts)) or doc.metadata.get("title") or pdf_path.stem
    title=re.sub(r"\s+", " ",title)
    if len(title)>350:title=pdf_path.stem
    result={"title":title,"page_count":len(doc),"sections":sections,"paragraphs":paragraphs,"assets":assets,"references":refs,"warnings":warnings,"body_font":font,"parser_version":1}
    # Preserve a small visual proof of the source in the local workbench.
    doc[0].get_pixmap(matrix=fitz.Matrix(.7,.7), alpha=False).save(output/"cover.png")
    doc.close()
    return result
