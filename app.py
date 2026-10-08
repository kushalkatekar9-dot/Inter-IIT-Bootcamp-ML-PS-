import os
import json
import html
import difflib
import streamlit as st
from groq import Groq

STT_MODEL = "whisper-large-v3"
REFINE_MODEL = "qwen/qwen3.8-27b"
DOC_MODEL = "openai/gpt-oss-120b"

ALLOWED = ["mp3", "wav", "m4a"]
MAX_MB = 25  


REFINE_PROMPT = """You fix speech-to-text errors in a meeting transcript.
Rules:
- Only correct words that are clearly misheard, mainly technical terms, acronyms and product names.
- Use the meeting topic, the extra context/glossary and the rest of the transcript as context.
- If a glossary term sounds like a misheard word, use the glossary spelling.
- Do NOT summarize, shorten, reorder or add anything.
- Keep names, numbers, dates, negations (not, never, can't) and commitments exactly as they are.
- If you are not sure, leave the word as it is.
Return only the corrected transcript, nothing else."""

DOC_PROMPT = """You write meeting records from a transcript.
Return ONLY a JSON object with these keys:
{
  "summary": "2-4 sentence summary",
  "minutes": [ {"topic": "...", "points": ["...", "..."]} ],
  "decisions": ["..."],
  "action_items": [ {"task": "...", "owner": "...", "deadline": "..."} ]
}
Rules:
- Use only what is said in the transcript. Do not invent anything.
- A decision is something the group clearly agreed on. A suggestion or proposal that was not agreed is NOT a decision.
- An action item is a task someone was clearly asked or agreed to do.
- If the owner or deadline was not said, write "unspecified".
- If there are no decisions or no action items, use an empty list."""


def get_client():
    key = os.environ.get("GROQ_API_KEY") or st.session_state.get("key", "")
    if not key:
        return None
    return Groq(api_key=key)


def check_file(f):
    # returns an error message or None
    ext = f.name.split(".")[-1].lower()
    if ext not in ALLOWED:
        return "Unsupported file type. Please upload mp3, wav or m4a."
    size = len(f.getvalue())
    if size == 0:
        return "The file is empty."
    if size > MAX_MB * 1024 * 1024:
        return "File is bigger than 25 MB. Please upload a smaller or compressed file."
    return None


def transcribe(client, f, hint):
    result = client.audio.transcriptions.create(
        file=(f.name, f.getvalue()),
        model=STT_MODEL,
        language="en",
        prompt=hint[:800],
        response_format="json",
        temperature=0,
    )
    return result.text.strip()


def split_text(text, size=6000):
    # split on spaces so we never cut a word in half
    chunks = []
    current = ""
    for word in text.split(" "):
        if len(current) + len(word) > size:
            chunks.append(current)
            current = ""
        current += word + " "
    if current.strip():
        chunks.append(current)
    return chunks


def refine(client, raw, topic, glossary):
    parts = []
    for chunk in split_text(raw):
        msg = "Meeting topic: " + (topic or "not given") + "\n"
        msg += "Extra context / glossary: " + (glossary or "none") + "\n\n"
        msg += "Transcript:\n" + chunk
        res = client.chat.completions.create(
            model=REFINE_MODEL,
            temperature=0,
            messages=[
                {"role": "system", "content": REFINE_PROMPT},
                {"role": "user", "content": msg},
            ],
        )
        parts.append(res.choices[0].message.content.strip())
    return "\n".join(parts)


def make_record(client, refined):
    res = client.chat.completions.create(
        model=DOC_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": DOC_PROMPT},
            {"role": "user", "content": "Transcript:\n" + refined},
        ],
    )
    text = res.choices[0].message.content
    #in case the model adds extra text around the json
    text = text[text.find("{"): text.rfind("}") + 1]
    data = json.loads(text)

    # make sure every field exists and missing things say "unspecified"
    record = {
        "summary": data.get("summary", ""),
        "minutes": data.get("minutes", []),
        "decisions": data.get("decisions", []),
        "action_items": [],
    }
    for item in data.get("action_items", []):
        owner = str(item.get("owner") or "").strip()
        deadline = str(item.get("deadline") or "").strip()
        record["action_items"].append({
            "task": item.get("task", ""),
            "owner": owner if owner else "unspecified",
            "deadline": deadline if deadline else "unspecified",
        })
    return record


