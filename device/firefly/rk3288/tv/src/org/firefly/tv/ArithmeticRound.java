/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import java.util.Random;

/** Offline arithmetic questions and a deterministic, restorable practice session. */
final class ArithmeticRound {
    static final String[] MODES = {"count", "add", "sub", "compare", "mixed"};
    final String kind;
    final int limit;
    final int left;
    final int right;
    final int result;
    final String instruction;
    final String equation;
    final String[] answers;
    final int correctIndex;

    ArithmeticRound(Random random, String mode, int maximum) {
        if (random == null) throw new IllegalArgumentException("A random source is required");
        limit = normalizeLimit(maximum);
        String requested = normalizeMode(mode);
        kind = "mixed".equals(requested) ? MODES[random.nextInt(4)] : requested;
        if ("count".equals(kind)) {
            left = 1 + random.nextInt(limit);
            right = 0;
            result = left;
            instruction = "数一数，一共有几个圆点？";
            equation = "一共有  ?  个";
        } else if ("add".equals(kind)) {
            int total = 1 + random.nextInt(limit);
            left = random.nextInt(total + 1);
            right = total - left;
            result = total;
            instruction = "把两组圆点放在一起，是多少？";
            equation = left + "  +  " + right + "  =  ?";
        } else if ("sub".equals(kind)) {
            left = 1 + random.nextInt(limit);
            right = random.nextInt(left + 1);
            result = left - right;
            instruction = "划掉的圆点拿走了，还剩几个？";
            equation = left + "  −  " + right + "  =  ?";
        } else {
            // Include equal quantities often enough for the equality choice to be useful.
            left = random.nextInt(limit + 1);
            right = random.nextInt(3) == 0 ? left : random.nextInt(limit + 1);
            result = Integer.compare(left, right);
            instruction = "比一比，左边和右边谁更多？";
            equation = left + "  ?  " + right;
        }
        correctIndex = random.nextInt(3);
        answers = new String[3];
        if ("compare".equals(kind)) {
            int[] values = {-1, 0, 1};
            answers[correctIndex] = comparison(result);
            int position = 1;
            for (int value : values) if (value != result) {
                answers[(correctIndex + position++) % 3] = comparison(value);
            }
        } else {
            int other = random.nextInt(limit);
            if (other >= result) other++;
            int last;
            do { last = random.nextInt(limit + 1); } while (last == result || last == other);
            answers[correctIndex] = Integer.toString(result);
            answers[(correctIndex + 1) % 3] = Integer.toString(other);
            answers[(correctIndex + 2) % 3] = Integer.toString(last);
        }
    }

    static String comparison(int value) {
        return value < 0 ? "左边少  <" : value > 0 ? "左边多  >" : "一样多  =";
    }

    static String normalizeMode(String mode) {
        for (String candidate : MODES) if (candidate.equals(mode)) return candidate;
        return "mixed";
    }

    static int normalizeLimit(int limit) { return limit == 5 || limit == 20 ? limit : 10; }
    static int normalizeQuestionCount(int count) { return count == 10 ? 10 : 5; }

    static String modeLabel(String mode) {
        switch (normalizeMode(mode)) {
            case "count": return "数一数";
            case "add": return "加一加";
            case "sub": return "减一减";
            case "compare": return "比大小";
            default: return "综合练习";
        }
    }

    /** No Android or watching-time dependency: practice can never grant video time. */
    static final class Session {
        static final int IGNORED = 0;
        static final int RETRY = -1;
        static final int CORRECT = 1;
        final String id;
        final String mode;
        final int limit;
        final int questionCount;
        final long seed;
        private int index;
        private int answered;
        private int firstCorrect;
        private boolean attempted;
        private boolean solved;

        Session(String id, String mode, int limit, int questionCount, long seed) {
            if (id == null || id.isEmpty() || id.length() > 128) {
                throw new IllegalArgumentException("Invalid practice session identity");
            }
            this.id = id;
            this.mode = normalizeMode(mode);
            this.limit = normalizeLimit(limit);
            this.questionCount = normalizeQuestionCount(questionCount);
            this.seed = seed;
        }

        ArithmeticRound question() {
            if (completed()) throw new IllegalStateException("Practice is complete");
            return new ArithmeticRound(new Random(seed ^ (0x9e3779b97f4a7c15L * (index + 1L))), mode, limit);
        }

        int answer(int choice) {
            if (completed() || solved || choice < 0 || choice >= 3) return IGNORED;
            boolean correct = choice == question().correctIndex;
            if (!attempted) {
                answered++;
                if (correct) firstCorrect++;
                attempted = true;
            }
            if (!correct) return RETRY;
            solved = true;
            return CORRECT;
        }

        boolean next() {
            if (!solved || completed()) return false;
            index++;
            attempted = false;
            solved = false;
            return true;
        }

        int index() { return index; }
        int answered() { return answered; }
        int firstCorrect() { return firstCorrect; }
        boolean attempted() { return attempted; }
        boolean solved() { return solved; }
        boolean completed() { return index == questionCount; }

        static Session restore(String id, String mode, int limit, int questionCount, long seed,
                int index, int answered, int firstCorrect, boolean attempted, boolean solved) {
            Session session = new Session(id, mode, limit, questionCount, seed);
            if (index < 0 || index > session.questionCount || firstCorrect < 0
                    || answered != index + (attempted ? 1 : 0) || firstCorrect > answered
                    || firstCorrect > index + (solved ? 1 : 0) || (solved && !attempted)
                    || (index == session.questionCount && (attempted || solved))) {
                throw new IllegalArgumentException("Invalid restored practice state");
            }
            session.index = index;
            session.answered = answered;
            session.firstCorrect = firstCorrect;
            session.attempted = attempted;
            session.solved = solved;
            return session;
        }
    }
}
