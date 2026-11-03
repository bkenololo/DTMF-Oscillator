from pathlib import Path
import shutil,json,hashlib
import argparse
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description='Rebuild editable LTspice blocks, symbols and test benches.')
parser.add_argument('--output-dir',type=Path,default=ROOT/'reproduced')
args=parser.parse_args()
O=args.output_dir.resolve()
if O==ROOT:parser.error('Choose a separate output directory to preserve the editable master files.')
O.mkdir(parents=True,exist_ok=True)
REF=ROOT
def write(name,s): (O/name).write_bytes(s.strip().encode('ascii')+b'\n')
def symbol(name,prefix,pins,graphics,windows='',value=''):
 s='Version 4\nSymbolType CELL\n'+graphics+'\n'+windows+f'\nSYMATTR Prefix {prefix}\n'
 if value:s+=f'SYMATTR Value {value}\n'
 for i,(pin,x,y) in enumerate(pins,1):s+=f'PIN {x} {y} NONE 0\nPINATTR PinName {pin}\nPINATTR SpiceOrder {i}\n'
 write(name+'.asy',s)
def lines(points):return '\n'.join(f'LINE Normal {a} {b} {c} {d}' for (a,b),(c,d) in zip(points,points[1:]))
zig=[(0,0),(16,0),(24,-12),(36,12),(48,-12),(60,12),(72,-12),(80,0),(96,0)]
symbol('R_H','R',[('A',0,0),('B',96,0)],lines(zig),'WINDOW 0 48 -56 Center 2\nWINDOW 3 48 -28 Center 2')
symbol('R_V','R',[('A',0,0),('B',0,96)],lines([(-y,x) for x,y in zig]),'WINDOW 0 32 24 Left 2\nWINDOW 3 32 56 Left 2')
ch='LINE Normal 0 0 44 0\nLINE Normal 44 -24 44 24\nLINE Normal 52 -24 52 24\nLINE Normal 52 0 96 0'
cv='LINE Normal 0 0 0 44\nLINE Normal -24 44 24 44\nLINE Normal -24 52 24 52\nLINE Normal 0 52 0 96'
symbol('C_H','C',[('A',0,0),('B',96,0)],ch,'WINDOW 0 48 -80 Center 2\nWINDOW 3 48 -52 Center 2')
symbol('C_V','C',[('A',0,0),('B',0,96)],cv,'WINDOW 0 32 24 Left 2\nWINDOW 3 32 56 Left 2')
symbol('C_Polar_V','C',[('POS',0,0),('NEG',0,96)],cv+'\nLINE Normal -28 16 -12 16\nLINE Normal -20 8 -20 24','WINDOW 0 32 24 Left 2\nWINDOW 3 32 56 Left 2')
symbol('Diode_1N4148','X',[('A',0,0),('K',96,0)],'LINE Normal 0 0 32 0\nLINE Normal 32 -24 32 24\nLINE Normal 32 -24 64 0\nLINE Normal 32 24 64 0\nLINE Normal 64 -24 64 24\nLINE Normal 64 0 96 0','WINDOW 0 48 -48 Center 2','1N4148')
symbol('TL074_Channel','X',[('IN+',0,96),('IN-',0,32),('VCC',96,0),('VEE',96,128),('OUT',192,64)],'''LINE Normal 0 32 32 32
LINE Normal 0 96 32 96
LINE Normal 32 0 32 128
LINE Normal 32 0 192 64
LINE Normal 32 128 192 64
LINE Normal 96 0 96 24
LINE Normal 96 128 96 104
LINE Normal 44 32 60 32
LINE Normal 44 96 60 96
LINE Normal 52 88 52 104''','WINDOW 0 96 56 Center 2\nWINDOW 3 96 80 Center 1','TL074')
symbol('V_Source','V',[('POS',0,0),('NEG',0,96)],'''LINE Normal 0 0 0 16
CIRCLE Normal -32 16 32 80
LINE Normal 0 80 0 96
LINE Normal -8 32 8 32
LINE Normal 0 24 0 40
LINE Normal -8 64 8 64''','WINDOW 0 48 24 Left 2\nWINDOW 3 48 64 Left 2')
class Sheet:
 def __init__(self,name,w=1344,h=1328):self.name=name;self.w=w;self.h=h;self.wires=[];self.flags=[];self.parts=[];self.texts=[];self.ports=[]
 def wire(self,*pts):
  for a,b in zip(pts,pts[1:]):
   assert a[0]==b[0] or a[1]==b[1],(a,b)
   if a!=b:self.wires.append(f'WIRE {a[0]} {a[1]} {b[0]} {b[1]}')
 def flag(self,x,y,n,port=None):
  self.flags.append(f'FLAG {x} {y} {n}')
  if port:self.ports.append(f'IOPIN {x} {y} {port}')
 def part(self,sym,x,y,name,value=None,rot='R0'):
  s=f'SYMBOL {sym} {x} {y} {rot}\nSYMATTR InstName {name}'
  if value is not None:s+=f'\nSYMATTR Value {value}'
  self.parts.append(s)
 def text(self,x,y,t,size=2,directive=False):self.texts.append(f'TEXT {x} {y} Left {size} '+('!' if directive else ';')+t)
 def save(self):write(self.name+'.asc','\n'.join([f'Version 4\nSHEET 1 {self.w} {self.h}']+self.wires+self.flags+self.ports+self.parts+self.texts))
