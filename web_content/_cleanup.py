"""精简 web_content/app.py：删诊断+批量+反馈+设置+LLM modal+health+warmup+main。

从后往前删避免 line 号位移。"""
from pathlib import Path

P = Path("C:/ideon/ideon-portal-main/web_content/app.py")
lines = P.read_text(encoding="utf-8").splitlines(keepends=True)
total = len(lines)
print(f"原始行数: {total}")

# [start, end] 1-indexed inclusive
ranges = [
    (1900, total),   # main 入口 + 末尾
    (1870, 1899),    # warmup + on_event
    (1848, 1850),    # /health
    (1429, 1846),    # settings 全部
    (1308, 1423),    # feedback 全部
    (1302, 1304),    # _parse_xlsx
    (425, 835),      # 02 诊断 + 03 批量
]

def del_range(lines, start, end):
    return [l for i, l in enumerate(lines, 1) if not (start <= i <= end)]

for start, end in ranges:
    if start > total:
        print(f"skip [{start},{end}] 越界")
        continue
    before = len(lines)
    lines = del_range(lines, start, end)
    after = len(lines)
    print(f"del [{start:>4},{end:>4}]  {before:>4}->{after:>4}  (删 {before-after} 行)")

P.write_text("".join(lines), encoding="utf-8")
print(f"\n最终行数: {len(lines)}")