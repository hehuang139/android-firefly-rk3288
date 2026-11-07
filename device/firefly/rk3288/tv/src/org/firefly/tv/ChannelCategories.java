/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Display-only classifications. Every entry is an index into the unchanged catalog. */
final class ChannelCategories {
    private ChannelCategories() {}

    static final class Group {
        final String key;
        final String label;
        final List<Integer> indices;

        Group(String key, String label, List<Integer> indices) {
            this.key = key;
            this.label = label;
            this.indices = Collections.unmodifiableList(new ArrayList<>(indices));
        }
    }

    // Administrative order, with the special administrative regions presented
    // separately below. A display label never replaces the catalog's metadata.
    private static final String[][] PROVINCES = {
        {"11", "北京", "北京市"}, {"12", "天津", "天津市"},
        {"13", "河北", "河北省"}, {"14", "山西", "山西省"},
        {"15", "内蒙古", "内蒙古自治区"}, {"21", "辽宁", "辽宁省"},
        {"22", "吉林", "吉林省"}, {"23", "黑龙江", "黑龙江省"},
        {"31", "上海", "上海市"}, {"32", "江苏", "江苏省"},
        {"33", "浙江", "浙江省"}, {"34", "安徽", "安徽省"},
        {"35", "福建", "福建省"}, {"36", "江西", "江西省"},
        {"37", "山东", "山东省"}, {"41", "河南", "河南省"},
        {"42", "湖北", "湖北省"}, {"43", "湖南", "湖南省"},
        {"44", "广东", "广东省"}, {"45", "广西", "广西壮族自治区"},
        {"46", "海南", "海南省"}, {"50", "重庆", "重庆市"},
        {"51", "四川", "四川省"}, {"52", "贵州", "贵州省"},
        {"53", "云南", "云南省"}, {"54", "西藏", "西藏自治区"},
        {"61", "陕西", "陕西省"}, {"62", "甘肃", "甘肃省"},
        {"63", "青海", "青海省"}, {"64", "宁夏", "宁夏回族自治区"},
        {"65", "新疆", "新疆维吾尔自治区"},
    };
    private static final String[][] TYPES = {
        {"general", "综合"}, {"news", "新闻"}, {"film", "影视"},
        {"sports", "体育"}, {"children", "儿童"}, {"documentary", "纪录"},
        {"education", "科教"}, {"arts", "文艺综艺"}, {"life", "生活"},
        {"agriculture", "农业"}, {"finance", "财经"}, {"military", "军事"},
        {"international", "国际"},
    };
    private static final Pattern CCTV_ID = Pattern.compile("^cctv[-_ ]?(\\d{1,2})(?:plus|\\+)?(?:[.]cn)?$");
    private static final Pattern CCTV_NAME = Pattern.compile("^cctv[- ]?(\\d{1,2})(?:\\+)?(?:\\D|$)");

    static List<Group> regions(List<ChannelCatalog.Channel> channels) {
        Map<String, List<Integer>> entries = new LinkedHashMap<>();
        Map<String, String> labels = new LinkedHashMap<>();
        for (int index = 0; index < channels.size(); index++) {
            ChannelCatalog.Channel channel = channels.get(index);
            String key;
            String label;
            if (central(channel)) {
                key = "central";
                label = "中央";
            } else if (hongKongMacaoTaiwan(channel)) {
                key = "hmt";
                label = "港澳台";
            } else {
                String[] province = province(channel);
                if (province != null) {
                    key = "province-" + province[0];
                    label = province[1];
                } else if (international(channel)) {
                    key = "international";
                    label = "国际";
                } else {
                    key = "other";
                    label = "其他";
                }
            }
            entries.computeIfAbsent(key, unused -> new ArrayList<>()).add(index);
            labels.put(key, label);
        }
        List<String> keys = new ArrayList<>(entries.keySet());
        keys.sort(Comparator.comparingInt(ChannelCategories::regionOrder));
        List<Group> groups = new ArrayList<>();
        groups.add(all(channels.size()));
        for (String key : keys) {
            List<Integer> indices = entries.get(key);
            // Sort the display index copy only. Provincial satellite services
            // precede that province's local services; ties keep catalog order.
            if (key.startsWith("province-")) {
                indices.sort(Comparator.comparingInt((Integer index) -> satellite(channels.get(index)) ? 0 : 1)
                        .thenComparingInt(Integer::intValue));
            }
            groups.add(new Group(key, labels.get(key), indices));
        }
        return Collections.unmodifiableList(groups);
    }

