/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.util.Log;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.net.URI;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Loads the shipped catalog, or a previously validated update retained locally. */
final class ChannelCatalog {
    private static final String TAG = "FireflyChannels";
    private static final int MAXIMUM_BYTES = 2 * 1024 * 1024;
    final List<Channel> channels;

    private ChannelCatalog(List<Channel> channels) {
        this.channels = Collections.unmodifiableList(channels);
    }

    static ChannelCatalog load(Context context) {
        File cache = new File(context.getFilesDir(), "channels.json");
        List<File> candidates = List.of(cache,
                new File("/product/etc/firefly-tv/channels.json"));
        for (File candidate : candidates) {
            if (!candidate.isFile()) {
                continue;
            }
            try {
                return parse(read(candidate));
            } catch (IOException | JSONException | IllegalArgumentException error) {
                Log.w(TAG, "Cannot load catalog " + candidate, error);
            }
        }
        return new ChannelCatalog(new ArrayList<>());
    }

    private static String read(File file) throws IOException {
        long size = file.length();
        if (size <= 0 || size > MAXIMUM_BYTES) {
            throw new IOException("Catalog exceeds size limit");
        }
        byte[] bytes = Files.readAllBytes(file.toPath());
        if (bytes.length > MAXIMUM_BYTES) {
            throw new IOException("Catalog grew beyond size limit");
        }
        return new String(bytes, StandardCharsets.UTF_8);
    }

    static ChannelCatalog parse(String value) throws JSONException {
        JSONObject root = new JSONObject(value);
        JSONArray array = root.getJSONArray("channels");
        if (array.length() > 3000) {
            throw new JSONException("Too many channels");
        }
        List<Channel> channels = new ArrayList<>();
        Map<String, Boolean> seen = new LinkedHashMap<>();
        for (int index = 0; index < array.length(); index++) {
            JSONObject item = array.getJSONObject(index);
            Channel channel = channel(item, index + 1);
            if (seen.put(channel.id, Boolean.TRUE) != null) {
                throw new JSONException("Duplicate channel id");
            }
            channels.add(channel);
        }
        return new ChannelCatalog(channels);
    }

    private static Channel channel(JSONObject item, int number) throws JSONException {
        List<Source> sources = new ArrayList<>();
        JSONArray array = item.getJSONArray("sources");
        if (array.length() == 0 || array.length() > 20) {
            throw new JSONException("Invalid source count");
        }
        for (int index = 0; index < array.length(); index++) {
            sources.add(source(array.getJSONObject(index)));
        }
        String id = item.getString("id");
        if (id.isBlank() || id.length() > 160) {
            throw new JSONException("Invalid channel id");
        }
        return new Channel(id, item.getString("name"), item.optString("group", "其他"),
                item.optString("tvgId", id), item.optInt("number", number), sources);
    }

    private static Source source(JSONObject item) throws JSONException {
        String url = item.getString("url");
        URI uri = URI.create(url);
        String scheme = uri.getScheme();
        if ((!"https".equalsIgnoreCase(scheme) && !"http".equalsIgnoreCase(scheme))
                || uri.getHost() == null || uri.getUserInfo() != null) {
            throw new JSONException("Unsupported stream URL");
        }
        Map<String, String> headers = new LinkedHashMap<>();
        addHeader(headers, "User-Agent", item.optString("userAgent"));
        addHeader(headers, "Referer", item.optString("referer"));
        JSONObject resolver = item.optJSONObject("resolver");
        String provider = resolver == null ? "" : resolver.getString("provider");
        String channelId = resolver == null ? "" : resolver.getString("channelId");
        return new Source(url, headers, item.optBoolean("requiresProxy", false),
                "kodi".equals(item.optString("player")), provider, channelId);
    }

    private static void addHeader(Map<String, String> headers, String key, String value)
            throws JSONException {
        if (value.indexOf('\r') >= 0 || value.indexOf('\n') >= 0) {
            throw new JSONException("Invalid stream header");
        }
        if (!value.isEmpty()) {
            headers.put(key, value);
        }
    }

    static final class Channel {
        final String id;
        final String name;
        final String group;
        final String tvgId;
        final int number;
        final List<Source> sources;

        Channel(String id, String name, String group, String tvgId, int number,
                List<Source> sources) {
            this.id = id;
            this.name = name;
            this.group = group;
            this.tvgId = tvgId;
            this.number = number;
            this.sources = Collections.unmodifiableList(sources);
        }
    }

    static final class Source {
        final String url;
        final Map<String, String> headers;
        final boolean requiresProxy;
        final boolean kodi;
        final String resolverProvider;
        final String resolverChannelId;

        Source(String url, Map<String, String> headers, boolean requiresProxy,
                boolean kodi, String provider, String channelId) {
            this.url = url;
            this.headers = Collections.unmodifiableMap(headers);
            this.requiresProxy = requiresProxy;
            this.kodi = kodi;
            resolverProvider = provider;
            resolverChannelId = channelId;
        }
    }
}
