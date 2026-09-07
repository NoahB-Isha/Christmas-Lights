import json,glob,os,sys
from PIL import Image, ImageDraw
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from lightshow.formats.props import load_mod
os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'props'))
files=sorted(glob.glob('*.mod'), key=lambda f: json.load(open(f))['dotCount'])
def hsv(h):
    import colorsys; r,g,b=colorsys.hsv_to_rgb(h%1.0,0.85,1.0); return (int(r*255),int(g*255),int(b*255))
CELL=260; COLS=5; PAD=8
rows=(len(files)+COLS-1)//COLS
img=Image.new('RGB',(COLS*CELL,rows*CELL),(12,12,16))
dr=ImageDraw.Draw(img)
for k,f in enumerate(files):
    P=load_mod(f).xy; n=len(P)          # loader gives y-UP
    cx,cy=(k%COLS)*CELL,(k//COLS)*CELL
    xs=[p[0] for p in P]; ys=[p[1] for p in P]
    w=max(xs)-min(xs) or 1; h=max(ys)-min(ys) or 1
    sc=min((CELL-2*PAD-18)/w,(CELL-2*PAD-18)/h)
    ox=cx+CELL/2-(min(xs)+max(xs))/2*sc; oy=cy+CELL/2+8-(min(ys)+max(ys))/2*sc
    for i,p in enumerate(P):
        X=ox+p[0]*sc; Y=oy-p[1]*sc       # y-up -> screen
        r=1.6
        dr.ellipse([X-r,Y-r,X+r,Y+r],fill=hsv(i/n*0.85))
    dr.text((cx+6,cy+4),f"{f}  n={n}",fill=(230,230,230))
outdir=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','out')
os.makedirs(outdir, exist_ok=True)
out=os.path.join(outdir,'prop_shapes.png')
img.save(out)
print(out,len(files),'props; colour runs blue->red along wire order')