    static List<Group> types(List<ChannelCatalog.Channel> channels) {
        Map<String, List<Integer>> entries = new LinkedHashMap<>();
        for (String[] type : TYPES) {
            entries.put(type[0], new ArrayList<>());
        }
        for (int index = 0; index < channels.size(); index++) {
            for (String key : typeKeys(channels.get(index))) {
                entries.get(key).add(index);
            }
        }
        List<Group> groups = new ArrayList<>();
        groups.add(all(channels.size()));
        for (String[] type : TYPES) {
            List<Integer> indices = entries.get(type[0]);
            if (!indices.isEmpty()) {
                groups.add(new Group(type[0], type[1], indices));
            }
        }
        return Collections.unmodifiableList(groups);
    }

    static Set<String> typeKeys(ChannelCatalog.Channel channel) {
        Set<String> keys = new LinkedHashSet<>();
        // Administrative categories (央视/卫视/省级/地市/区县) are not
        // genre evidence. Explicit genre categories take priority over names.
        addRoles(keys, text(channel.category));
        String id = text(channel.id);
        String name = text(channel.name);
        int cctv = cctvNumber(id, name);
        if (cctv > 0) {
            switch (cctv) {
                case 1: keys.add("general"); break;
                case 2: keys.add("finance"); break;
                case 3: case 11: case 15: keys.add("arts"); break;
                case 4: keys.add("general"); keys.add("international"); break;
                case 5: case 16: keys.add("sports"); break;
                case 6: case 8: keys.add("film"); break;
                case 7: keys.add("military"); break;
                case 9: keys.add("documentary"); break;
                case 10: case 12: keys.add("education"); break;
                case 13: keys.add("news"); break;
                case 14: keys.add("children"); break;
                case 17: keys.add("agriculture"); break;
                default: break;
            }
        }
        if (cgtn(channel)) {
            keys.add("international");
            if (contains(id + " " + name, "documentary", "discoveringchina", "discovering china", "纪录", "纪实")) {
                keys.add("documentary");
            } else if (contains(id + " " + name, "chinatravel", "china travel", "旅游")) {
                keys.add("life");
            } else {
                keys.add("news");
                if (contains(id + " " + name, "globalbiz", "global biz")) {
                    keys.add("finance");
                }
            }
        }
        if (id.startsWith("cetv") || name.startsWith("中国教育电视台")
                || id.startsWith("cndfilmmiddleschool") || name.contains("中央新影·中学生")) {
            keys.add("education");
        }
        // Only stable channel roles are used. There is no EPG/program-title
        // input, and an education/youth channel is not automatically a child channel.
        addRoles(keys, name);
        if (satellite(channel) && keys.isEmpty()) {
            keys.add("general");
        }
        if (keys.isEmpty()) {
            keys.add("general");
        }
        return Collections.unmodifiableSet(keys);
    }

    private static void addRoles(Set<String> keys, String value) {
        if (contains(value, "综合", "general")) keys.add("general");
        if (contains(value, "新闻", "资讯", "news")) keys.add("news");
        if (contains(value, "影视", "电影", "电视剧", "剧场", "movie", "film")) keys.add("film");
        if (contains(value, "体育", "奥林匹克", "奥运", "赛事", "sport")) keys.add("sports");
        if (contains(value, "少儿", "儿童", "青少", "卡通", "动画", "children", "kids", "cartoon")) keys.add("children");
        if (contains(value, "纪录", "纪实", "documentary")) keys.add("documentary");
        if (contains(value, "科教", "教科", "教育", "科技", "法治", "法制", "science", "education")) keys.add("education");
        if (contains(value, "文艺", "综艺", "娱乐", "音乐", "戏曲", "秦腔", "戏剧", "文化", "variety", "music")) keys.add("arts");
        if (contains(value, "生活", "民生", "休闲", "旅游", "文旅", "健康", "银龄", "lifestyle", "travel")) keys.add("life");
        if (contains(value, "农业", "农村", "农牧", "农林", "乡村", "agriculture", "rural")) keys.add("agriculture");
        if (contains(value, "财经", "经济", "金融", "证券", "财富", "经视", "finance", "business")) keys.add("finance");
        if (contains(value, "军事", "国防", "军旅", "military", "defense")) keys.add("military");
        if (contains(value, "国际", "international")) keys.add("international");
    }

