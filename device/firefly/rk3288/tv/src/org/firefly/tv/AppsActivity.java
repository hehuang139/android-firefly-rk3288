/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.graphics.drawable.Drawable;
import android.os.Bundle;
import android.view.View;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public final class AppsActivity extends TvActivity {
    @Override protected void onCreate(Bundle state){
        super.onCreate(state);LinearLayout page=TvUi.page(this,"应用","你的大屏应用，尽在这里");
        ScrollView scroll=new ScrollView(this);scroll.setClipToPadding(false);scroll.setClipChildren(false);scroll.setVerticalScrollBarEnabled(false);
        LinearLayout grid=TvUi.column(this);grid.setClipChildren(false);grid.setClipToPadding(false);grid.setPadding(TvUi.dp(this,5),TvUi.dp(this,5),TvUi.dp(this,5),TvUi.dp(this,5));
        PackageManager pm=getPackageManager();Map<String,String> apps=new LinkedHashMap<>();collect(pm,Intent.CATEGORY_LEANBACK_LAUNCHER,apps);collect(pm,Intent.CATEGORY_LAUNCHER,apps);
        Map<String,String> sorted=new TreeMap<>();apps.forEach((name,label)->sorted.put(label+"\u0000"+name,name));
        LinearLayout row=null;View first=null;int index=0;
        for(String name:sorted.values()){
            if(index%5==0){row=TvUi.row(this);row.setClipChildren(false);LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,TvUi.dp(this,112));rp.bottomMargin=TvUi.dp(this,16);grid.addView(row,rp);}
            Drawable icon=null;try{icon=pm.getApplicationIcon(name);}catch(PackageManager.NameNotFoundException ignored){}
            View card=TvUi.appCard(this,apps.get(name),icon,"◈",v->AppLaunch.open(this,name));LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(0,-1,1);if(index%5!=4)cp.rightMargin=TvUi.dp(this,14);row.addView(card,cp);if(first==null)first=card;index++;
        }
        if(row!=null)while(index%5!=0){LinearLayout.LayoutParams empty=new LinearLayout.LayoutParams(0,1,1);if(index%5!=4)empty.rightMargin=TvUi.dp(this,14);row.addView(new View(this),empty);index++;}
        scroll.addView(grid);page.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));if(first!=null)first.requestFocus();
    }
    private void collect(PackageManager pm,String category,Map<String,String> result){
        for(ResolveInfo info:pm.queryIntentActivities(new Intent(Intent.ACTION_MAIN).addCategory(category),0)){String name=info.activityInfo.packageName;if(!getPackageName().equals(name))result.put(name,info.loadLabel(pm).toString());}
    }
}
