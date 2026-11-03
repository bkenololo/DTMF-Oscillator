#!/usr/bin/env python3
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from summing import read_raw_multi
from audio_export import export_audio
cfg=json.loads((ROOT/'config.json').read_text());nom=json.loads((ROOT/'results/nominal.json').read_text())
data=read_raw_multi(ROOT/'results/cases'/nom['measurement']['case_id']/'waveform.raw')
meta=export_audio(data,cfg,ROOT/'audio')
print(json.dumps(meta,indent=2))
