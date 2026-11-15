"""Small fail-closed numeric and citation guard for opt-in portfolio explanations.

This guard is NOT semantic verification. A supported number can still be used
misleadingly, and a cited issuer excerpt can omit important context. Human
evaluation and independent financial review remain required.
"""
from __future__ import annotations
import json
import re

_NUM = re.compile(r'(?<![\w])[-+]?\$?\d[\d,]*(?:\.\d+)?%?')
_CITE = re.compile(r'\[([a-z][a-z0-9_]*|sec:[A-Za-z0-9:._-]+)\]')


def _numbers(text: str) -> list[float]:
    values=[]
    for match in _NUM.finditer(text):
        token=match.group(0).replace(',','').replace('$','').replace('%','')
        try:values.append(float(token))
        except ValueError:pass
    return values


def validate_answer(answer: str, *, called: list[str], payloads: list[dict],
                    filing: dict | None = None) -> dict:
    """Require numeric provenance and prevent made-up citation labels/URLs.

    For backwards compatibility, prose without numeric claims can rely on
    server-provided source cards even if the LLM omits inline markers.
    """
    if not answer or len(answer)>2500:
        raise RuntimeError('AI explanation was empty or unbounded')
    cited=set(_CITE.findall(answer))
    allowed=set(called)
    if filing:
        allowed.add(str(filing.get('source_id') or ''))
    if any(c not in allowed for c in cited):
        raise RuntimeError('AI explanation cited unavailable source material')
    if re.search(r'guaranteed (?:profit|return)|(?:i|we) (?:recommend|advise) (?:you )?(?:buy|sell)',
                 answer,re.I):
        raise RuntimeError('AI explanation included an unsupported trade recommendation')
    # An output URL is only legitimate if it exactly matches the server-fetched
    # SEC original. URLs and malicious links cannot be authored by the model.
    allowed_url = str(filing.get('url') or '') if filing else ''
    for match in re.finditer(r'https?://[^\s<>\]\)]+',answer,re.I):
        url=match.group(0).rstrip('.,;')
        if not allowed_url or url != allowed_url:
            raise RuntimeError('AI explanation invented a source URL')
    evidence_text=json.dumps(payloads,ensure_ascii=True,allow_nan=False)
    facts=_numbers(evidence_text)
    stated=_numbers(answer)
    for value in stated:
        if not any(abs(value-v)<=max(.0051,abs(v)*.000001)
                   or round(value,2)==round(v,2) for v in facts):
            raise RuntimeError('AI explanation included a numeric claim absent from tool evidence')
    if stated and not cited:
        raise RuntimeError('Numeric AI claims require an explicit called-tool citation')
    return {
        'screened': True,
        'numeric_mentions':len(stated),
        'cited_source_ids': sorted(cited),
        'scope':'syntactic evidence screening, not independent truth verification',
    }