def block(name,label,summer=False):
 if summer:
  w,h=320,288;pins=[('IN_LOW',-64,80),('IN_HIGH',-64,208),('OUT',384,144),('VCC',160,-48),('VEE',160,336),('GND',-64,272)]
  g=['LINE Normal -64 80 0 80','LINE Normal -64 208 0 208','LINE Normal 320 144 384 144','LINE Normal 160 -48 160 0','LINE Normal 160 288 160 336','LINE Normal -64 272 0 272','TEXT 16 80 Left 1 IN_LOW','TEXT 16 208 Left 1 IN_HIGH','TEXT 304 144 Right 1 OUT','TEXT 160 16 Center 1 VCC','TEXT 160 272 Center 1 VEE','TEXT 16 272 Left 1 GND','TEXT 160 104 Center 2 SUMMER','TEXT 160 144 Center 1 -10k / 22k']
 else:
  w,h=256,224;pins=[('OUT',320,96),('VCC',128,-48),('VEE',128,272),('GND',-64,192)]
  g=['LINE Normal 256 96 320 96','LINE Normal 128 -48 128 0','LINE Normal 128 224 128 272','LINE Normal -64 192 0 192','TEXT 240 96 Right 1 OUT','TEXT 128 16 Center 1 VCC','TEXT 128 208 Center 1 VEE','TEXT 16 192 Left 1 GND',f'TEXT 128 80 Center 2 {label}','TEXT 128 128 Center 1 Wien bridge']
 s=f'Version 4\nSymbolType BLOCK\nRECTANGLE Normal 0 0 {w} {h}\n'+'\n'.join(g)+'\nWINDOW 0 0 -32 Left 2\n'
 for i,(n,x,y) in enumerate(pins,1):s+=f'PIN {x} {y} NONE 0\nPINATTR PinName {n}\nPINATTR SpiceOrder {i}\n'
 write(name+'.asy',s)
 return pins