def to_markdown(record):
    md = "# Meeting Minutes\n\n"
    md += "## Summary\n" + record["summary"] + "\n\n"
    md += "## Minutes\n"
    for m in record["minutes"]:
        md += "### " + m.get("topic", "") + "\n"
        for p in m.get("points", []):
            md += "- " + p + "\n"
        md += "\n"
    md += "## Key Decisions\n"
    if record["decisions"]:
        for d in record["decisions"]:
            md += "- " + d + "\n"
    else:
        md += "No decisions were reached.\n"
    md += "\n## Action Items\n"
    if record["action_items"]:
        for a in record["action_items"]:
            md += "- " + a["task"] + " (Owner: " + a["owner"] + ", Deadline: " + a["deadline"] + ")\n"
    else:
        md += "No action items were assigned.\n"
    return md


def make_diff(raw, refined):
    # compares the two transcripts word by word
    a = raw.split()
    b = refined.split()
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    out = ""
    changes = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out += html.escape(" ".join(a[i1:i2])) + " "
        else:
            changes += 1
            if i2 > i1:
                old = html.escape(" ".join(a[i1:i2]))
                out += '<del style="background:#ffd6d6;color:#000">' + old + "</del> "
            if j2 > j1:
                new = html.escape(" ".join(b[j1:j2]))
                out += '<ins style="background:#d4f5d4;color:#000;text-decoration:none">' + new + "</ins> "
    return out, changes


# ---------------- page ----------------
st.set_page_config(page_title="Meeting Assistant", layout="wide")
st.title("AI Meeting Assistant")

with st.sidebar:
    st.header("Settings")
    if not os.environ.get("GROQ_API_KEY"):
        st.text_input("Groq API key", type="password", key="key")
    st.write("Speech-to-text: " + STT_MODEL)
    st.write("Refinement: " + REFINE_MODEL)
    st.write("Documentation: " + DOC_MODEL)

uploaded = st.file_uploader("Upload meeting recording", type=ALLOWED)
topic = st.text_input("Meeting topic (optional, helps fix technical terms)")
glossary = st.text_area("Extra context (optional): names, acronyms, product or technical terms",
                        placeholder="e.g. Kubernetes, CI/CD, Priya Sharma, Q3 roadmap", height=80)

if st.button("Process meeting"):
    client = get_client()
    if client is None:
        st.error("Please enter your Groq API key in the sidebar.")
    elif uploaded is None:
        st.error("Please upload an audio file first.")
    else:
        error = check_file(uploaded)
        if error:
            st.error(error)
        else:
            try:
                with st.status("Processing...", expanded=True) as status:
                    st.write("Step 1/3: transcribing audio")
                    hint = topic + ". " + glossary if (topic or glossary) else ""
                    raw = transcribe(client, uploaded, hint)
                    if not raw:
                        raise ValueError("No speech was found in this recording.")

                    st.write("Step 2/3: refining transcript")
                    refined = refine(client, raw, topic, glossary)

                    st.write("Step 3/3: writing minutes, decisions and tasks")
                    record = make_record(client, refined)
                    status.update(label="Done", state="complete")

                st.session_state["result"] = {"raw": raw, "refined": refined, "record": record}
            except Exception as e:
                st.error("Something went wrong: " + str(e))

# show results (kept in session_state so download buttons don't clear them)
if "result" in st.session_state:
    r = st.session_state["result"]
    record = r["record"]

    st.subheader("Transcripts")
    c1, c2 = st.columns(2)
    c1.markdown("**Raw transcript**")
    c1.text_area("raw", r["raw"], height=300, label_visibility="collapsed")
    c2.markdown("**Refined transcript**")
    c2.text_area("refined", r["refined"], height=300, label_visibility="collapsed")

    diff_html, n = make_diff(r["raw"], r["refined"])
    with st.expander("What did refinement change? (" + str(n) + " edits)"):
        st.markdown("Red = removed from raw, green = added in refined")
        st.markdown(diff_html, unsafe_allow_html=True)

    st.subheader("Meeting record")
    st.markdown(to_markdown(record))

    st.subheader("Downloads")
    d1, d2, d3, d4, d5 = st.columns(5)
    d1.download_button("Raw transcript", r["raw"], "raw_transcript.txt")
    d2.download_button("Refined transcript", r["refined"], "refined_transcript.txt")
    d3.download_button("Minutes (.md)", to_markdown(record), "meeting_minutes.md")
    d4.download_button("Record (.json)", json.dumps(record, indent=2), "meeting_record.json")
    d5.download_button("Decisions + tasks (.json)",
                       json.dumps({"decisions": record["decisions"], "action_items": record["action_items"]}, indent=2),
                       "decisions_and_tasks.json")
