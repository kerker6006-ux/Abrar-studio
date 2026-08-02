from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Iterable
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]

def transparent_white(image: Image.Image) -> Image.Image:
    rgba = image.convert('RGBA'); px = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            r,g,b,a = px[x,y]; brightness=(r+g+b)/3; sat=max(r,g,b)-min(r,g,b)
            alpha = 0 if brightness>=232 and sat<30 else int(max(0,min(255,(232-brightness)/25*255))) if brightness>207 and sat<21 else 255
            px[x,y]=(r,g,b,min(a,alpha))
    return rgba

def masked_crop(source: Image.Image, bbox: tuple[int,int,int,int], polygon: Iterable[tuple[int,int]]|None=None)->Image.Image:
    x0,y0,x1,y1=bbox; crop=source.crop(bbox)
    if polygon:
        mask=Image.new('L',crop.size,0); ImageDraw.Draw(mask).polygon([(x-x0,y-y0) for x,y in polygon],fill=255)
        crop.putalpha(Image.composite(crop.getchannel('A'),Image.new('L',crop.size,0),mask))
    return crop

def sha256(path: Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

PROFILES={
'seo_yeon':{
 'root':[100,350],'ground_y':656,'neck':[91,132],'shoulder':[86,157],'elbow':[77,275],'wrist':[65,350],'knee':[103,485],'ankle':[102,615],'toe':[48,645],
 'parts':{
  'hair_back':{'bbox':[92,70,190,275],'polygon':[(95,75),(155,80),(190,145),(188,245),(150,270),(108,220)],'pivot':[91,132]},
  'head':{'bbox':[28,0,145,165],'polygon':[(45,15),(120,10),(140,55),(125,140),(92,160),(55,135),(35,75)],'pivot':[91,132]},
  'torso':{'bbox':[40,105,165,370],'polygon':[(72,115),(112,110),(150,145),(160,320),(140,350),(88,360),(72,318),(70,170)],'pivot':[100,350]},
  'upper_arm':{'bbox':[48,140,112,315],'polygon':[(74,145),(108,155),(103,250),(92,295),(62,305),(52,245)],'pivot':[86,157]},
  'lower_arm':{'bbox':[42,250,100,390],'polygon':[(62,255),(98,260),(88,340),(79,380),(53,385),(44,345)],'pivot':[77,275]},
  'upper_leg':{'bbox':[68,325,135,520],'polygon':[(78,330),(128,335),(130,470),(118,510),(82,510),(72,440)],'pivot':[100,350]},
  'lower_leg':{'bbox':[73,455,135,635],'polygon':[(84,458),(126,460),(126,600),(116,630),(88,630),(78,585)],'pivot':[103,485]},
  'foot':{'bbox':[34,590,137,665],'polygon':[(88,595),(122,596),(132,632),(120,655),(45,660),(36,642),(58,620)],'pivot':[102,615]}}},
'min_jun':{
 'root':[98,350],'ground_y':658,'neck':[85,108],'shoulder':[92,145],'elbow':[84,265],'wrist':[67,345],'knee':[104,485],'ankle':[104,620],'toe':[48,648],
 'parts':{
  'head':{'bbox':[32,0,140,140],'polygon':[(43,15),(115,10),(133,45),(120,115),(86,135),(52,112),(38,60)],'pivot':[85,108]},
  'torso':{'bbox':[35,92,165,370],'polygon':[(67,102),(116,95),(150,120),(160,325),(140,350),(88,360),(68,320),(65,145)],'pivot':[98,350]},
  'upper_arm':{'bbox':[48,135,115,315],'polygon':[(75,140),(110,150),(105,255),(96,295),(62,305),(50,245)],'pivot':[92,145]},
  'lower_arm':{'bbox':[42,245,103,390],'polygon':[(62,250),(100,255),(90,340),(80,380),(52,385),(44,340)],'pivot':[84,265]},
  'upper_leg':{'bbox':[68,325,137,520],'polygon':[(78,330),(132,335),(132,470),(120,512),(82,510),(72,440)],'pivot':[98,350]},
  'lower_leg':{'bbox':[73,455,138,640],'polygon':[(84,458),(130,460),(130,605),(120,635),(88,635),(78,585)],'pivot':[104,485]},
  'foot':{'bbox':[31,595,140,665],'polygon':[(86,598),(126,598),(136,635),(123,660),(42,662),(33,644),(56,622)],'pivot':[104,620]}}}}

def generate(cid:str)->None:
    r=PROFILES[cid]; root=ROOT/'assets'/'characters'/cid; source=transparent_white(Image.open(root/'poses'/'full_side.png'))
    outdir=root/'rig'/'side'; outdir.mkdir(parents=True,exist_ok=True); meta={}
    for name,s in r['parts'].items():
        bbox=tuple(s['bbox']); image=masked_crop(source,bbox,s.get('polygon')); out=outdir/f'{name}.png'; image.save(out)
        x0,y0,_,_=bbox; px,py=s['pivot']; meta[name]={'file':f'rig/side/{name}.png','pivot':[px-x0,py-y0],'source_pivot':[px,py],'bbox':list(bbox)}
    parts={
     'arm_back_upper':{**meta['upper_arm'],'parent':'torso','rest_offset':[r['shoulder'][0]-r['root'][0]+5,r['shoulder'][1]-r['root'][1]-2],'z':1,'brightness':0.76},
     'arm_back_lower':{**meta['lower_arm'],'parent':'arm_back_upper','rest_offset':[r['elbow'][0]-r['shoulder'][0],r['elbow'][1]-r['shoulder'][1]],'z':2,'brightness':0.76},
     'leg_back_upper':{**meta['upper_leg'],'parent':'torso','rest_offset':[-5,0],'z':3,'brightness':0.73},
     'leg_back_lower':{**meta['lower_leg'],'parent':'leg_back_upper','rest_offset':[r['knee'][0]-r['root'][0],r['knee'][1]-r['root'][1]],'z':4,'brightness':0.73},
     'foot_back':{**meta['foot'],'parent':'leg_back_lower','rest_offset':[r['ankle'][0]-r['knee'][0],r['ankle'][1]-r['knee'][1]],'z':5,'brightness':0.73},
     'torso':{**meta['torso'],'parent':None,'rest_offset':[0,0],'z':6},
     'leg_front_upper':{**meta['upper_leg'],'parent':'torso','rest_offset':[5,0],'z':7},
     'leg_front_lower':{**meta['lower_leg'],'parent':'leg_front_upper','rest_offset':[r['knee'][0]-r['root'][0],r['knee'][1]-r['root'][1]],'z':8},
     'foot_front':{**meta['foot'],'parent':'leg_front_lower','rest_offset':[r['ankle'][0]-r['knee'][0],r['ankle'][1]-r['knee'][1]],'z':9},
     'arm_front_upper':{**meta['upper_arm'],'parent':'torso','rest_offset':[r['shoulder'][0]-r['root'][0],r['shoulder'][1]-r['root'][1]],'z':10},
     'arm_front_lower':{**meta['lower_arm'],'parent':'arm_front_upper','rest_offset':[r['elbow'][0]-r['shoulder'][0],r['elbow'][1]-r['shoulder'][1]],'z':11},
     'head':{**meta['head'],'parent':'torso','rest_offset':[r['neck'][0]-r['root'][0],r['neck'][1]-r['root'][1]],'z':12}}
    if 'hair_back' in meta: parts['hair_back']={**meta['hair_back'],'parent':'head','rest_offset':[0,0],'z':0,'brightness':0.93,'lag':0.16}
    rig={'format':'abrar_articulated_rig_v1','character_id':cid,'view':'side','source_size':list(source.size),'root':r['root'],'ground_y':r['ground_y'],'joints':{k:r[k] for k in ['neck','shoulder','elbow','wrist','knee','ankle','toe']},'parts':parts,'motions':['idle_breathe','walk_slow','walk_normal','walk_confident','walk_sad','run_normal','run_panicked','start_walk','stop_sudden','step_back','shock_recoil']}
    rig_path=root/'rig'/'rig.json'; rig_path.write_text(json.dumps(rig,ensure_ascii=False,indent=2),encoding='utf-8')
    mp=root/'manifest.json'; m=json.loads(mp.read_text(encoding='utf-8')); m['rig_version']='ARTICULATED_SIDE_RIG_3.0'; m['rig_type']='articulated_bone_rig_v3'; m['articulated_rig']='rig/rig.json'; checks=m.setdefault('asset_checksums',{})
    for p in sorted((root/'rig').rglob('*')):
        if p.is_file(): checks[p.relative_to(root).as_posix()]=sha256(p)
    mp.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':
    for cid in PROFILES: generate(cid)
    print('Generated articulated rigs')
