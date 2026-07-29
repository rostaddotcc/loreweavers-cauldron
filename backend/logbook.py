"""
Mörkrets Rike — Loggbok / Äventyrsjournal
============================================
LLM extraherar en dag-för-dag tidslinje ur kampanjens transkript.
"""

# Swedish prompt (default)
LOG_PROMPT_SV = """Du är en krönikör som skriver en äventyrsjournal för ett mörkt fantasy-rollspel.

Analysera följande kampanjtranskript och sammanfattningar. Skapa en tidslinje organiserad per dag.

Regler:
- Gruppera händelser per dag (Dag 1, Dag 2, osv.)
- Om dag inte nämns explicit, uppskatta baserat på händelseflödet
- Varje dag: 2-4 korta punkter med de viktigaste händelserna
- Inkludera: platser besökta, NPCs mötta, strider, viktiga beslut, fynd
- Skriv på svenska, kort och koncist (max 15 ord per punkt)
- Lägg till en kort "stämning" per dag (t.ex. "Dimmig och orolig" eller "Blodig men hoppfull")

Svara ENDAST med giltig JSON (ingen markdown):
{
  "title": "Kampanjens namn eller tema",
  "days": [
    {
      "day": 1,
      "title": "Kort titel för dagen",
      "mood": "Stämning i 2-3 ord",
      "events": ["Händelse 1", "Händelse 2", "Händelse 3"],
      "location": "Var dagen utspelade sig",
      "npcs_met": ["NPC-namn"],
      "quests": ["Uppdragsnamn om relevanta"]
    }
  ],
  "summary": "En kort sammanfattning av hela äventyret hittills (max 50 ord)"
}"""

# English prompt
LOG_PROMPT_EN = """You are a chronicler writing an adventure journal for a dark fantasy RPG.

Analyze the following campaign transcript and summaries. Create a timeline organized by day.

Rules:
- Group events by day (Day 1, Day 2, etc.)
- If the day is not mentioned explicitly, estimate based on the flow of events
- Each day: 2-4 short bullet points with the most important events
- Include: locations visited, NPCs met, battles, important decisions, finds
- Write in English, short and concise (max 15 words per point)
- Add a short "mood" per day (e.g. "Foggy and uneasy" or "Bloody but hopeful")

Reply ONLY with valid JSON (no markdown):
{
  "title": "Campaign name or theme",
  "days": [
    {
      "day": 1,
      "title": "Short title for the day",
      "mood": "Mood in 2-3 words",
      "events": ["Event 1", "Event 2", "Event 3"],
      "location": "Where the day took place",
      "npcs_met": ["NPC names"],
      "quests": ["Quest names if relevant"]
    }
  ],
  "summary": "A short summary of the entire adventure so far (max 50 words)"
}"""


def build_log_prompt(transcript_text: str, summaries_text: str, campaign_name: str, language: str = "sv") -> str:
    """Build prompt for logbook generation. Supports 'sv' and 'en'."""
    base = LOG_PROMPT_EN if language == "en" else LOG_PROMPT_SV
    parts = [base]
    if campaign_name:
        label = "Campaign" if language == "en" else "Kampanj"
        parts.append(f"\n{label}: {campaign_name}")
    if summaries_text:
        label = "Summaries" if language == "en" else "Sammanfattningar"
        parts.append(f"\n## {label}\n{summaries_text}")
    if transcript_text:
        # Truncate if extremely long
        if len(transcript_text) > 30000:
            trunc_label = "[... truncated ...]" if language == "en" else "[... trunkerad ...]"
            transcript_text = transcript_text[:30000] + f"\n{trunc_label}"
        label = "Transcript" if language == "en" else "Transkript"
        parts.append(f"\n## {label}\n{transcript_text}")
    return "\n".join(parts)
