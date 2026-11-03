from pathlib import Path
from collections import defaultdict,Counter
import shlex,json,re,math
# Exact graph isomorphism with color refinement and adjacency-preserving backtracking.
class Graph:
 def __init__(self):self.nodes={};self.adj=defaultdict(set)
 def add_node(self,n,**attrs):self.nodes[n]=attrs;self.adj[n]
 def add_edge(self,a,b):self.adj[a].add(b);self.adj[b].add(a)
def is_isomorphic(a,b,node_match=None):
 if len(a.nodes)!=len(b.nodes):return False
 ca={n:a.nodes[n]['color'] for n in a.nodes};cb={n:b.nodes[n]['color'] for n in b.nodes}
 prior=0
 for _ in range(len(ca)):
  aa={n:(ca[n],tuple(sorted(ca[m] for m in a.adj[n]))) for n in ca}
  bb={n:(cb[n],tuple(sorted(cb[m] for m in b.adj[n]))) for n in cb}
  palette={v:str(i) for i,v in enumerate(sorted(set(aa.values())|set(bb.values())))}
  ca={n:palette[v] for n,v in aa.items()};cb={n:palette[v] for n,v in bb.items()}
  if Counter(ca.values())!=Counter(cb.values()):return False
  count=len(set(ca.values()))
  if count==prior:break
  prior=count
 candidates={n:{m for m in cb if cb[m]==ca[n]} for n in ca};mapping={};used=set()
 def visit():
  if len(mapping)==len(ca):return True
  n=max((n for n in ca if n not in mapping),key=lambda n:(len(a.adj[n]&mapping.keys()),-len(candidates[n]-used),len(a.adj[n])))
  for m in candidates[n]-used:
   if any(((k in a.adj[n]) != (v in b.adj[m])) for k,v in mapping.items()):continue
   mapping[n]=m;used.add(m)
   if visit():return True
   del mapping[n];used.remove(m)
  return False
 return visit()
class NX:
 Graph=Graph
 is_isomorphic=staticmethod(is_isomorphic)
nx=NX()
from PIL import Image,ImageDraw,ImageFont
import argparse
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description='Check ASC/ASY connectivity against the preserved source netlist and render previews.')
parser.add_argument('--project-dir',type=Path,default=ROOT/'reproduced')
args=parser.parse_args()
O=args.project_dir.resolve();V=O/'verification';V.mkdir(parents=True,exist_ok=True)
def data(path):return path.read_text(encoding='ascii').splitlines()
def symbol(name):
 d={'pins':[],'attrs':{},'windows':{},'graphics':[],'kind':'CELL'};pin=None
 for line in data(O/(name+'.asy')):
  a=line.split()
  if not a:continue
  if a[0]=='SymbolType':d['kind']=a[1]
  elif a[0]=='PIN':pin={'xy':tuple(map(int,a[1:3]))};d['pins'].append(pin)
  elif a[0]=='PINATTR':pin[a[1]]=' '.join(a[2:])
  elif a[0]=='SYMATTR':d['attrs'][a[1]]=' '.join(a[2:])
  elif a[0]=='WINDOW':d['windows'][a[1]]=(int(a[2]),int(a[3]),a[4],int(a[5]))
  elif a[0] in ['LINE','RECTANGLE','CIRCLE','TEXT']:d['graphics'].append(line)
 d['pins'].sort(key=lambda p:int(p['SpiceOrder']))
 return d
def transform(xy,pos,rot):
 x,y=xy;sx,sy=pos
 if rot=='R0':return sx+x,sy+y
 if rot=='R180':return sx-x,sy-y
 raise ValueError(rot)
class Union:
 def __init__(self):self.p={}
 def find(self,a):
  if a not in self.p:self.p[a]=a
  if self.p[a]!=a:self.p[a]=self.find(self.p[a])
  return self.p[a]
 def join(self,a,b):self.p[self.find(a)]=self.find(b)
