"""Generate the original vector mark and matching PNG / Windows ICO."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'static/brand';OUT.mkdir(parents=True,exist_ok=True)
navy='#102839';paper='#fbf8f1';gold='#d2bb7a';line='#69808a'
svg='''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" role="img" aria-label="High_SC 双栏精读标志"><rect width="512" height="512" rx="88" fill="#102839"/><path d="M88 120 232 136 232 388 88 372Z M272 136 424 120 424 372 272 388Z" fill="#fbf8f1"/><g stroke="#69808a" stroke-width="10" stroke-linecap="round"><path d="M120 182 200 190 M120 222 200 230 M120 320 200 328 M304 182 388 174 M304 222 352 218 M304 326 350 322"/></g><path d="M120 270 210 280" stroke="#d2bb7a" stroke-width="18"/><path d="M252 152V394 M388 240V326" stroke="#d2bb7a" stroke-width="9" stroke-linecap="round"/><g fill="#d2bb7a"><circle cx="388" cy="240" r="13"/><circle cx="388" cy="283" r="13"/><circle cx="388" cy="326" r="13"/></g></svg>'''
(OUT/'icon.svg').write_text(svg,encoding='utf-8')
scale=3
img=Image.new('RGBA',(512*scale,512*scale));d=ImageDraw.Draw(img)
def pts(values):return [(int(x*scale),int(y*scale)) for x,y in values]
def stroke(points,fill,width):
    d.line(pts(points),fill=fill,width=width*scale)
    radius=width*scale/2
    for x,y in pts([points[0],points[-1]]):d.ellipse((x-radius,y-radius,x+radius,y+radius),fill=fill)
d.rounded_rectangle((0,0,512*scale-1,512*scale-1),radius=88*scale,fill=navy)
for p in [[(88,120),(232,136),(232,388),(88,372)],[(272,136),(424,120),(424,372),(272,388)]]:d.polygon(pts(p),fill=paper)
for p in [[(120,182),(200,190)],[(120,222),(200,230)],[(120,320),(200,328)],[(304,182),(388,174)],[(304,222),(352,218)],[(304,326),(350,322)]]:stroke(p,line,10)
stroke([(120,270),(210,280)],gold,18)
stroke([(252,152),(252,394)],gold,9);stroke([(388,240),(388,326)],gold,9)
for y in [240,283,326]:d.ellipse((375*scale,(y-13)*scale,401*scale,(y+13)*scale),fill=gold)
def save_raster(image,path):
    # Preserve provenance metadata when the generated pixels are unchanged.
    if path.exists():
        with Image.open(path) as old:
            if old.size==image.size and old.convert('RGBA').tobytes()==image.convert('RGBA').tobytes():return
    image.save(path)
img=img.resize((512,512),Image.Resampling.LANCZOS);save_raster(img,OUT/'icon.png');img.save(OUT/'High_SC.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
word=Image.new('RGBA',(1400,420),paper);word.alpha_composite(img.resize((280,280)),(70,70));draw=ImageDraw.Draw(word)
font=ImageFont.truetype(str(ROOT/'static/fonts/IBMPlexSans.ttf'),164)
draw.text((398,100),'High_SC',font=font,fill=navy)
save_raster(word,OUT/'wordmark.png')
print('Built original High_SC book / annotation logo, PNG, wordmark and multi-size ICO.')
