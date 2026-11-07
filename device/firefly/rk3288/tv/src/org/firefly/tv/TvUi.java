/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;
import android.app.Activity;
import android.content.Context;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.StateListDrawable;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;

final class TvUi {
    static final int BACKGROUND=0xff101216,PANEL=0xff22262e,TEXT=0xfff3f4f7,MUTED=0xffa7adb9,ACCENT=0xffb8d8e8;
    private TvUi(){}
    static int dp(Context c,int n){return Math.round(n*c.getResources().getDisplayMetrics().density);}
    static LinearLayout column(Context c){LinearLayout v=new LinearLayout(c);v.setOrientation(1);v.setClipChildren(false);v.setClipToPadding(false);return v;}
    static LinearLayout row(Context c){LinearLayout v=new LinearLayout(c);v.setOrientation(0);v.setGravity(Gravity.CENTER_VERTICAL);v.setClipChildren(false);v.setClipToPadding(false);return v;}
    static LinearLayout page(Activity a,String title,String subtitle){
        LinearLayout p=column(a);p.setBackgroundColor(BACKGROUND);p.setPadding(dp(a,44),dp(a,28),dp(a,44),dp(a,24));
        TextView heading=text(a,title,27,TEXT);heading.setTypeface(Typeface.create("sans-serif-medium",0));p.addView(heading);
        TextView detail=text(a,subtitle,14,MUTED);detail.setPadding(0,dp(a,8),0,dp(a,22));p.addView(detail);a.setContentView(p);return p;
    }
    static TextView text(Context c,String value,int size,int color){
        TextView v=new TextView(c);v.setText(value);v.setTextSize(size);v.setTextColor(color);v.setFontFeatureSettings("kern");v.setIncludeFontPadding(false);return v;
    }
    static GradientDrawable rounded(Context c,int color,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(c,radius));return d;}
    static StateListDrawable focusBackground(Context c){
        StateListDrawable s=new StateListDrawable();GradientDrawable f=rounded(c,0xff343b47,12);f.setStroke(dp(c,2),0xffedf3fb);
        s.addState(new int[]{android.R.attr.state_pressed},rounded(c,0xff465365,12));s.addState(new int[]{android.R.attr.state_focused},f);
        s.addState(new int[]{android.R.attr.state_hovered},f);s.addState(new int[0],rounded(c,PANEL,12));return s;
    }
    static void interactive(View v,View.OnClickListener click){
        v.setId(View.generateViewId());v.setFocusable(true);v.setFocusableInTouchMode(true);v.setClickable(true);v.setOnClickListener(click);
        v.setOnFocusChangeListener((view,focus)->{
            if(focus){
                android.view.ViewParent parent=view.getParent();
                while(parent instanceof android.view.ViewGroup){
                    android.view.ViewGroup group=(android.view.ViewGroup)parent;
                    group.setClipChildren(false);group.setClipToPadding(false);parent=group.getParent();
                }
            }
            // Full-width list rows use the outline only, avoiding clipping at viewport edges.
            boolean row=view instanceof Button;
            view.animate().scaleX(focus&&!row?1.035f:1f).scaleY(focus&&!row?1.035f:1f).setDuration(130).start();
        });
        v.setOnHoverListener((view,event)->{if(event.getAction()==MotionEvent.ACTION_HOVER_ENTER)view.requestFocus();return false;});
    }
    static Button button(Context c,String label,View.OnClickListener click){
        Button b=new Button(c);b.setText(label);b.setTextSize(17);b.setTextColor(TEXT);b.setAllCaps(false);b.setGravity(Gravity.CENTER_VERTICAL|Gravity.START);
        b.setMinHeight(dp(c,54));b.setPadding(dp(c,20),dp(c,10),dp(c,20),dp(c,10));b.setBackground(focusBackground(c));interactive(b,click);return b;
    }
    static LinearLayout appCard(Context c,String label,Drawable icon,String fallback,View.OnClickListener click){
        LinearLayout card=column(c);card.setGravity(Gravity.CENTER);card.setPadding(dp(c,10),dp(c,14),dp(c,10),dp(c,10));card.setBackground(focusBackground(c));interactive(card,click);
        if(icon!=null){ImageView image=new ImageView(c);image.setImageDrawable(icon);image.setScaleType(ImageView.ScaleType.FIT_CENTER);card.addView(image,new LinearLayout.LayoutParams(dp(c,48),dp(c,48)));}
        else{TextView glyph=text(c,fallback,28,TEXT);glyph.setGravity(Gravity.CENTER);card.addView(glyph,new LinearLayout.LayoutParams(dp(c,48),dp(c,48)));}
        TextView name=text(c,label,13,TEXT);name.setGravity(Gravity.CENTER);name.setSingleLine(true);name.setEllipsize(android.text.TextUtils.TruncateAt.END);
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(c,10);card.addView(name,p);card.setContentDescription(label);return card;
    }
    static void addButton(LinearLayout p,Button b){LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.bottomMargin=dp(p.getContext(),10);p.addView(b,lp);}
    static void addWeighted(LinearLayout p,View c,int h){LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,dp(p.getContext(),h),1);lp.rightMargin=dp(p.getContext(),12);p.addView(c,lp);}
    static void emphasize(TextView v){v.setTypeface(Typeface.DEFAULT,Typeface.BOLD);}
}
