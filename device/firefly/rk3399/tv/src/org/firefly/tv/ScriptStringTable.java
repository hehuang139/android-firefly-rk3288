/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

/** Reads a bounded array of JavaScript string literals without executing code. */
final class ScriptStringTable {
    private static final int MAX_INPUT = 65_536;
    private static final int MAX_STRINGS = 512;
    private static final int MAX_STRING = 8_192;
    private final String input;
    private int position;

    private ScriptStringTable(String input) throws IOException {
        if (input == null || input.length() > MAX_INPUT) {
            throw invalid();
        }
        this.input = input;
    }

    static List<String> parse(String input) throws IOException {
        return new ScriptStringTable(input).readArray();
    }

    private List<String> readArray() throws IOException {
        whitespace();
        require('[');
        List<String> values = new ArrayList<>();
        whitespace();
        if (!take(']')) {
            while (true) {
                if (values.size() >= MAX_STRINGS) {
                    throw invalid();
                }
                values.add(string());
                whitespace();
                if (take(']')) {
                    break;
                }
                require(',');
                whitespace();
                // A trailing comma is valid JavaScript; sparse array holes are not.
                if (take(']')) {
                    break;
                }
            }
        }
        whitespace();
        if (position != input.length()) {
            throw invalid();
        }
        return values;
    }

    private String string() throws IOException {
        if (position >= input.length()) {
            throw invalid();
        }
        char quote = input.charAt(position++);
        if (quote != '\'' && quote != '"' && quote != '`') {
            throw invalid();
        }
        StringBuilder value = new StringBuilder();
        while (position < input.length()) {
            char c = input.charAt(position++);
            if (c == quote) {
                return value.toString();
            }
            if (quote == '`' && c == '$' && peek('{')) {
                throw invalid();
            }
            if (c == '\\') {
                if (position >= input.length()) {
                    throw invalid();
                }
                char escape = input.charAt(position++);
                switch (escape) {
                    case '\n':
                        continue;
                    case '\r':
                        take('\n');
                        continue;
                    case '\\': case '\'': case '"': case '`': case '/':
                        c = escape;
                        break;
                    case '$':
                        if (quote != '`') throw invalid();
                        c = '$';
                        break;
                    case 'n': c = '\n'; break;
                    case 'r': c = '\r'; break;
                    case 't': c = '\t'; break;
                    case 'b': c = '\b'; break;
                    case 'f': c = '\f'; break;
                    case 'v': c = '\u000b'; break;
                    case '0':
                        if (position < input.length() && input.charAt(position) >= '0'
                                && input.charAt(position) <= '9') throw invalid();
                        c = '\0';
                        break;
                    case 'x': c = hex(2); break;
                    case 'u': c = hex(4); break;
                    default: throw invalid();
                }
            } else if (c == '\n' || c == '\r') {
                if (quote != '`') {
                    throw invalid();
                }
                if (c == '\r') take('\n');
                c = '\n';
            }
            if (value.length() >= MAX_STRING) {
                throw invalid();
            }
            value.append(c);
        }
        throw invalid();
    }

    private char hex(int digits) throws IOException {
        int value = 0;
        for (int i = 0; i < digits; i++) {
            if (position >= input.length()) throw invalid();
            char c = input.charAt(position++);
            int digit = c >= '0' && c <= '9' ? c - '0'
                    : c >= 'a' && c <= 'f' ? c - 'a' + 10
                    : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1;
            if (digit < 0) throw invalid();
            value = value * 16 + digit;
        }
        return (char) value;
    }

    private void whitespace() {
        while (position < input.length()) {
            char c = input.charAt(position);
            if (c != ' ' && c != '\t' && c != '\r' && c != '\n') break;
            position++;
        }
    }

    private boolean peek(char expected) {
        return position < input.length() && input.charAt(position) == expected;
    }

    private boolean take(char expected) {
        if (!peek(expected)) return false;
        position++;
        return true;
    }

    private void require(char expected) throws IOException {
        if (!take(expected)) throw invalid();
    }

    private static IOException invalid() {
        // Input may contain runtime metadata. Keep it out of exception messages.
        return new IOException("Invalid literal string table");
    }
}
