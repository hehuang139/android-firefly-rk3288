package org.firefly.tools;

import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.os.SystemClock;
import java.nio.ByteBuffer;
import java.util.zip.CRC32;
import org.json.JSONObject;

/** Exact software-codec decode to ByteBuffers. No Surface, AudioTrack or network. */
public final class CodecProbe {
    public static void main(String[] args) throws Exception {
        if(args.length!=2 || !(args[1].equals("avc")||args[1].equals("aac")||args[1].equals("opus")))
            throw new IllegalArgumentException("CodecProbe /path/sample avc|aac|opus");
        boolean video=args[1].equals("avc");
        String expectedMime=video?"video/avc":args[1].equals("opus")?"audio/opus":"audio/mp4a-latm";
        String exactCodec="c2.android."+args[1]+".decoder";
        MediaExtractor extractor=new MediaExtractor();MediaCodec codec=null;
        long start=SystemClock.elapsedRealtime();
        JSONObject report=new JSONObject().put("kind",args[1]).put("requestedCodec",exactCodec)
                .put("hardwareTest",false).put("audioTrackUsed",false).put("surfaceUsed",false);
        int inputSamples=0,outputBuffers=0;long outputBytes=0,firstPts=-1,lastPts=-1;
        CRC32 crc=new CRC32();byte[] chunk=new byte[16384];MediaFormat outputFormat=null;
        try{
            extractor.setDataSource(args[0]);MediaFormat format=null;
            for(int i=0;i<extractor.getTrackCount();i++){
                MediaFormat f=extractor.getTrackFormat(i);
                if(expectedMime.equals(f.getString(MediaFormat.KEY_MIME))){format=f;extractor.selectTrack(i);break;}
            }
            if(format==null)throw new IllegalStateException("Expected track absent: "+expectedMime);
            report.put("inputFormat",format.toString());
            codec=MediaCodec.createByCodecName(exactCodec);report.put("actualCodec",codec.getName());
            if(!exactCodec.equals(codec.getName()))throw new IllegalStateException("Unexpected codec substitution");
            codec.configure(format,null,null,0);codec.start();
            boolean inputEos=false,outputEos=false;
            MediaCodec.BufferInfo info=new MediaCodec.BufferInfo();
            while(!outputEos){
                if(SystemClock.elapsedRealtime()-start>20000)throw new IllegalStateException("Decode deadline exceeded");
                if(!inputEos){
                    int slot=codec.dequeueInputBuffer(10000);
                    if(slot>=0){
                        ByteBuffer buffer=codec.getInputBuffer(slot);buffer.clear();
                        int length=extractor.readSampleData(buffer,0);
                        if(length<0){codec.queueInputBuffer(slot,0,0,0,MediaCodec.BUFFER_FLAG_END_OF_STREAM);inputEos=true;}
                        else{long pts=extractor.getSampleTime();codec.queueInputBuffer(slot,0,length,pts,0);inputSamples++;extractor.advance();}
                    }
                }
                int slot=codec.dequeueOutputBuffer(info,10000);
                if(slot==MediaCodec.INFO_OUTPUT_FORMAT_CHANGED){outputFormat=codec.getOutputFormat();report.put("outputFormat",outputFormat.toString());}
                else if(slot>=0){
                    if(info.size>0 && (info.flags&MediaCodec.BUFFER_FLAG_CODEC_CONFIG)==0){
                        ByteBuffer decoded=codec.getOutputBuffer(slot);
                        if(decoded==null)throw new IllegalStateException("Null decoded ByteBuffer");
                        decoded.position(info.offset);decoded.limit(info.offset+info.size);
                        while(decoded.hasRemaining()){int count=Math.min(decoded.remaining(),chunk.length);decoded.get(chunk,0,count);crc.update(chunk,0,count);}
                        if(firstPts<0)firstPts=info.presentationTimeUs;lastPts=info.presentationTimeUs;
                        outputBuffers++;outputBytes+=info.size;
                    }
                    outputEos=(info.flags&MediaCodec.BUFFER_FLAG_END_OF_STREAM)!=0;
                    codec.releaseOutputBuffer(slot,false);
                }
            }
            if(outputBuffers<(video?20:10)||outputBytes<=0)throw new IllegalStateException("Insufficient decoded output");
            report.put("passed",true).put("endOfStream",true);
        }catch(Throwable error){
            report.put("passed",false).put("error",error.toString());
            error.printStackTrace(System.err);
        }finally{
            report.put("inputSamples",inputSamples).put("outputBuffers",outputBuffers)
                    .put("outputBytes",outputBytes).put("firstPtsUs",firstPts).put("lastPtsUs",lastPts)
                    .put("elapsedMs",SystemClock.elapsedRealtime()-start).put("decodedCrc32",Long.toHexString(crc.getValue()));
            if(!video && outputFormat!=null){
                int channels=outputFormat.getInteger(MediaFormat.KEY_CHANNEL_COUNT);
                int sampleRate=outputFormat.getInteger(MediaFormat.KEY_SAMPLE_RATE);
                int encoding=outputFormat.containsKey(MediaFormat.KEY_PCM_ENCODING)?outputFormat.getInteger(MediaFormat.KEY_PCM_ENCODING):2;
                int bytesPerSample=encoding==2?2:encoding==4?4:encoding==3?1:0;
                report.put("pcmChannels",channels).put("pcmSampleRate",sampleRate).put("pcmEncoding",encoding);
                if(bytesPerSample>0)report.put("pcmFrames",outputBytes/(channels*bytesPerSample));
            }
            if(codec!=null){try{codec.stop();}catch(Exception ignored){}codec.release();}
            extractor.release();System.out.println("FIREFLY_CODEC_RESULT "+report.toString());
        }
        if(!report.optBoolean("passed"))System.exit(1);
    }
}
