"""Test fixtures — sample HTML, LLM responses, and entity data for testing.

Provides consistent test data across unit, integration, and e2e tests.
"""

from __future__ import annotations

# ─── Sample HTML Pages ───────────────────────────────────────────

STARTUP_HTML = """
<html>
<head><title>Anthropic - AI Safety Research</title></head>
<body>
<article>
<h1>Anthropic</h1>
<p>Anthropic is an AI safety company founded in 2021 by Dario Amodei and Daniela Amodei.</p>
<p>The company is headquartered in San Francisco, California.</p>
<p>Anthropic has raised $7.3 billion in funding from investors including Google and Spark Capital.</p>
<p>Their flagship product is Claude, a helpful, harmless, and honest AI assistant.</p>
<p>Website: <a href="https://www.anthropic.com">anthropic.com</a></p>
</article>
</body>
</html>
"""

PRODUCT_HTML = """
<html>
<head><title>ChatGPT - AI Assistant by OpenAI</title></head>
<body>
<h1>ChatGPT</h1>
<p>ChatGPT is an AI chatbot developed by OpenAI, launched in November 2022.</p>
<p>It uses large language models including GPT-4o.</p>
<p>Pricing: Free tier available, Plus at $20/month.</p>
<p>Available on: Web, iOS, Android, Desktop</p>
</body>
</html>
"""

PAPER_HTML = """
<html>
<head><title>Attention Is All You Need</title></head>
<body>
<h1>Attention Is All You Need</h1>
<p>Authors: Ashish Vaswani, Noam Shazeer, Niki Parmar, et al.</p>
<p>Published: 2017-06-12</p>
<p>Abstract: The dominant sequence transduction models are based on complex recurrent
or convolutional neural networks. We propose a new architecture, the Transformer,
based solely on attention mechanisms.</p>
<p>ArXiv: 1706.03762</p>
<p>Citations: 100,000+</p>
</body>
</html>
"""

JOB_HTML = """
<html>
<head><title>Senior ML Engineer at Anthropic</title></head>
<body>
<h1>Senior Machine Learning Engineer</h1>
<p>Company: Anthropic</p>
<p>Location: San Francisco, CA (Remote OK)</p>
<p>Salary: $200,000 - $350,000/year</p>
<p>Skills: Python, PyTorch, Transformers, RLHF</p>
<p>Posted: 2026-08-01</p>
</body>
</html>
"""


# ─── Sample LLM Extraction Responses ────────────────────────────

STARTUP_EXTRACTION = {
    "entityName": {"value": "Anthropic", "evidence": "Anthropic is an AI safety company", "confidence": 0.99},
    "description": {"value": "AI safety company", "evidence": "Anthropic is an AI safety company", "confidence": 0.95},
    "foundedDate": {"value": "2021", "evidence": "founded in 2021", "confidence": 0.93},
    "founders": [
        {"value": "Dario Amodei", "evidence": "founded in 2021 by Dario Amodei", "confidence": 0.95},
        {"value": "Daniela Amodei", "evidence": "Dario Amodei and Daniela Amodei", "confidence": 0.94},
    ],
    "headquarters": {"value": "San Francisco, California", "evidence": "headquartered in San Francisco, California", "confidence": 0.96},
    "fundingTotal": {"value": "$7.3B", "evidence": "raised $7.3 billion in funding", "confidence": 0.98},
    "website": {"value": "https://www.anthropic.com", "evidence": "anthropic.com", "confidence": 0.97},
}

PRODUCT_EXTRACTION = {
    "entityName": {"value": "ChatGPT", "evidence": "ChatGPT is an AI chatbot", "confidence": 0.99},
    "company": {"value": "OpenAI", "evidence": "developed by OpenAI", "confidence": 0.98},
    "launchDate": {"value": "November 2022", "evidence": "launched in November 2022", "confidence": 0.92},
    "pricing": {"value": "Free tier available, Plus at $20/month", "evidence": "Free tier available, Plus at $20/month", "confidence": 0.96},
}


# ─── Seed Entities ───────────────────────────────────────────────

SEED_ENTITIES = [
    {"canonical_id": "startup_openai", "name": "OpenAI", "aliases": ["Open AI", "OpenAI Inc"]},
    {"canonical_id": "startup_anthropic", "name": "Anthropic", "aliases": ["Anthropic AI"]},
    {"canonical_id": "startup_deepmind", "name": "DeepMind", "aliases": ["Google DeepMind"]},
    {"canonical_id": "product_chatgpt", "name": "ChatGPT", "aliases": ["Chat GPT"]},
    {"canonical_id": "product_claude", "name": "Claude", "aliases": ["Claude AI"]},
]
