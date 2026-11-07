/* SPDX-License-Identifier: Apache-2.0 */
package org.firefly.tv;

import java.util.Random;

/** Original offline picture questions; no advertising, accounts or network requests. */
final class PuzzleRound {
    final String instruction;
    final String target;
    final String[] answers;
    final int[] colors;
    final int targetColor;
    final int correct;

    PuzzleRound(Random random, int kind, int difficulty) {
        correct = random.nextInt(3);
        colors = new int[] {0xFFE96262, 0xFF56B8F3, 0xFFFFD65B};
        if (kind == 0) {
            instruction = "找出和上面颜色一样的圆圆";
            target = "●";
            answers = new String[] {"●", "●", "●"};
            targetColor = colors[correct];
        } else if (kind == 1) {
            instruction = "找出和上面一样的形状";
            answers = new String[] {"●", "▲", "■"};
            target = answers[correct];
            targetColor = 0xFF71DBC8;
            java.util.Arrays.fill(colors, targetColor);
        } else {
            instruction = "数一数，上面有几个小圆圆？";
            int maximum = difficulty == 0 ? 5 : 3;
            int count = 1 + random.nextInt(maximum);
            target = "● ".repeat(count).trim();
            answers = counts(random, count, maximum);
            targetColor = 0xFF71DBC8;
            java.util.Arrays.fill(colors, targetColor);
        }
    }

    private String[] counts(Random random, int count, int maximum) {
        int other = 1 + random.nextInt(maximum - 1);
        if (other >= count) {
            other++;
        }
        int last = 1;
        while (last == count || last == other) {
            last++;
        }
        String[] result = new String[3];
        result[correct] = Integer.toString(count);
        result[(correct + 1) % 3] = Integer.toString(other);
        result[(correct + 2) % 3] = Integer.toString(last);
        return result;
    }
}
