# Meeting Assistant
You upload a recording of a meeting. The app gives you back the raw transcript, a cleaned-up
transcript, the minutes, the decisions and the action items.

## Setup

You need Python 3.10 or above.

```
pip install -r requirements.txt
```

## Running it

```
python -m streamlit run app.py
```

This opens the app in your browser. Paste your Groq API key in the sidebar (you can get a free one
at https://console.groq.com), upload an mp3, wav or m4a file (up to 25 MB) and press "Process meeting".

There are two optional boxes, the meeting topic and extra context. Put things like names, acronyms
and technical terms there, it helps with the spelling of difficult words.

## Models used

| Stage | Model | What it does |
|---|---|---|
| 1. Speech to text | whisper-large-v3 | turns the audio into the raw transcript |
| 2. Refinement | qwen/qwen3.8-27b | fixes wrongly heard technical terms and acronyms, nothing else |
| 3. Documentation | openai/gpt-oss-120b | makes the summary, minutes, decisions and action items from the refined transcript |

All three run through the Groq API.

## How it works

1. Whisper transcribes the audio. The topic and extra context are passed to it as a small prompt,
   so it has a better chance of hearing the terms correctly.
2. The raw transcript goes to Qwen along with the topic and extra context. It only corrects words
   that were clearly misheard and keeps names, numbers and negations as they are.
3. The refined transcript goes to GPT-OSS, which returns JSON. The app then fills in "unspecified"
   for any owner or deadline that was not said in the meeting.
4. The Markdown minutes are made from that same JSON, so the readable file and the JSON file
   always have the same decisions and tasks.

## What you get in the app

- raw and refined transcripts next to each other
- a diff (done with Python's difflib) showing every word the refinement changed
- the minutes, decisions and action items
- downloads for the raw transcript, refined transcript, minutes (.md), full record (.json) and
  decisions + tasks (.json)

## Errors

If the file has the wrong type, is empty, is bigger than 25 MB, has no speech in it, or the API
call fails, the app shows a message instead of crashing.

## Prompts

Both prompts are at the top of `app.py` (`REFINE_PROMPT` and `DOC_PROMPT`). The model names are
right above them if you want to change them.

## Samples

The `samples/` folder has the recording used and the outputs the app generated for it.
