# Test cases

One folder per case. The folder name is the case name.

```
test_cases/
  excel_div_zero/
    1.png            # screenshots, sorted by filename = oldest → newest
    2.png
    question.txt     # required: what the user types
    title.txt        # optional: the window title, e.g. "Budget.xlsx - Excel"
    expect.txt       # optional: what a good answer should mention (for you to compare by eye)
```

Tips:
- Cover several different apps — the coach is meant to work with any software.
- Mix easy questions, vague ones ("why isn't this working?"), and ones the screenshot can't answer.
- Screenshots may show personal info (emails, file names). Don't commit ones you wouldn't want public.

Run from the project root:

```bash
/mnt/c/Users/CHENY1/screencoach-venv/Scripts/python.exe -m scripts.try_prompt
```
