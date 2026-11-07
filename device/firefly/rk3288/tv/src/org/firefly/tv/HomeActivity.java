/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.*;
import android.graphics.drawable.*;
import android.net.*;
import android.os.*;
import android.text.format.DateFormat;
import android.view.*;
import android.widget.*;
import java.util.Date;

/** A calm, compact home for television, remote control and mouse. */
public final class HomeActivity extends TvActivity {
    private final Handler handler=new Handler(Looper.getMainLooper());
    private TextView clock,network;
    private ConnectivityManager connectivity;
    private boolean observing;
    private final Runnable tick=new Runnable(){public void run(){clock.setText(DateFormat.format("HH:mm",new Date()));updateNetwork();handler.postDelayed(this,30000);}};
    private final ConnectivityManager.NetworkCallback callback=new ConnectivityManager.NetworkCallback(){
        @Override public void onAvailable(Network n){handler.post(()->updateNetwork());}
        @Override public void onLost(Network n){handler.post(()->updateNetwork());}
        @Override public void onCapabilitiesChanged(Network n,NetworkCapabilities c){handler.post(()->updateNetwork());}
    };
    @Override protected void onCreate(Bundle state){super.onCreate(state);WatchTimeTracker.start(this);connectivity=getSystemService(ConnectivityManager.class);buildHome();}
    @Override protected void onResume(){
        super.onResume();if(new ParentalPrefs(this).enabled()){startActivity(new Intent(this,KidsActivity.class));return;}
        handler.removeCallbacks(tick);handler.post(tick);if(!observing){connectivity.registerDefaultNetworkCallback(callback);observing=true;}
    }
    @Override protected void onPause(){handler.removeCallbacks(tick);if(observing){connectivity.unregisterNetworkCallback(callback);observing=false;}super.onPause();}
    private int dp(int n){return TvUi.dp(this,n);}
    private void buildHome(){
        LinearLayout root=TvUi.column(this);root.setBackgroundColor(TvUi.BACKGROUND);root.setPadding(dp(42),dp(22),dp(42),dp(14));root.setClipChildren(false);root.setClipToPadding(false);setContentView(root);
        LinearLayout top=TvUi.row(this);top.setClipChildren(false);
        TextView logo=TvUi.text(this,"FIREFLY",17,TvUi.TEXT);logo.setLetterSpacing(.16f);logo.setTypeface(Typeface.create("sans-serif-medium",0));logo.setGravity(Gravity.CENTER_VERTICAL);
        top.addView(logo,new LinearLayout.LayoutParams(dp(152),dp(32)));
        top.addView(nav("首页",true,v->{}));top.addView(nav("直播",false,v->open(LiveActivity.class)));top.addView(nav("应用",false,v->open(AppsActivity.class)));top.addView(nav("儿童",false,v->open(KidsActivity.class)));
        top.addView(new View(this),new LinearLayout.LayoutParams(0,1,1));
        network=TvUi.text(this,"",12,TvUi.MUTED);network.setGravity(Gravity.CENTER_VERTICAL);top.addView(network);
        clock=TvUi.text(this,"",17,TvUi.TEXT);clock.setPadding(dp(18),0,dp(18),0);top.addView(clock);top.addView(nav("设置",false,v->open(SettingsActivity.class)));
        root.addView(top,new LinearLayout.LayoutParams(-1,dp(42)));
        ScrollView scroll=new ScrollView(this);scroll.setClipToPadding(false);scroll.setClipChildren(false);scroll.setVerticalScrollBarEnabled(false);scroll.setFillViewport(true);
        LinearLayout content=TvUi.column(this);content.setClipChildren(false);content.setClipToPadding(false);content.setPadding(dp(4),dp(13),dp(4),dp(12));scroll.addView(content);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        content.addView(hero(),new LinearLayout.LayoutParams(-1,dp(228)));
        LinearLayout section=TvUi.row(this);section.setPadding(0,dp(23),0,dp(14));TextView heading=TvUi.text(this,"你的应用",17,TvUi.TEXT);heading.setTypeface(Typeface.create("sans-serif-medium",0));section.addView(heading,new LinearLayout.LayoutParams(0,-2,1));
        TextView all=TvUi.text(this,"查看全部  ›",13,TvUi.MUTED);all.setPadding(dp(14),dp(5),dp(14),dp(5));all.setBackground(TvUi.focusBackground(this));TvUi.interactive(all,v->open(AppsActivity.class));section.addView(all);content.addView(section);
        LinearLayout apps=TvUi.row(this);apps.setClipChildren(false);apps.setClipToPadding(false);
        addApp(apps,"哔哩哔哩",AppLaunch.BILIBILI);addApp(apps,"酷喵",AppLaunch.YOUKU);addApp(apps,"奇异果",AppLaunch.IQIYI);addApp(apps,"SmartTube",AppLaunch.YOUTUBE);addApp(apps,"本地影院",AppLaunch.KODI);
        addAppCell(apps,TvUi.appCard(this,"儿童专区",null,"✦",v->open(KidsActivity.class)),true);content.addView(apps,new LinearLayout.LayoutParams(-1,dp(108)));
        LinearLayout footer=TvUi.row(this);footer.setPadding(dp(4),dp(10),dp(4),0);footer.addView(TvUi.text(this,"方向键选择  ·  确定打开  ·  Esc 返回",11,0xff737d8e),new LinearLayout.LayoutParams(0,-2,1));
        TextView remote=TvUi.text(this,"遥控器  ›",11,TvUi.MUTED);remote.setPadding(dp(12),dp(5),dp(12),dp(5));remote.setBackground(TvUi.focusBackground(this));TvUi.interactive(remote,v->open(RemoteActivity.class));footer.addView(remote);root.addView(footer);
    }
    private TextView nav(String label,boolean selected,View.OnClickListener click){
        TextView v=TvUi.text(this,label,14,selected?TvUi.TEXT:TvUi.MUTED);v.setGravity(Gravity.CENTER);v.setPadding(dp(15),dp(8),dp(15),dp(8));
        StateListDrawable navStates=new StateListDrawable();
        GradientDrawable focused=TvUi.rounded(this,0xff343b47,18);focused.setStroke(dp(2),0xffedf3fb);
        navStates.addState(new int[]{android.R.attr.state_focused},focused);
        navStates.addState(new int[]{android.R.attr.state_hovered},focused);
        navStates.addState(new int[]{android.R.attr.state_pressed},TvUi.rounded(this,0xff465365,18));
        navStates.addState(new int[0],TvUi.rounded(this,selected?0xff303640:0x00101216,18));
        v.setBackground(navStates);TvUi.interactive(v,click);return v;
    }
    private FrameLayout hero(){
        FrameLayout card=new FrameLayout(this);GradientDrawable bg=new GradientDrawable(GradientDrawable.Orientation.TL_BR,new int[]{0xff1d283a,0xff253c4d,0xff263144});bg.setCornerRadius(dp(18));card.setBackground(bg);card.setClipToOutline(true);card.addView(new CinemaArt(this),new FrameLayout.LayoutParams(-1,-1));
        LinearLayout text=TvUi.column(this);text.setPadding(dp(30),dp(24),dp(30),dp(24));
        TextView eyebrow=TvUi.text(this,"TELEVISION  /  "+ChannelCatalog.load(this).channels.size()+" 个直播频道",11,0xffb6c9d6);eyebrow.setLetterSpacing(.09f);text.addView(eyebrow);
        TextView title=TvUi.text(this,"精彩，正在发生。",34,0xfff5f7fa);title.setTypeface(Typeface.create("sans-serif-medium",0));LinearLayout.LayoutParams tp=new LinearLayout.LayoutParams(-2,-2);tp.topMargin=dp(18);text.addView(title,tp);
        TextView sub=TvUi.text(this,"新闻、体育、影视，随心切换。",14,0xffbdcad7);LinearLayout.LayoutParams sp=new LinearLayout.LayoutParams(-2,-2);sp.topMargin=dp(12);text.addView(sub,sp);
        LinearLayout actions=TvUi.row(this);actions.setClipChildren(false);actions.setPadding(0,dp(24),0,0);TextView watch=action("▶  看直播",true,v->open(LiveActivity.class));actions.addView(watch);
        TextView local=action("本地影院",false,v->AppLaunch.open(this,AppLaunch.KODI));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-2,dp(38));lp.leftMargin=dp(12);actions.addView(local,lp);text.addView(actions);card.addView(text,new FrameLayout.LayoutParams(-1,-1));watch.post(()->watch.requestFocus());return card;
    }
    private TextView action(String label,boolean primary,View.OnClickListener click){
        TextView v=TvUi.text(this,label,14,primary?0xff152130:TvUi.TEXT);v.setTypeface(Typeface.create("sans-serif-medium",0));v.setGravity(Gravity.CENTER);v.setPadding(dp(22),dp(10),dp(22),dp(10));
        if(primary){StateListDrawable states=new StateListDrawable();GradientDrawable f=TvUi.rounded(this,0xffffffff,22);f.setStroke(dp(2),0xffa3d4ee);states.addState(new int[]{android.R.attr.state_focused},f);states.addState(new int[0],TvUi.rounded(this,0xffe8eef3,22));v.setBackground(states);}else v.setBackground(TvUi.focusBackground(this));TvUi.interactive(v,click);return v;
    }
    private void addApp(LinearLayout row,String label,String[] packages){
        Intent intent=AppLaunch.resolve(getPackageManager(),packages);if(intent==null)return;Drawable icon=null;
        try{android.content.ComponentName component=intent.resolveActivity(getPackageManager());if(component!=null)icon=getPackageManager().getApplicationIcon(component.getPackageName());}catch(PackageManager.NameNotFoundException ignored){}
        addAppCell(row,TvUi.appCard(this,label,icon,"▶",v->AppLaunch.open(this,packages)),false);
    }
    private void addAppCell(LinearLayout row,View cell,boolean last){LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-1,1);if(!last)lp.rightMargin=dp(12);row.addView(cell,lp);}
    private void updateNetwork(){if(network==null||connectivity==null)return;NetworkCapabilities c=connectivity.getNetworkCapabilities(connectivity.getActiveNetwork());network.setText(c==null?"○  未连接":"●  "+(c.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET)?"有线网络":"已连接"));network.setTextColor(c==null?TvUi.MUTED:0xffa9c9bb);}
    private void open(Class<?> activity){startActivity(new Intent(this,activity));}
    @Override protected void handleBackAction(){ /* Home is the root of navigation. */ }
    @Override public boolean onKeyDown(int code,KeyEvent e){return code==KeyEvent.KEYCODE_BACK||super.onKeyDown(code,e);}
    /** Original vector illustration; no external images or fabricated programme art. */
    private static final class CinemaArt extends View {
        final Paint p=new Paint(Paint.ANTI_ALIAS_FLAG);
        CinemaArt(Context c){super(c);setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
        @Override protected void onDraw(Canvas c){
            float w=getWidth(),h=getHeight();p.setShader(new RadialGradient(w*.82f,h*.14f,w*.43f,new int[]{0x5872b0ae,0x00396c89},null,Shader.TileMode.CLAMP));c.drawRect(0,0,w,h,p);p.setShader(null);
            c.save();c.translate(w*.77f,h*.49f);c.rotate(-13);float sw=w*.27f,sh=h*.65f;p.setColor(0x18253649);c.drawRoundRect(new RectF(-sw*.5f,-sh*.5f,sw*.5f,sh*.5f),h*.065f,h*.065f,p);
            p.setStyle(Paint.Style.STROKE);p.setStrokeWidth(1.4f);p.setColor(0x385c8fa9);for(int n=0;n<4;n++){float a=n*h*.046f;c.drawRoundRect(new RectF(-sw*.5f+a,-sh*.5f+a,sw*.5f-a,sh*.5f-a),h*.04f,h*.04f,p);}p.setStyle(Paint.Style.FILL);p.setColor(0x557ec1d4);
            Path play=new Path();play.moveTo(-h*.04f,-h*.09f);play.lineTo(h*.10f,0);play.lineTo(-h*.04f,h*.09f);play.close();c.drawPath(play,p);c.restore();p.setColor(0x18ffffff);c.drawCircle(w*.94f,h*.83f,3,p);c.drawCircle(w*.65f,h*.16f,2,p);
        }
    }
}
