/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.util.Xml;
import org.xmlpull.v1.XmlPullParser;
import org.xmlpull.v1.XmlPullParserException;
import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/** Bounded XMLTV reader retaining only the channels shipped with this product. */
final class ProgramGuide {
    private static final DateTimeFormatter TIME =
            DateTimeFormatter.ofPattern("uuuuMMddHHmmss xx", Locale.ROOT);
    private final Map<String, List<Program>> entries = new HashMap<>();

    static ProgramGuide read(File file, ChannelCatalog catalog)
            throws IOException, XmlPullParserException {
        if (file.length() <= 0 || file.length() > 16 * 1024 * 1024) {
            throw new IOException("Invalid XMLTV size");
        }
        Set<String> allowed = new HashSet<>();
        for (ChannelCatalog.Channel channel : catalog.channels) {
            if (!channel.tvgId.isBlank()) {
                allowed.add(channel.tvgId);
            }
        }
        ProgramGuide guide = new ProgramGuide();
        try (FileInputStream input = new FileInputStream(file)) {
            XmlPullParser parser = Xml.newPullParser();
            parser.setFeature(XmlPullParser.FEATURE_PROCESS_NAMESPACES, false);
            parser.setFeature(XmlPullParser.FEATURE_PROCESS_DOCDECL, false);
            parser.setInput(input, "UTF-8");
            guide.parse(parser, allowed);
        }
        return guide;
    }

    private void parse(XmlPullParser parser, Set<String> allowed)
            throws IOException, XmlPullParserException {
        int total = 0;
        while (parser.next() != XmlPullParser.END_DOCUMENT) {
            if (Thread.currentThread().isInterrupted()) {
                throw new IOException("Guide loading cancelled");
            }
            if (parser.getEventType() != XmlPullParser.START_TAG
                    || !"programme".equals(parser.getName())) {
                continue;
            }
            total++;
            if (total > 200_000) {
                throw new IOException("XMLTV programme limit exceeded");
            }
            String channel = parser.getAttributeValue(null, "channel");
            if (allowed.contains(channel)) {
                add(parser, channel);
            }
        }
        if (entries.isEmpty()) {
            throw new IOException("No matching programmes in XMLTV guide");
        }
        for (List<Program> programmes : entries.values()) {
            programmes.sort((first, second) -> Long.compare(first.start, second.start));
        }
    }

    private void add(XmlPullParser parser, String channel)
            throws IOException, XmlPullParserException {
        long start = time(parser.getAttributeValue(null, "start"));
        long stop = time(parser.getAttributeValue(null, "stop"));
        String title = title(parser);
        if (start <= 0 || stop <= start || stop - start > 86_400_000 || title.isEmpty()) {
            return;
        }
        List<Program> programmes = entries.computeIfAbsent(channel, key -> new ArrayList<>());
        if (programmes.size() < 500) {
            programmes.add(new Program(start, stop, title.substring(0, Math.min(512, title.length()))));
        }
    }

    private static String title(XmlPullParser parser) throws IOException, XmlPullParserException {
        String title = "";
        int depth = parser.getDepth();
        int event;
        while ((event = parser.next()) != XmlPullParser.END_DOCUMENT) {
            if (event == XmlPullParser.END_TAG && parser.getDepth() == depth) {
                break;
            }
            if (event == XmlPullParser.START_TAG && "title".equals(parser.getName())) {
                title = parser.nextText().trim();
            }
        }
        return title;
    }

    private static long time(String value) {
        try {
            return OffsetDateTime.parse(value == null ? "" : value.trim(), TIME)
                    .toInstant().toEpochMilli();
        } catch (DateTimeParseException error) {
            return 0;
        }
    }

    String current(String channel) {
        long now = System.currentTimeMillis();
        for (Program programme : entries.getOrDefault(channel, List.of())) {
            if (programme.start <= now && now < programme.stop) {
                return "正在播出：" + programme.title;
            }
        }
        return "当前暂无节目单";
    }

    private static final class Program {
        final long start;
        final long stop;
        final String title;

        Program(long start, long stop, String title) {
            this.start = start;
            this.stop = stop;
            this.title = title;
        }
    }
}
