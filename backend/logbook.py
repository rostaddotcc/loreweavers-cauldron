"""
Mörkrets Rike — Loggbok / Äventyrsjournal
============================================
LLM extraherar en dag-för-dag tidslinje ur kampanjens transkript.
"""

LOG_PROMPT = """Du är en krönikör som skriver en äventyrsjournal för ett mörkt fantasy-rollspel.

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


def build_log_prompt(transcript_text: str, summaries_text: str, campaign_name: str) -> str:
    """Bygg prompt för loggboksgenerering."""
    parts = [LOG_PROMPT]
    if campaign_name:
        parts.append(f"\nKampanj: {campaign_name}")
    if summaries_text:
        parts.append(f"\n## Sammanfattningar\n{summaries_text}")
    if transcript_text:
        # Trunkera om extremt långt
        if len(transcript_text) > 30000:
            transcript_text = transcript_text[:30000] + "\n[... trunkerad ...]"
        parts.append(f"\n## Transkript\n{transcript_text}")
    return "\n".join(parts)
