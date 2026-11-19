"""Build the redistributable teaching example. No model/network/account needed."""
import json
import sys
from pathlib import Path

import pymupdf as fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from highsc.renderer import render_html


def build():
    folder = ROOT / 'examples'
    folder.mkdir(exist_ok=True)
    content = json.loads((folder / 'demo_content.json').read_text(encoding='utf-8'))
    paragraphs, notes, sections = [], {}, []
    pdf = fitz.open()
    for i, item in enumerate(content['sections']):
        page = pdf.new_page(width=612, height=792)
        page.insert_text((48, 48), 'High_SC | Original teaching example', fontsize=10)
        page.insert_text((48, 80), item['en'], fontsize=17)
        page.insert_textbox((48, 118, 564, 710), '\n\n'.join(p['en'] for p in item['paragraphs']), fontsize=12, lineheight=1.5)
        page.insert_text((48, 755), 'Illustrative text only. No experiment or empirical dataset is reported.', fontsize=9)
        sid = f'section-{i+1:02d}'
        sections.append({'id':sid, 'en':item['en'], 'zh':item['zh']})
        for row in item['paragraphs']:
            pid = f'p{len(paragraphs)+1:03d}'
            paragraphs.append({'id':pid, 'en':row['en'], 'pages':[i+1], 'section_id':sid})
            notes[pid] = {**row['note'], 'id':pid, 'support_quotes':[], 'warnings':[], 'review_flags':[]}
    pdf.set_metadata({'title':content['title'], 'author':'High_SC contributors', 'subject':'Original fictional teaching example'})
    pdf.save(folder / 'source.pdf', deflate=True)
    pdf.close()
    parsed = {'title':content['title'], 'page_count':len(sections), 'sections':sections,
              'paragraphs':paragraphs, 'assets':[], 'references':[], 'warnings':[]}
    outline = content['outline']
    outline['sections'] = [{'id':s['id'],'zh':s['zh'],'logic':content['sections'][i]['logic']} for i,s in enumerate(sections)]
    path = render_html(folder, parsed, outline, notes)
    target = folder / 'demo.html'
    path.replace(target)
    print(f'Built {target.name}: {len(paragraphs)} paragraphs; original teaching content only.')


if __name__ == '__main__': build()