    private static boolean central(ChannelCatalog.Channel channel) {
        String id = text(channel.id);
        String name = text(channel.name);
        String category = text(channel.category);
        return id.startsWith("cctv") || name.startsWith("cctv") || name.startsWith("央视")
                || cgtn(channel) || id.startsWith("cetv") || name.startsWith("中国教育电视台")
                || id.startsWith("cndfilm") || name.startsWith("中央新影")
                || category.equals("央视") || category.equals("中央") || category.equals("中央其他");
    }

    private static boolean cgtn(ChannelCatalog.Channel channel) {
        return text(channel.id).startsWith("cgtn") || text(channel.name).startsWith("cgtn")
                || text(channel.group).contains("央视国际") || text(channel.category).contains("央视国际");
    }

    private static boolean satellite(ChannelCatalog.Channel channel) {
        return text(channel.category).equals("卫视") || text(channel.name).contains("卫视");
    }

    private static boolean hongKongMacaoTaiwan(ChannelCatalog.Channel channel) {
        String code = provinceCode(channel);
        String value = text(channel.province) + " " + text(channel.group);
        String id = text(channel.id);
        return code.equals("71") || code.equals("81") || code.equals("82")
                || contains(value, "香港", "澳门", "台湾", "港澳台", "港台")
                || id.endsWith(".hk") || id.endsWith(".mo") || id.endsWith(".tw");
    }

    private static String[] province(ChannelCatalog.Channel channel) {
        String code = provinceCode(channel);
        for (String[] province : PROVINCES) {
            if (province[0].equals(code)) return province;
        }
        String value = text(channel.province);
        for (String[] province : PROVINCES) {
            if (value.equals(province[1]) || value.equals(province[2])) return province;
        }
        // Older public catalogs have a group but no province metadata. Match
        // only a group prefix, never a channel's name or a current programme.
        String group = text(channel.group);
        for (String[] province : PROVINCES) {
            if (group.equals(province[1]) || group.startsWith(province[2])
                    || group.startsWith(province[1] + " ") || group.startsWith(province[1] + "·")) return province;
        }
        return null;
    }

    private static String provinceCode(ChannelCatalog.Channel channel) {
        String code = text(channel.provinceCode);
        return code.matches("[0-9]{2}(?:[0-9]{4})?") ? code.substring(0, 2) : "";
    }

    private static boolean international(ChannelCatalog.Channel channel) {
        String id = text(channel.id);
        return contains(text(channel.group) + " " + text(channel.category), "国际", "海外", "境外", "international")
                || (id.matches(".*[.][a-z]{2}") && !id.endsWith(".cn"));
    }

    private static int regionOrder(String key) {
        if (key.equals("central")) return 0;
        if (key.startsWith("province-")) return 100 + Integer.parseInt(key.substring(9));
        if (key.equals("hmt")) return 200;
        if (key.equals("international")) return 201;
        return 202;
    }

    private static int cctvNumber(String id, String name) {
        Matcher match = CCTV_ID.matcher(id);
        if (!match.matches()) {
            match = CCTV_NAME.matcher(name);
            if (!match.find()) return 0;
        }
        return Integer.parseInt(match.group(1));
    }

    private static Group all(int count) {
        List<Integer> indices = new ArrayList<>();
        for (int index = 0; index < count; index++) indices.add(index);
        return new Group("all", "全部", indices);
    }

    private static String text(String value) {
        return value == null ? "" : value.trim().toLowerCase(Locale.ROOT);
    }

    private static boolean contains(String value, String... terms) {
        for (String term : terms) if (value.contains(term)) return true;
        return false;
    }
}
