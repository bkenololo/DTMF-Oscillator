// Replay the downloaded public code; input PCM is resampled offline, not by WebAudio.
const fs=require('fs'),vm=require('vm'),path=require('path');
const root=path.resolve(__dirname,'..');
const code=fs.readFileSync(path.join(root,'05_Kode_Decoder_Publik/Goertzel.js'),'utf8')+'\n'+fs.readFileSync(path.join(root,'05_Kode_Decoder_Publik/DTMFDecoder.js'),'utf8')+'\nglobalThis.Decoder=DTMFDecoder;';
const ctx={};vm.createContext(ctx);vm.runInContext(code,ctx);
const input=JSON.parse(fs.readFileSync(path.join(root,'02_Hasil_Analisis/pcm_8k_untuk_replay.json')));
const samples=input.samples,rate=input.sample_rate_hz,N=320,frames=[];
for(let i=0;i+N<=samples.length;i+=N){const dec=new ctx.Decoder({sampleRate:rate,energyThreshold:0});const a=samples.slice(i,i+N);a.forEach((v,j)=>dec.goertzel.processSample(dec._exactBlackmanWindow(v,j,N)));frames.push({start_s:i/rate,energies:{...dec.goertzel.energies}});}
function trial(threshold,scale=1){const dec=new ctx.Decoder({sampleRate:rate,energyThreshold:threshold});let decoded='',prev='';const labels=[];for(let i=0;i+N<=samples.length;i+=N){let cur=dec.processBuffer(samples.slice(i,i+N).map(x=>x*scale));if(prev!==cur){decoded+=cur;prev=cur;}labels.push({start_s:i/rate,label:cur});}return {threshold,scale,decoded,frames:labels.filter(x=>x.label)};}
const sweep=[.1,.05,.02,.01,.009,.005,.001,.0001].map(t=>trial(t));
const scaling=[.1,.5,1,2].map(k=>trial(.009,k));
fs.writeFileSync(path.join(root,'02_Hasil_Analisis/replay_decoder.json'),JSON.stringify({frame_size:N,sample_rate_hz:rate,sweep,scaling,frames,limitation:'Same public JS algorithm; offline FIR resampling differs from browser WebAudio resampler. Not a new observed website test.'},null,2));
console.log(JSON.stringify({sweep:sweep.map(({threshold,decoded})=>({threshold,decoded})),scaling:scaling.map(({scale,decoded})=>({scale,decoded}))}));
