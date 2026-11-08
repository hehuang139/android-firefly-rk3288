/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Random;
import java.util.Set;

/** Production question/session/statistics tests; Android rendering is not emulated. */
public final class ArithmeticHostTest {
    private static int questions;
    private static int restoredSessions;

    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) throws Exception {
        generateQuestions();
        sessionScoringAndRestore();
        progressIsIdempotentAndIsolated();
        pictureChallengeInputGuard();
        System.out.println("Arithmetic questions verified: " + questions);
        System.out.println("Session restorations verified: " + restoredSessions);
        System.out.println("Completed-round statistics, repeated submission, retry after failed commit, and concurrency: passed");
        System.out.println("Picture challenge cooldown, stale callbacks, retries, and duplicate confirmation: passed");
    }

    private static void generateQuestions() {
        Random random = new Random(730219L);
        for (int limit : new int[] {5, 10, 20}) {
            for (String mode : ArithmeticRound.MODES) {
                Set<String> kinds = new HashSet<>();
                Set<Integer> answerPositions = new HashSet<>();
                boolean zeroResult = false;
                boolean maximumResult = false;
                for (int i = 0; i < 700; i++) {
                    ArithmeticRound q = new ArithmeticRound(random, mode, limit);
                    questions++;
                    kinds.add(q.kind);
                    answerPositions.add(q.correctIndex);
                    check(q.limit == limit, "Limit changed");
                    check(q.left >= 0 && q.left <= limit && q.right >= 0 && q.right <= limit,
                            "An operand exceeds its range");
                    check(q.instruction != null && !q.instruction.isEmpty() && !q.equation.isEmpty(), "Missing question text");
                    check(q.answers.length == 3 && new HashSet<>(Arrays.asList(q.answers)).size() == 3,
                            "Three distinct choices required");
                    check(q.correctIndex >= 0 && q.correctIndex < 3, "Invalid correct index");
                    if ("compare".equals(q.kind)) {
                        check(q.result == Integer.compare(q.left, q.right), "Comparison mismatch");
                        check(q.answers[q.correctIndex].equals(ArithmeticRound.comparison(q.result)), "Comparison answer mismatch");
                        check(new HashSet<>(Arrays.asList(q.answers)).equals(new HashSet<>(Arrays.asList(
                                ArithmeticRound.comparison(-1), ArithmeticRound.comparison(0), ArithmeticRound.comparison(1)))),
                                "Comparison choices incomplete");
                    } else {
                        check(q.result >= 0 && q.result <= limit, "Result exceeds its range");
                        if ("count".equals(q.kind)) check(q.result == q.left && q.left >= 1, "Count mismatch");
                        if ("add".equals(q.kind)) check(q.result == q.left + q.right, "Addition mismatch");
                        if ("sub".equals(q.kind)) check(q.result == q.left - q.right && q.right <= q.left, "Negative subtraction");
                        check(Integer.parseInt(q.answers[q.correctIndex]) == q.result, "Wrong correct choice");
                        for (String answer : q.answers) {
                            int value = Integer.parseInt(answer);
                            check(value >= 0 && value <= limit, "Distractor exceeds its range");
                        }
                        zeroResult |= q.result == 0;
                        maximumResult |= q.result == limit;
                    }
                }
                check(answerPositions.size() == 3, "Correct positions do not vary");
                check(kinds.size() == ("mixed".equals(mode) ? 4 : 1), "Mixed coverage missing");
                if (!"compare".equals(mode)) check(maximumResult, "Maximum boundary never generated");
                if ("sub".equals(mode)) check(zeroResult, "Zero subtraction never generated");
            }
        }
        check(ArithmeticRound.normalizeMode(null).equals("mixed"), "Missing mode default");
        check(ArithmeticRound.normalizeMode("unexpected").equals("mixed"), "Unknown mode default");
        check(ArithmeticRound.normalizeLimit(200) == 10, "Invalid maximum default");
        check(ArithmeticRound.normalizeQuestionCount(30) == 5, "Invalid count default");
    }

    private static ArithmeticRound.Session copy(ArithmeticRound.Session source) {
        restoredSessions++;
        return ArithmeticRound.Session.restore(source.id, source.mode, source.limit, source.questionCount,
                source.seed, source.index(), source.answered(), source.firstCorrect(), source.attempted(), source.solved());
    }

    private static void sessionScoringAndRestore() {
        for (String mode : ArithmeticRound.MODES) for (int limit : new int[] {5, 10, 20}) {
            for (int count : new int[] {5, 10}) {
                ArithmeticRound.Session session = new ArithmeticRound.Session(mode + limit + count, mode, limit, count, 1234L);
                int expectedFirstCorrect = 0;
                for (int i = 0; i < count; i++) {
                    ArithmeticRound question = session.question();
                    ArithmeticRound.Session same = copy(session);
                    check(Arrays.equals(question.answers, same.question().answers)
                                    && question.equation.equals(same.question().equation), "Restoration changed current question");
                    check(session.answer(-1) == ArithmeticRound.Session.IGNORED
                                    && session.answer(3) == ArithmeticRound.Session.IGNORED
                                    && session.answered() == i, "Invalid input consumed a question");
                    check(!session.next(), "Unanswered question advanced");
                    if (i % 2 == 0) {
                        check(session.answer((question.correctIndex + 1) % 3) == ArithmeticRound.Session.RETRY,
                                "Wrong answer was accepted");
                        check(!session.next(), "Wrong answer advanced");
                        session = copy(session);
                        check(session.answer((question.correctIndex + 1) % 3) == ArithmeticRound.Session.RETRY,
                                "Retry failed");
                    } else expectedFirstCorrect++;
                    check(session.answer(question.correctIndex) == ArithmeticRound.Session.CORRECT, "Correct answer rejected");
                    check(session.answer(question.correctIndex) == ArithmeticRound.Session.IGNORED, "Double confirmation was counted");
                    check(session.answered() == i + 1 && session.firstCorrect() == expectedFirstCorrect,
                            "First-answer statistics mismatch");
                    session = copy(session);
                    check(session.answer(question.correctIndex) == ArithmeticRound.Session.IGNORED,
                            "Restored solved question counted again");
                    check(session.next(), "Solved question did not advance");
                    check(!session.next(), "Repeated next skipped a question");
                }
                check(session.completed() && session.answered() == count && session.firstCorrect() == count / 2,
                        "Completed totals mismatch");
                session = copy(session);
                check(session.completed() && session.answer(0) == ArithmeticRound.Session.IGNORED && !session.next(),
                        "Completed restored session accepted input");
            }
        }
        boolean rejected = false;
        try { ArithmeticRound.Session.restore("x", "add", 10, 5, 1, 0, 0, 1, false, false); }
        catch (IllegalArgumentException expected) { rejected = true; }
        check(rejected, "Malformed restored score accepted");
    }

    private static void progressIsIdempotentAndIsolated() throws Exception {
        Context context = new Context();
        SharedPreferences parental = context.getSharedPreferences("parental", 0);
        parental.edit().putInt("daily_minutes", 35).putLong("daily_spent", 9999).commit();
        KidsProgress first = new KidsProgress(context);
        check(first.completedRounds() == 0 && first.answeredQuestions() == 0 && first.firstTryCorrect() == 0,
                "Unexpected initial progress");
        check(first.lastMode().equals("mixed") && first.lastLimit() == 10, "Unexpected initial last options");
        check(first.recordRound("one", "sub", 5, 5, 3), "First result not recorded");
        check(!first.recordRound("one", "sub", 5, 5, 3), "Same completion counted twice");
        KidsProgress restored = new KidsProgress(context);
        check(!restored.recordRound("one", "sub", 5, 5, 3), "Recreated screen counted completion twice");
        check(restored.completedRounds() == 1 && restored.answeredQuestions() == 5 && restored.firstTryCorrect() == 3,
                "Stored totals incorrect");
        check(restored.lastMode().equals("sub") && restored.lastLimit() == 5, "Last options not retained");
        SharedPreferences store = context.getSharedPreferences("kids_progress", 0);
        store.failNextCommit = true;
        check(!restored.recordRound("two", "add", 20, 10, 7), "Failed commit reported success");
        check(restored.completedRounds() == 1, "Failed commit changed totals");
        check(restored.recordRound("two", "add", 20, 10, 7), "Failed commit could not be retried");
        Thread[] writers = new Thread[12];
        for (int i = 0; i < writers.length; i++) {
            writers[i] = new Thread(() -> new KidsProgress(context).recordRound("same-concurrent", "count", 10, 5, 5));
            writers[i].start();
        }
        for (Thread writer : writers) writer.join();
        check(restored.completedRounds() == 3 && restored.answeredQuestions() == 20 && restored.firstTryCorrect() == 15,
                "Concurrent duplicate submission counted twice");
        check(parental.getInt("daily_minutes", 0) == 35 && parental.getLong("daily_spent", 0) == 9999,
                "Practice touched watching-time preferences");
        boolean rejected = false;
        try { restored.recordRound("incomplete", "count", 10, 2, 2); }
        catch (IllegalArgumentException expected) { rejected = true; }
        check(rejected && restored.completedRounds() == 3, "Incomplete round was recorded");
    }

    private static void pictureChallengeInputGuard() {
        PuzzleInputGate gate = new PuzzleInputGate();
        int first = gate.begin(1000);
        check(gate.submit(first, true, 1000) == PuzzleInputGate.IGNORED, "New question accepted a double click");
        check(gate.submit(first, true, 1499) == PuzzleInputGate.IGNORED, "Question cooldown too short");
        check(gate.submit(first, false, 1500) == PuzzleInputGate.RETRY, "Wrong answer could not be retried");
        check(gate.submit(first, true, 1501) == PuzzleInputGate.CORRECT, "Correct retry rejected");
        check(gate.submit(first, true, 1502) == PuzzleInputGate.IGNORED, "Correct answer counted twice");
        int second = gate.begin(1503);
        check(gate.submit(first, true, 3000) == PuzzleInputGate.IGNORED, "Stale answer entered a new question");
        check(gate.submit(second, true, 1550) == PuzzleInputGate.IGNORED, "Double click skipped the next question");
        check(gate.submit(second, true, 2003) == PuzzleInputGate.CORRECT, "Next question not ready after cooldown");
        int third = gate.begin(2500);
        gate.invalidate();
        check(gate.submit(third, true, 9999) == PuzzleInputGate.IGNORED, "Dismissed challenge accepted a stale answer");
    }
}
