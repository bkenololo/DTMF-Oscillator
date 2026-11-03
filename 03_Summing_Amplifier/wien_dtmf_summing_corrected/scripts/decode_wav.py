#!/usr/bin/env python3
"""Basic spectral DTMF sanity checker for exported mono 16-bit PCM WAV."""
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from audio_export import decode_basic,read_pcm
p=argparse.ArgumentParser();p.add_argument('wav',type=Path);a=p.parse_args()
fs,signal=read_pcm(a.wav);print(json.dumps(decode_basic(signal,fs),indent=2))