interfaces={}
for name,hz,base,small,shunt,offset in [('LowOscillator',770,'20k','620','560',0),('HighOscillator',1209,'13k','82','110',7)]:
 interfaces[name]=block(name,f'{hz} Hz')
 s=Sheet(name)
 s.text(64,16,f'{hz} Hz WIEN OSCILLATOR - refined component values',3)
 s.text(64,1280,'One TL074 channel; C = 10 nF; both diodes = 1N4148, across the 7.5k resistor only.',1)
 s.part('TL074_Channel',672,352,'U1A' if hz==770 else 'U1B')
 # Feedback: Rfixed in series with (Rbypassed || D1 || D2).
 s.wire((864,416),(1056,416),(1200,416));s.flag(1200,416,'OUT','Out')
 s.wire((1056,416),(1056,128),(896,128))
 s.part('R_H',800,128,f'R{6+offset}','15k');s.wire((800,128),(608,128),(512,128))
 s.part('R_H',416,128,f'R{7+offset}','7.5k');s.wire((416,128),(352,128),(352,208),(352,320),(352,384),(672,384))
 s.part('Diode_1N4148',416,208,'D1' if hz==770 else 'D3')
 s.part('Diode_1N4148',512,320,'D2' if hz==770 else 'D4',rot='R180')
 for y in [208,320]:
  s.wire((352,y),(416,y));s.wire((512,y),(608,y))
 s.wire((608,128),(608,208),(608,320))
 s.wire((352,384),(224,384),(224,448));s.part('R_V',224,448,f'R{5+offset}','10k');s.wire((224,544),(224,1040))
 # Positive feedback Wien network.
 s.wire((1056,416),(1056,688),(992,688));s.part('R_H',896,688,f'R{1+offset}',base)
 s.wire((896,688),(800,688));s.part('R_H',704,688,f'R{2+offset}',small)
 s.wire((704,688),(608,688));s.part('C_H',512,688,'C1' if hz==770 else 'C3','10n')
 s.wire((512,688),(480,688),(416,688),(288,688),(288,752))
 s.wire((416,688),(416,448),(672,448));s.flag(416,448,'WIEN')
 s.part('R_V',288,752,f'R{3+offset}',base);s.wire((288,848),(288,896));s.part('R_V',288,896,f'R{4+offset}',shunt);s.wire((288,992),(288,1040))
 s.wire((480,688),(480,752));s.part('C_V',480,752,'C2' if hz==770 else 'C4','10n');s.wire((480,848),(480,1040))
 s.wire((224,1040),(288,1040),(480,1040),(1120,1040));s.flag(1120,1040,'GND','BiDir')
 s.wire((768,352),(768,304));s.flag(768,304,'VCC','In')
 s.wire((768,480),(768,544));s.flag(768,544,'VEE','In')
 s.text(64,1120,'Simulation-only startup pulse (same seed as original ngspice circuit):',1)
 s.text(64,1168,'Iseed GND WIEN PWL(0 0 1u 0 2u 100n 11u 100n 12u 0)',1,True)
 s.text(64,1232,'Run the matching Test_*.asc; this sheet is a reusable hierarchical block.',1)
 s.save()
# Summer block.
interfaces['SummingAmplifier']=block('SummingAmplifier','SUMMER',True)
s=Sheet('SummingAmplifier',1472,1008)
s.text(64,16,'INVERTING SUMMING AMPLIFIER - TL074 U1C',3)
s.text(64,64,'V(OUT) = -(10k/22k) * [V(IN_LOW) + V(IN_HIGH)]')
s.part('TL074_Channel',736,352,'U1C')
s.wire((928,416),(1120,416),(1280,416));s.flag(1280,416,'OUT','Out')
s.wire((1120,416),(1120,192),(896,192));s.part('R_H',800,192,'R17','10k');s.wire((800,192),(608,192),(608,384),(736,384))
s.wire((128,320),(256,320));s.flag(128,320,'IN_LOW','In');s.part('R_H',256,320,'R15','22k');s.wire((352,320),(608,320))
s.wire((128,592),(256,592));s.flag(128,592,'IN_HIGH','In');s.part('R_H',256,592,'R16','22k');s.wire((352,592),(608,592),(608,384))
s.wire((736,448),(672,448),(672,752),(1280,752));s.flag(1280,752,'GND','BiDir')
s.wire((832,352),(832,288));s.flag(832,288,'VCC','In');s.wire((832,480),(832,544));s.flag(832,544,'VEE','In')
s.text(64,848,'The 1 Meg scope load belongs to the parent sheet, not to this amplifier block.',1)
s.text(64,896,'Physical TL074 U1C: OUT pin 8, IN- pin 9, IN+ pin 10.',1);s.save()
def include_and_run(s,y=1504):
 for i,line in enumerate(['.include "models.inc"','.temp 27','.options reltol=1e-5 abstol=1e-10 vntol=1e-7 method=trap plotwinsize=0','.tran 1.25u 0.5 0 1.25u']):s.text(64,y+i*40,line,1,True)