def sheet(name):
 d={'parts':[],'wires':[],'flags':[],'ports':{},'texts':[]};cur=None
 for line in data(O/(name+'.asc')):
  a=line.split()
  if not a:continue
  if a[0]=='SHEET':d['size']=tuple(map(int,a[2:4]))
  elif a[0]=='WIRE':d['wires'].append((tuple(map(int,a[1:3])),tuple(map(int,a[3:5]))))
  elif a[0]=='FLAG':d['flags'].append((tuple(map(int,a[1:3])),a[3]))
  elif a[0]=='IOPIN':d['ports'][tuple(map(int,a[1:3]))]=a[3]
  elif a[0]=='SYMBOL':cur={'symbol':a[1],'pos':tuple(map(int,a[2:4])),'rot':a[4],'attrs':{}};d['parts'].append(cur)
  elif a[0]=='SYMATTR':cur['attrs'][a[1]]=' '.join(a[2:])
  elif a[0]=='TEXT':d['texts'].append((int(a[1]),int(a[2]),int(a[4]),' '.join(a[5:])))
 u=Union();points=set();named=defaultdict(list)
 for a,b in d['wires']:u.join(a,b);points.update([a,b])
 for xy,n in d['flags']:points.add(xy);named[n].append(xy)
 for part in d['parts']:
  part['def']=symbol(part['symbol']);part['pins']=[transform(p['xy'],part['pos'],part['rot']) for p in part['def']['pins']];points.update(part['pins'])
 for xy in points:
  u.find(xy)
  for a,b in d['wires']:
   if (a[0]==b[0]==xy[0] and min(a[1],b[1])<=xy[1]<=max(a[1],b[1])) or (a[1]==b[1]==xy[1] and min(a[0],b[0])<=xy[0]<=max(a[0],b[0])):u.join(xy,a)
 for n,locs in named.items():
  for xy in locs[1:]:u.join(locs[0],xy)
 labels=defaultdict(set)
 for xy,n in d['flags']:labels[u.find(xy)].add(n)
 assert all(len(names)==1 for names in labels.values()),(name,'Shorted labels',dict(labels))
 anon={}
 def net(xy):
  root=u.find(xy)
  if labels[root]:return next(iter(labels[root]))
  if root not in anon:anon[root]='N'+str(len(anon)+1)
  return anon[root]
 for part in d['parts']:part['nets']=[net(xy) for xy in part['pins']]
 d['portnames']={n for xy,n in d['flags'] if xy in d['ports']};d['net']=net;d['points']=points
 # Every pin must meet a wire endpoint/segment or flag; no deliberate floating pins here.
 for p in d['parts']:
  for xy in p['pins']:
   assert any((a[0]==b[0]==xy[0] and min(a[1],b[1])<=xy[1]<=max(a[1],b[1])) or (a[1]==b[1]==xy[1] and min(a[0],b[0])<=xy[0]<=max(a[0],b[0])) for a,b in d['wires']),(name,p['attrs'],xy,'unconnected')
 return d
cache={name:sheet(name) for name in ['LowOscillator','HighOscillator','SummingAmplifier','DTMF4','Test_LowOscillator','Test_HighOscillator','Test_SummingAmplifier']}
for name in ['LowOscillator','HighOscillator','SummingAmplifier']:
 assert {p['PinName'] for p in symbol(name)['pins']}==cache[name]['portnames']
def flatten(name,prefix='',mapping=None):
 d=cache[name];mapping=mapping or {};out=[];direct=[]
 def node(n):return '0' if n=='0' else mapping.get(n,prefix+n)
 for p in d['parts']:
  name0=p['attrs']['InstName'];nd=[node(n) for n in p['nets']];sd=p['def']
  if sd['kind']=='BLOCK':
   pinmap={pin['PinName']:n for pin,n in zip(sd['pins'],nd)}
   elems,cmds=flatten(p['symbol'],prefix+name0+'.',pinmap);out+=elems;direct+=cmds
  else:
   attrs={**sd['attrs'],**p['attrs']};pr=attrs['Prefix'];val=attrs['Value']
   out.append([pr+prefix+name0,*nd,val])
 for x,y,size,t in d['texts']:
  if t.startswith('!'):
   text=t[1:]
   if text.startswith('Iseed '):
    a=text.split();out.append(['I'+prefix+'seed',node(a[1]),node(a[2]),' '.join(a[3:])])
   else:direct.append(text)
 return out,direct
# Compare the flattened ASC network to the original refined .cir independent of names and drawing positions.
def numeric(v):
 try:return format(float(v),'.12g')
 except ValueError:
  m=re.fullmatch(r'([0-9.]+)([A-Za-z]+)',v)
  if m:
   suffix={'k':1e3,'meg':1e6,'n':1e-9,'u':1e-6,'m':1e-3,'p':1e-12}
   if m[2].lower() in suffix:return format(float(m[1])*suffix[m[2].lower()],'.12g')
  return re.sub(r'\s+','',v).lower()
def graph(elems):
 g=nx.Graph()
 for i,e in enumerate(elems):
  typ=e[0][0].upper();n=5 if typ=='X' and e[-1].upper()=='TL074' else 2;ns=e[1:1+n];value=numeric(e[-1]);dev=('dev',i);g.add_node(dev,color=typ+':'+value)
  for j,node in enumerate(ns):
   net=('net',node.lower());g.add_node(net,color='GND' if node=='0' else 'net')
   pin=('pin',i,j);g.add_node(pin,color='pin' if typ in ['R','C'] else 'pin'+str(j));g.add_edge(dev,pin);g.add_edge(pin,net)
 return g
ref=[]
for l in (ROOT/'reference/circuit.cir').read_text().splitlines():
 if l and l[0].upper() in ['R','C','V','X','I'] and not l.startswith('*'):
  a=l.split();n=5 if a[0][0].upper()=='X' and a[-1].upper()=='TL074' else 2;ref.append([a[0],*a[1:n+1],' '.join(a[n+1:])])
