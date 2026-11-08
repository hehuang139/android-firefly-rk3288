/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.util.Log;
import org.json.JSONException;
import org.json.JSONObject;
import org.xmlpull.v1.XmlPullParserException;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardCopyOption;
import javax.net.ssl.HttpsURLConnection;

/** Retains the last parsed guide if a bounded HTTPS refresh fails. */
final class GuideLoader {
    private static final String TAG = "FireflyGuide";
    private static final File BAKED = new File("/product/etc/firefly-tv/epg.xml");

    private GuideLoader() { }

    static ProgramGuide load(Context context, ChannelCatalog catalog) {
        File cached = new File(context.getFilesDir(), "epg.xml");
        ProgramGuide previous = parse(cached.isFile() ? cached : BAKED, catalog);
        if (previous == null && cached.isFile()) {
            previous = parse(BAKED, catalog);
        }
        File temporary = new File(context.getFilesDir(), "epg.xml.download");
        try {
            File settings = new File("/product/etc/firefly-tv/epg-settings.json");
            JSONObject options = new JSONObject(Files.readString(settings.toPath(),
                    StandardCharsets.UTF_8));
            if (!options.optBoolean("enabled", false)) return previous;
            long interval = Math.max(1, options.optInt("refreshIntervalHours", 12)) * 3_600_000L;
            if (cached.isFile() && System.currentTimeMillis() - cached.lastModified() < interval) {
                return previous;
            }
            download(options.getString("source"), temporary);
            ProgramGuide refreshed = ProgramGuide.read(temporary, catalog);
            Files.move(temporary.toPath(), cached.toPath(), StandardCopyOption.ATOMIC_MOVE,
                    StandardCopyOption.REPLACE_EXISTING);
            return refreshed;
        } catch (IOException | JSONException | XmlPullParserException error) {
            Log.w(TAG, "Retaining existing guide after refresh failure", error);
            return previous;
        } finally {
            if (temporary.exists() && !temporary.delete()) {
                Log.w(TAG, "Cannot remove temporary guide download");
            }
        }
    }

    private static ProgramGuide parse(File file, ChannelCatalog catalog) {
        try {
            return ProgramGuide.read(file, catalog);
        } catch (IOException | XmlPullParserException error) {
            Log.w(TAG, "Cannot parse guide " + file, error);
            return null;
        }
    }

    private static void download(String address, File target) throws IOException {
        URL url = new URL(address);
        if (!"https".equals(url.getProtocol()) || url.getUserInfo() != null) {
            throw new IOException("Guide refresh requires HTTPS");
        }
        HttpsURLConnection connection = (HttpsURLConnection) url.openConnection();
        connection.setConnectTimeout(10_000);
        connection.setReadTimeout(10_000);
        connection.setRequestProperty("User-Agent", "Firefly-TV/1.0");
        try {
            if (connection.getResponseCode() != 200) {
                throw new IOException("Guide HTTP status " + connection.getResponseCode());
            }
            copy(connection, target);
        } finally {
            connection.disconnect();
        }
    }

    private static void copy(HttpsURLConnection connection, File target) throws IOException {
        try (InputStream input = connection.getInputStream();
                OutputStream output = Files.newOutputStream(target.toPath())) {
            byte[] buffer = new byte[16 * 1024];
            int size;
            int total = 0;
            while ((size = input.read(buffer)) != -1) {
                total += size;
                if (total > 16 * 1024 * 1024 || Thread.currentThread().isInterrupted()) {
                    throw new IOException("Guide download exceeded size limit or was cancelled");
                }
                output.write(buffer, 0, size);
            }
        }
    }
}