def supplies(s,y=1248,full=True):
 for x,n,value,rail in [(128,'Vpositive','12','VCC'),(384,'Vnegative','-12','VEE')]:
  s.part('V_Source',x,y,n,value);s.wire((x,y),(x,y-48));s.flag(x,y-48,rail);s.wire((x,y+96),(x,y+160));s.flag(x,y+160,'0')
 if full:
  for x,n,val,top,bottom,typ in [(640,'Cdec_pos','100n','VCC','0','C_V'),(832,'Cbulk_pos','10u','VCC','0','C_Polar_V'),(1056,'Cdec_neg','100n','VEE','0','C_V'),(1248,'Cbulk_neg','10u','0','VEE','C_Polar_V')]:
   s.part(typ,x,y,n,val);s.wire((x,y),(x,y-48));s.flag(x,y-48,top);s.wire((x,y+96),(x,y+160));s.flag(x,y+160,bottom)
def addosc(s,kind,x,y,inst,out):
 s.part(kind,x,y,inst)
 s.wire((x+128,y-48),(x+128,y-96));s.flag(x+128,y-96,'VCC')
 s.wire((x+128,y+272),(x+128,y+320));s.flag(x+128,y+320,'VEE')
 s.wire((x-64,y+192),(x-112,y+192),(x-112,y+240));s.flag(x-112,y+240,'0')
 s.flag(x+320,y+96,out)
def addsum(s,x,y,inst):
 s.part('SummingAmplifier',x,y,inst)
 s.wire((x+160,y-48),(x+160,y-96));s.flag(x+160,y-96,'VCC')
 s.wire((x+160,y+336),(x+160,y+400));s.flag(x+160,y+400,'VEE')
 s.wire((x-64,y+272),(x-128,y+272),(x-128,y+336));s.flag(x-128,y+336,'0')
s=Sheet('DTMF4',2208,2256)
s.text(64,16,'DTMF DIGIT 4 - 770 Hz + 1209 Hz - hierarchical design',3)
s.text(64,2160,'Three reusable blocks / one TL074 package / +/-12 V / 1 Meg scope load',1)
addosc(s,'LowOscillator',128,192,'U_LOW','LOW_OUT');addosc(s,'HighOscillator',128,704,'U_HIGH','HIGH_OUT');addsum(s,960,448,'U_SUM')
s.wire((448,288),(704,288),(704,528),(896,528));s.wire((448,800),(768,800),(768,656),(896,656))
s.wire((1344,592),(1456,592),(1600,592));s.flag(1600,592,'DTMF_OUT');s.wire((1456,592),(1456,688));s.part('R_V',1456,688,'Rscope','1Meg');s.wire((1456,784),(1456,848));s.flag(1456,848,'0')
s.text(64,1120,'SHARED SUPPLY AND DECOUPLING - Cbulk_neg positive terminal goes to ground',2);supplies(s)
s.text(1456,1120,'Unused fourth TL074 channel U1D',1)
s.part('TL074_Channel',1504,1216,'U1D');s.wire((1504,1248),(1440,1248),(1440,1168),(1776,1168),(1776,1280),(1696,1280))
s.wire((1504,1312),(1440,1312),(1440,1408));s.flag(1440,1408,'0')
s.wire((1600,1216),(1600,1168));s.flag(1600,1168,'VCC') # VCC must not touch feedback wire above; re-route below.
s.wires.remove('WIRE 1600 1216 1600 1168');s.flags.remove('FLAG 1600 1168 VCC')
s.wire((1600,1216),(1600,1184),(1648,1184));s.flag(1648,1184,'VCC')
s.wire((1600,1344),(1600,1408));s.flag(1600,1408,'VEE')
include_and_run(s)
s.text(64,1680,'.save V(LOW_OUT) V(HIGH_OUT) V(DTMF_OUT)',1,True)
for i,(label,node) in enumerate([('low','LOW_OUT'),('high','HIGH_OUT')]):
 s.text(64,1800+i*120,f'.meas tran T_{label} TRIG V({node}) VAL=0 RISE=1 TD=0.4 TARG V({node}) VAL=0 RISE=2 TD=0.4',1,True)
 s.text(64,1840+i*120,f'.meas tran f_{label} PARAM 1/T_{label}',1,True)
 s.text(64,1880+i*120,f'.meas tran vpp_{label} PP V({node}) FROM 0.4 TO 0.5',1,True)
