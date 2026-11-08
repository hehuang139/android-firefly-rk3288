#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Generate two original, silent preschool video lessons using simple geometry."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')


def frame(title, caption, circles, label, destination):
    image = Image.new('RGB', (1280, 720), '#0a111e')
    draw = ImageDraw.Draw(image)
    for text, y, size, color in [(title, 52, 52, '#edf3fa'),
                                  (caption, 135, 30, '#99adc3'),
                                  (label, 555, 54, '#edf3fa')]:
        draw.text((640, y), text, font=ImageFont.truetype(str(FONT), size),
                  anchor='mt', fill=color)
    width = len(circles) * 180
    for index, color in enumerate(circles):
        left = (1280 - width) // 2 + index * 180 + 20
        draw.ellipse((left, 290, left + 140, 430), fill=color)
    image.save(destination)


def lesson(name, pages):
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        for index, page in enumerate(pages):
            frame(*page, work / f'{index:02}.png')
        output = ROOT / (name + '.mp4')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-framerate', '1/8', '-i', str(work / '%02d.png'),
                        '-c:v', 'libx264', '-profile:v', 'main', '-level:v', '3.1',
                        '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
                        '-r', '25', '-movflags', '+faststart', str(output)], check=True)
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                                              '-show_format', '-of', 'json', str(output)]))
    return {'file': output.name, 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'bytes': output.stat().st_size, 'probe': info}


colors = [('红色', '#ed6363'), ('蓝色', '#56b8f3'), ('黄色', '#ffd65b'),
          ('绿色', '#71dba0'), ('紫色', '#b294ec')]
records = [lesson('colors', [('认识颜色', '看看圆圆是什么颜色，找找身边相同颜色的东西。',
                             [color], name) for name, color in colors]),
           lesson('counting', [('数一数 1–5', '和爸爸妈妈一起，慢慢数数小圆圆。',
                               ['#71dbc8'] * count, str(count)) for count in range(1, 6)])]
(ROOT / 'media.json').write_text(json.dumps({'license': 'CC0-1.0',
    'description': 'Original geometric preschool lessons, silent, 720p25, 40 seconds each.',
    'font': 'Noto Sans CJK (SIL OFL 1.1), rendered into frames; no font distributed',
    'files': records}, ensure_ascii=False, indent=2) + '\n')
print(json.dumps([{'file': x['file'], 'bytes': x['bytes']} for x in records]))
