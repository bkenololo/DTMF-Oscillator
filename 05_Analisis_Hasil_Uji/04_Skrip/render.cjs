const path=require('path'),fs=require('fs');
const sharp=require(process.env.SHARP_MODULE || 'sharp');
const dir=path.resolve(__dirname,'../03_Grafik');
(async()=>{for(const name of ['ringkasan','waveform_dan_fft'])await sharp(path.join(dir,name+'.svg')).png().toFile(path.join(dir,name+'.png'));})();
