"""LLM extraction prompts — evidence-first schema instructions (v2 §21).

Instead of asking the LLM to return just values, we require:
    { "field": { "value": "...", "evidence": "...", "confidence": 0.97 } }

This makes hallucination structurally harder.
"""

from __future__ import annotations

SYSTEM_PROMPT = """You are an AI data extraction specialist for ProvenMesh, an intelligence graph system.
Your task is to extract structured data from web page content with EVIDENCE for every field.

CRITICAL RULES:
1. For EVERY extracted field, you MUST provide:
   - "value": The extracted value
   - "evidence": The EXACT text span from the source that supports this value
   - "confidence": A float 0.0-1.0 indicating your confidence

2. If you cannot find evidence for a field in the source text, set:
   - "value": null
   - "evidence": ""
   - "confidence": 0.0

3. NEVER invent or hallucinate information. Only extract what is explicitly stated in the source text.
4. The "evidence" field must be a direct quote or close paraphrase from the source — not your own summary.
5. Output valid JSON matching the requested schema."""


STARTUP_PROMPT = """Extract startup/company information from the following web page content.

Return a JSON object with this structure:
{
  "entityName": {"value": "...", "evidence": "...", "confidence": 0.0},
  "description": {"value": "...", "evidence": "...", "confidence": 0.0},
  "foundedDate": {"value": "YYYY-MM-DD or null", "evidence": "...", "confidence": 0.0},
  "founders": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "headquarters": {"value": "...", "evidence": "...", "confidence": 0.0},
  "industry": {"value": "...", "evidence": "...", "confidence": 0.0},
  "fundingTotal": {"value": "...", "evidence": "...", "confidence": 0.0},
  "lastFundingRound": {"value": "...", "evidence": "...", "confidence": 0.0},
  "employeeCount": {"value": "...", "evidence": "...", "confidence": 0.0},
  "website": {"value": "...", "evidence": "...", "confidence": 0.0},
  "products": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "keyPeople": [{"name": {"value": "...", "evidence": "...", "confidence": 0.0}, "role": {"value": "...", "evidence": "...", "confidence": 0.0}}],
  "relationships": [
    {"source": "...", "target": "...", "type": "FOUNDED_BY|BUILDS_PRODUCT|WORKS_AT", "evidence": "...", "confidence": 0.0}
  ]
}

SOURCE CONTENT:
{content}"""


PRODUCT_PROMPT = """Extract AI product/tool information from the following web page content.

Return a JSON object with this structure:
{
  "entityName": {"value": "...", "evidence": "...", "confidence": 0.0},
  "description": {"value": "...", "evidence": "...", "confidence": 0.0},
  "company": {"value": "...", "evidence": "...", "confidence": 0.0},
  "category": {"value": "...", "evidence": "...", "confidence": 0.0},
  "launchDate": {"value": "YYYY-MM-DD or null", "evidence": "...", "confidence": 0.0},
  "pricing": {"value": "...", "evidence": "...", "confidence": 0.0},
  "pricingModel": {"value": "free|freemium|paid|enterprise", "evidence": "...", "confidence": 0.0},
  "features": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "platforms": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "website": {"value": "...", "evidence": "...", "confidence": 0.0},
  "githubUrl": {"value": "...", "evidence": "...", "confidence": 0.0},
  "relationships": [
    {"source": "...", "target": "...", "type": "BUILDS_PRODUCT", "evidence": "...", "confidence": 0.0}
  ]
}

SOURCE CONTENT:
{content}"""


PAPER_PROMPT = """Extract research paper information from the following content.

Return a JSON object with this structure:
{
  "entityName": {"value": "paper title", "evidence": "...", "confidence": 0.0},
  "title": {"value": "...", "evidence": "...", "confidence": 0.0},
  "abstract": {"value": "...", "evidence": "...", "confidence": 0.0},
  "authors": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "publishedDate": {"value": "YYYY-MM-DD or null", "evidence": "...", "confidence": 0.0},
  "arxivId": {"value": "...", "evidence": "...", "confidence": 0.0},
  "categories": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "githubUrl": {"value": "...", "evidence": "...", "confidence": 0.0},
  "affiliations": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "relationships": [
    {"source": "...", "target": "...", "type": "PUBLISHED_PAPER|CITES", "evidence": "...", "confidence": 0.0}
  ]
}

SOURCE CONTENT:
{content}"""


JOB_PROMPT = """Extract job listing information from the following web page content.

Return a JSON object with this structure:
{
  "entityName": {"value": "job title at company", "evidence": "...", "confidence": 0.0},
  "title": {"value": "...", "evidence": "...", "confidence": 0.0},
  "company": {"value": "...", "evidence": "...", "confidence": 0.0},
  "location": {"value": "...", "evidence": "...", "confidence": 0.0},
  "remotePolicy": {"value": "remote|hybrid|onsite", "evidence": "...", "confidence": 0.0},
  "employmentType": {"value": "full-time|part-time|contract", "evidence": "...", "confidence": 0.0},
  "salaryMin": {"value": "...", "evidence": "...", "confidence": 0.0},
  "salaryMax": {"value": "...", "evidence": "...", "confidence": 0.0},
  "skills": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "postedDate": {"value": "YYYY-MM-DD or null", "evidence": "...", "confidence": 0.0},
  "relationships": [
    {"source": "...", "target": "...", "type": "WORKS_AT", "evidence": "...", "confidence": 0.0}
  ]
}

SOURCE CONTENT:
{content}"""


NEWS_PROMPT = """Extract news article information from the following web page content.

Return a JSON object with this structure:
{
  "title": {"value": "...", "evidence": "...", "confidence": 0.0},
  "summary": {"value": "2-3 sentence summary", "evidence": "...", "confidence": 0.0},
  "publishedDate": {"value": "YYYY-MM-DD or null", "evidence": "...", "confidence": 0.0},
  "author": {"value": "...", "evidence": "...", "confidence": 0.0},
  "publisher": {"value": "...", "evidence": "...", "confidence": 0.0},
  "mentionedEntities": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "keyTopics": [{"value": "...", "evidence": "...", "confidence": 0.0}],
  "relationships": [
    {"source": "...", "target": "...", "type": "FOUNDED_BY|BUILDS_PRODUCT|CITES", "evidence": "...", "confidence": 0.0}
  ]
}

SOURCE CONTENT:
{content}"""

# Registry for prompt lookup by record type
EXTRACTION_PROMPTS: dict[str, str] = {
    "STARTUP": STARTUP_PROMPT,
    "PRODUCT": PRODUCT_PROMPT,
    "PAPER": PAPER_PROMPT,
    "JOB": JOB_PROMPT,
    "NEWS_SIGNAL": NEWS_PROMPT,
}
