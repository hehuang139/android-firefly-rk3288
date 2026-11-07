package org.firefly.tools;

import android.media.AudioAttributes;
import android.media.AudioDeviceInfo;
import android.media.AudioFormat;
import android.media.AudioTrack;
import android.os.SystemClock;
import org.json.JSONObject;

/** Four-second low-level stereo test. Does not change device or stream volume. */
public final class AudioTrackProbe {
    private static final int RATE=48000, CHANNELS=2, TOTAL_FRAMES=RATE*4;
    private static final double AMPLITUDE=32767.0*Math.pow(10.0,-26.0/20.0);
    public static void main(String[] args) throws Exception {
        if(args.length!=0)throw new IllegalArgumentException("AudioTrackProbe takes no arguments");
        JSONObject report=new JSONObject().put("sampleRate",RATE).put("channels",CHANNELS)
                .put("pcmBits",16).put("durationSeconds",4).put("peakDbfs",-26)
                .put("leftSeconds",2).put("rightSeconds",2).put("frequencyHz",440)
                .put("systemVolumeChanged",false).put("audibleConfirmationRequired",true);
        AudioTrack track=null;long begin=SystemClock.elapsedRealtime();int writtenSamples=0;
        long head=0,maxHead=0;
        try {
            int minimum=AudioTrack.getMinBufferSize(RATE,AudioFormat.CHANNEL_OUT_STEREO,
                    AudioFormat.ENCODING_PCM_16BIT);
            if(minimum<=0)throw new IllegalStateException("Invalid minimum buffer size: "+minimum);
            int bufferBytes=Math.max(minimum, RATE*CHANNELS*2/10);
            track=new AudioTrack.Builder()
                    .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
                    .setAudioFormat(new AudioFormat.Builder().setSampleRate(RATE)
                            .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                            .setEncoding(AudioFormat.ENCODING_PCM_16BIT).build())
                    .setTransferMode(AudioTrack.MODE_STREAM).setBufferSizeInBytes(bufferBytes).build();
            if(track.getState()!=AudioTrack.STATE_INITIALIZED)throw new IllegalStateException("Uninitialized AudioTrack");
            report.put("bufferCapacityFrames",track.getBufferCapacityInFrames())
                    .put("bufferSizeFrames",track.getBufferSizeInFrames()).put("sessionId",track.getAudioSessionId());
            short[] pcm=new short[TOTAL_FRAMES*CHANNELS];
            for(int frame=0;frame<TOTAL_FRAMES;frame++){
                int phaseFrame=frame%(RATE*2), side=frame<(RATE*2)?0:1;
                double ramp=Math.min(1.0,Math.min(phaseFrame,(RATE*2-1)-phaseFrame)/(RATE*0.025));
                pcm[frame*2+side]=(short)Math.round(AMPLITUDE*ramp*Math.sin(2*Math.PI*440*phaseFrame/RATE));
            }
            track.play();
            while(writtenSamples<pcm.length){
                if(SystemClock.elapsedRealtime()-begin>10000)throw new IllegalStateException("Audio write deadline exceeded");
                int count=track.write(pcm,writtenSamples,Math.min(4800,pcm.length-writtenSamples),AudioTrack.WRITE_NON_BLOCKING);
                if(count<0)throw new IllegalStateException("AudioTrack write returned "+count);
                if(count%CHANNELS!=0)throw new IllegalStateException("Partial stereo frame: "+count);
                writtenSamples+=count;
                head=Integer.toUnsignedLong(track.getPlaybackHeadPosition());maxHead=Math.max(maxHead,head);
                if(count==0)SystemClock.sleep(5);
            }
            while(head<TOTAL_FRAMES && SystemClock.elapsedRealtime()-begin<=10000){
                SystemClock.sleep(10);head=Integer.toUnsignedLong(track.getPlaybackHeadPosition());maxHead=Math.max(maxHead,head);
            }
            AudioDeviceInfo device=track.getRoutedDevice();
            if(device!=null)report.put("routedDevice",new JSONObject().put("id",device.getId())
                    .put("type",device.getType()).put("address",device.getAddress())
                    .put("productName",String.valueOf(device.getProductName())));
            report.put("underrunCount",track.getUnderrunCount()).put("playState",track.getPlayState());
            if(writtenSamples!=pcm.length || head<TOTAL_FRAMES)throw new IllegalStateException("Playback head did not consume all written frames");
            report.put("passed",true);
        } catch(Throwable error){report.put("passed",false).put("error",error.toString());error.printStackTrace(System.err);
        } finally {
            report.put("writtenSamples",writtenSamples).put("writtenFrames",writtenSamples/CHANNELS)
                    .put("writtenBytes",writtenSamples*2).put("playbackHeadFrames",head)
                    .put("maximumPlaybackHeadFrames",maxHead).put("elapsedMs",SystemClock.elapsedRealtime()-begin);
            if(track!=null){try{track.stop();}catch(Exception ignored){}track.release();}
            System.out.println("FIREFLY_AUDIOTRACK_RESULT "+report.toString());
        }
        if(!report.optBoolean("passed"))System.exit(1);
    }
}