s.text(64,1720,'.meas tran vpp_dtmf PP V(DTMF_OUT) FROM 0.4 TO 0.5',1,True)
s.text(64,2200,'Open a block with the LTspice hierarchy command to edit its components.',1);s.save()
# Standalone harnesses keep rails and analysis out of the reusable block sheets.
for kind,hz in [('LowOscillator',770),('HighOscillator',1209)]:
 s=Sheet('Test_'+kind,1648,1296);s.text(64,16,f'{hz} Hz OSCILLATOR TEST BENCH',3)
 addosc(s,kind,256,192,'U_TEST','OSC_OUT');s.wire((576,288),(800,288),(800,384));s.part('R_V',800,384,'Rload','1Meg');s.wire((800,480),(800,544));s.flag(800,544,'0')
 supplies(s,704,False);include_and_run(s,912);s.text(64,1080,'.save V(OSC_OUT)',1,True)
 s.text(64,1120,'.meas tran T_osc TRIG V(OSC_OUT) VAL=0 RISE=1 TD=0.4 TARG V(OSC_OUT) VAL=0 RISE=2 TD=0.4',1,True)
 s.text(64,1160,'.meas tran f_osc PARAM 1/T_osc',1,True);s.text(64,1200,'.meas tran vpp_osc PP V(OSC_OUT) FROM 0.4 TO 0.5',1,True);s.save()
s=Sheet('Test_SummingAmplifier',1856,1248);s.text(64,16,'SUMMER TEST BENCH - synthetic 3 V peak tones at 770 and 1209 Hz',3);addsum(s,832,256,'U_TEST')
for x,y,node,val in [(128,240,'IN_LOW','SINE(0 3 770)'),(416,528,'IN_HIGH','SINE(0 3 1209)')]:
 s.part('V_Source',x,y,'V'+node,val);s.wire((x,y),(x,y-48));s.flag(x,y-48,node);s.wire((x,y+96),(x,y+160));s.flag(x,y+160,'0')
s.wire((768,336),(640,336));s.flag(640,336,'IN_LOW');s.wire((768,464),(640,464));s.flag(640,464,'IN_HIGH')
s.wire((1216,400),(1392,400),(1392,496));s.flag(1392,400,'SUM_OUT');s.part('R_V',1392,496,'Rload','1Meg');s.wire((1392,592),(1392,656));s.flag(1392,656,'0')
supplies(s,848,False);include_and_run(s,1056);s.text(704,896,'.save V(IN_LOW) V(IN_HIGH) V(SUM_OUT)',1,True);s.text(704,944,'.meas tran vpp_sum PP V(SUM_OUT) FROM 0.4 TO 0.5',1,True);s.save()
# Original model retained byte-for-byte; active model only strips legacy DOS EOF.
shutil.copyfile(REF/'TL074_original.301',O/'TL074_original.301')
write('TL074.lib',(REF/'TL074_original.301').read_text().replace('\x1a',''))
shutil.copyfile(REF/'1N4148.lib',O/'1N4148.lib')
write('models.inc','.include "TL074.lib"\n.include "1N4148.lib"')
(O/'interfaces.json').write_text(json.dumps(interfaces,indent=2))
print(O)