main,_=flatten('DTMF4')
# The source seed uses decimal numbers; canonicalize the PWL syntax numerically.
def seednorm(elems):
 out=[]
 for e in elems:
  e=e.copy()
  if e[0][0]=='I':
   inside=e[-1].split('(',1)[1].rstrip(')');e[-1]='PWL('+','.join(numeric(x) for x in inside.replace(',',' ').split())+')'
  out.append(e)
 return out
iso=nx.is_isomorphic(graph(seednorm(main)),graph(seednorm(ref)),node_match=lambda a,b:a['color']==b['color'])
assert iso,'Generated hierarchical circuit differs electrically from source circuit'
for name in ['DTMF4','Test_LowOscillator','Test_HighOscillator','Test_SummingAmplifier']:
 elems,cmds=flatten(name)
 text='* Extracted from '+name+'.asc and matching hierarchy\n'+'\n'.join(' '.join(e) for e in elems)+'\n'+'\n'.join(cmds)+'\n.end\n'
 (O/(name+'_extracted.cir')).write_text(text,encoding='ascii')
# Render actual ASC/ASY geometry for visual review; these are not LTspice screenshots.
import os
fontpath=os.environ.get('SCHEMATIC_FONT','DejaVuSans.ttf')
if 'SCHEMATIC_FONT' not in os.environ and Path('/System/Library/Fonts/Supplemental/Arial.ttf').exists():
 fontpath='/System/Library/Fonts/Supplemental/Arial.ttf'
def getfont(size):
 try:return ImageFont.truetype(fontpath,size)
 except OSError:return ImageFont.load_default(size=size)
def render(name):
 d=cache[name];scale=1.6;w,h=d['size'];im=Image.new('RGB',(int(w*scale),int(h*scale)),'white');dr=ImageDraw.Draw(im)
 def xy(p):return tuple(round(z*scale) for z in p)
 def line(a,b,col='#172a3a',width=2):dr.line([xy(a),xy(b)],fill=col,width=width)
 def text(at,t,size=2,anchor='lm',col='black'):
  f=getfont(round(({1:18,2:24,3:32}[size])*scale));dr.text(xy(at),t,font=f,fill=col,anchor=anchor)
 for a,b in d['wires']:line(a,b,'#205b87')
 for part in d['parts']:
  tr=lambda p:transform(p,part['pos'],part['rot'])
  for l in part['def']['graphics']:
   a=l.split();cmd=a[0]
   if cmd=='LINE':line(tr(tuple(map(int,a[2:4]))),tr(tuple(map(int,a[4:6]))))
   elif cmd in ['RECTANGLE','CIRCLE']:
    x1,y1=xy(tr(tuple(map(int,a[2:4]))));x2,y2=xy(tr(tuple(map(int,a[4:6]))));box=(min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2))
    (dr.rectangle if cmd=='RECTANGLE' else dr.ellipse)(box,outline='#172a3a',width=2)
   elif cmd=='TEXT':
    xx,yy=int(a[1]),int(a[2]);anchor={'Left':'lm','Right':'rm','Center':'mm'}[a[3]];text(tr((xx,yy)),' '.join(a[5:]),int(a[4]),anchor)
  attrs={**part['def']['attrs'],**part['attrs']}
  for n,(xx,yy,just,size) in part['def']['windows'].items():
   if n=='0':v=attrs.get('InstName','')
   elif n=='3':v=attrs.get('Value','')
   else:continue
   # Keep text upright in previews of reversed diodes.
   anchor={'Left':'lm','Right':'rm','Center':'mm'}[just];text(tr((xx,yy)),v,size,anchor)
 for (x,y),n in d['flags']:
  if n=='0':
   line((x,y),(x,y+12));line((x-16,y+12),(x+16,y+12));line((x-10,y+20),(x+10,y+20));line((x-4,y+28),(x+4,y+28))
  else:text((x+4,y-20),n,1,'ls','#205b87')
 for x,y,size,t in d['texts']:
  if t.startswith('!'):text((x,y),t[1:],size,'lt','#555555')
  else:text((x,y),t[1:],size,'lt')
 # Junction dots only where multiple segments/pins meet.
 for pt in d['points']:
  count=sum(pt==a or pt==b for a,b in d['wires'])+sum(pt in p['pins'] for p in d['parts'])
  if count>=3:
   x,y=xy(pt);dr.ellipse((x-4,y-4,x+4,y+4),fill='#205b87')
 im.save(V/(name+'_preview.png'),dpi=(200,200))
for name in cache:render(name)
report={'electrically_isomorphic_to_original_refined_circuit':iso,'reference_components':len(ref),'generated_components':len(main),'interfaces_match':True,'unconnected_pins':0,'shorted_named_nets':0,'preview_note':'Rendered from the ASC/ASY source geometry; not an LTspice screenshot.'}
(V/'connectivity_check.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
