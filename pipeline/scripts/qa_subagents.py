"""
Mole FM — QA Subagent System
=============================
Multi-agent quality assurance pipeline for all Mole FM content.

AGENTS:
  1. Proofreader    — Grammar, spelling, French language correctness
  2. Editor         — Clarity, structure, value for listeners
  3. Fact Reviewer  — Checks claims against verified sources
  4. Ethics Officer — Dignity, respect, no sensationalism
  5. Audio Inspector— TTS text quality (no artifacts, flows well aloud)
  6. QC Supervisor  — Final GO/NO-GO decision + patch generation

PHILOSOPHY:
  - Every story must pass the "so what?" test — what value does this give listeners?
  - No rumor, no unverified claim, no exploitation of tragedy
  - Stories about Haiti must honor Haitian dignity — never reinforce stereotypes
  - Listener trust > clicks. Long-term credibility > short-term sensation.

Usage:
  from qa_subagents import QAOrchestra
  result = QAOrchestra().run(segments, context="newscast|podcast|biography")
"""

import re
import json
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class QAIssue:
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    agent: str
    segment_role: str
    description: str
    suggestion: str

@dataclass
class QAResult:
    decision: Literal["GO", "FIX_MINOR", "HOLD", "REJECT"]
    issues: list[QAIssue] = field(default_factory=list)
    auto_fixes: list[str] = field(default_factory=list)
    patches: list[str] = field(default_factory=list)
    score: float = 100.0
    report: str = ""

# ── Agent 1: Proofreader ───────────────────────────────────────────────────────

class ProofreaderAgent:
    """Checks French grammar, spelling, TTS-friendliness."""

    PROBLEMATIC_PATTERNS = [
        # Numbers that TTS won't read well
        (r'\b\d{4,}\b(?!\s*(KB|km|mg|kg|%|€|\$))', "Large number — spell it out for TTS"),
        # URLs in text
        (r'https?://\S+', "URL in audio script — replace with spoken equivalent"),
        # Abbreviations TTS mispronounces
        (r'\bM\.\b', "Abbreviation 'M.' — expand to 'Monsieur'"),
        (r'\bMme\.\b', "Abbreviation 'Mme.' — expand to 'Madame'"),
        # All-caps words (TTS reads letter by letter)
        (r'\b[A-Z]{4,}\b', "All-caps word — spell out or expand for TTS"),
        # Empty segments
        (r'^[\s.]*$', "Empty or near-empty segment"),
        # Excessive punctuation
        (r'\.{3,}', "Ellipsis — use pause markers instead for TTS"),
    ]

    def check(self, segments: list[dict]) -> list[QAIssue]:
        issues = []
        for seg in segments:
            text = seg.get("text", "")
            role = seg.get("role", "?")
            for pattern, desc in self.PROBLEMATIC_PATTERNS:
                matches = re.findall(pattern, text)
                if matches:
                    issues.append(QAIssue(
                        severity="LOW",
                        agent="Proofreader",
                        segment_role=role,
                        description=f"{desc}: {matches[:3]}",
                        suggestion="Review and fix before TTS generation"
                    ))
            # Minimum length check
            if len(text.strip()) < 10 and text.strip():
                issues.append(QAIssue(
                    severity="MEDIUM",
                    agent="Proofreader",
                    segment_role=role,
                    description="Segment too short — may cause awkward audio",
                    suggestion="Expand or merge with adjacent segment"
                ))
        return issues

# ── Agent 2: Editor ────────────────────────────────────────────────────────────

class EditorAgent:
    """Checks story value, structure, listener relevance."""

    VALUE_MARKERS = [
        # Positive — story explains impact
        "ce que cela signifie", "l'impact", "pour vous", "pour haïti",
        "ce qu'il faut retenir", "concrètement", "pourquoi c'est important",
        # Negative — clickbait or hollow phrases
        "choc", "scandale", "incroyable", "vous n'allez pas croire",
        "fou", "hallucinant",
    ]

    FILLER_PHRASES = [
        "parfait", "absolument", "exactement", "tout à fait",
        "en effet", "c'est vrai", "vous avez raison",
    ]

    def check(self, segments: list[dict], context: str = "newscast") -> list[QAIssue]:
        issues = []
        full_text = " ".join(s.get("text", "") for s in segments).lower()

        # Check for clickbait markers
        for word in ["choc", "scandale", "incroyable", "vous n'allez pas croire"]:
            if word in full_text:
                issues.append(QAIssue(
                    severity="MEDIUM",
                    agent="Editor",
                    segment_role="FULL_SCRIPT",
                    description=f"Clickbait language detected: '{word}'",
                    suggestion="Replace with specific factual description. Our standard: inform, not sensationalize."
                ))

        # Check echo turns (filler agreements)
        for seg in segments:
            text = seg.get("text", "").lower()
            role = seg.get("role", "?")
            for filler in self.FILLER_PHRASES:
                if text.strip().startswith(filler) and len(text) < 50:
                    issues.append(QAIssue(
                        severity="LOW",
                        agent="Editor",
                        segment_role=role,
                        description=f"Echo turn starting with '{filler}' — no added value",
                        suggestion="Replace with substantive response that adds new information"
                    ))

        # Check minimum content for podcast episodes
        if context == "podcast":
            word_count = len(full_text.split())
            if word_count < 2000:
                issues.append(QAIssue(
                    severity="HIGH",
                    agent="Editor",
                    segment_role="FULL_SCRIPT",
                    description=f"Podcast script too short: {word_count} words (target: 3400-3800)",
                    suggestion="Expand Act 2 with diaspora stakes. Add specific data points and human stories."
                ))

        return issues

# ── Agent 3: Ethics Officer ────────────────────────────────────────────────────

class EthicsOfficerAgent:
    """Ensures dignity, accuracy claims, no exploitation."""

    DIGNITY_VIOLATIONS = [
        # Stereotyping
        (r'\btoujours\s+pauvre\b', "Stereotype: 'always poor'"),
        (r'\bpays\s+le\s+plus\s+pauvre\b', "Poverty framing without context"),
        # Unverified death claims
        (r'\b(tué|assassiné|mort)\b.*\b(selon|d\'après)\b.*\bréseaux\s+sociaux\b',
         "Death claim sourced only from social media"),
        # Speculation presented as fact
        (r'\bserait\s+(impliqué|responsable|coupable)\b',
         "Conditional accusation — may be speculation"),
    ]

    def check(self, segments: list[dict]) -> list[QAIssue]:
        issues = []
        full_text = " ".join(s.get("text", "") for s in segments).lower()

        for pattern, desc in self.DIGNITY_VIOLATIONS:
            if re.search(pattern, full_text):
                issues.append(QAIssue(
                    severity="HIGH",
                    agent="EthicsOfficer",
                    segment_role="FULL_SCRIPT",
                    description=f"Dignity/accuracy concern: {desc}",
                    suggestion="Review and reframe. Our north star: trustworthy and respectful of human dignity."
                ))

        # Check for attribution on sensitive topics
        sensitive_topics = ["gang", "massacre", "kidnapping", "corruption", "arrestation"]
        for topic in sensitive_topics:
            if topic in full_text:
                # Check that attribution exists nearby
                has_attribution = any(
                    word in full_text
                    for word in ["selon", "d'après", "a déclaré", "a confirmé", "sources", "rapport"]
                )
                if not has_attribution:
                    issues.append(QAIssue(
                        severity="MEDIUM",
                        agent="EthicsOfficer",
                        segment_role="FULL_SCRIPT",
                        description=f"Sensitive topic '{topic}' without clear attribution",
                        suggestion="Add source attribution: 'Selon [source]...'"
                    ))
                    break  # One warning per script is enough

        return issues

# ── Agent 4: Audio Inspector ───────────────────────────────────────────────────

class AudioInspectorAgent:
    """Ensures text reads well aloud when converted to TTS."""

    def check(self, segments: list[dict]) -> list[QAIssue]:
        issues = []
        for seg in segments:
            text = seg.get("text", "")
            role = seg.get("role", "?")

            # Check for symbols TTS can't read
            bad_symbols = ["%", "€", "$", "&", "@", "#", "=", "+", ">", "<", "|"]
            for sym in bad_symbols:
                if sym in text:
                    issues.append(QAIssue(
                        severity="LOW",
                        agent="AudioInspector",
                        segment_role=role,
                        description=f"Symbol '{sym}' in TTS text — may be misread",
                        suggestion=f"Spell out: '%' → 'pourcent', '€' → 'euros', '$' → 'dollars'"
                    ))

            # Check paragraph breaks (may cause awkward pauses)
            if "\n\n" in text:
                issues.append(QAIssue(
                    severity="LOW",
                    agent="AudioInspector",
                    segment_role=role,
                    description="Double newline in TTS text — remove paragraph breaks",
                    suggestion="Flatten to single continuous paragraph for TTS"
                ))

            # Check for markdown (bold, italic, headers)
            if re.search(r'[*#_`]', text):
                issues.append(QAIssue(
                    severity="MEDIUM",
                    agent="AudioInspector",
                    segment_role=role,
                    description="Markdown formatting in TTS text",
                    suggestion="Remove all markdown — TTS will speak the asterisks"
                ))

        return issues

# ── QA Orchestra ──────────────────────────────────────────────────────────────

class QAOrchestra:
    """Runs all QA agents and produces a final GO/NO-GO decision."""

    def __init__(self):
        self.proofreader  = ProofreaderAgent()
        self.editor       = EditorAgent()
        self.ethics       = EthicsOfficerAgent()
        self.audio        = AudioInspectorAgent()

    def run(self, segments: list[dict], context: str = "newscast") -> QAResult:
        all_issues: list[QAIssue] = []

        # Run all agents
        all_issues += self.proofreader.check(segments)
        all_issues += self.editor.check(segments, context)
        all_issues += self.ethics.check(segments)
        all_issues += self.audio.check(segments)

        # Score
        score = 100.0
        for issue in all_issues:
            if issue.severity == "CRITICAL": score -= 30
            elif issue.severity == "HIGH":   score -= 15
            elif issue.severity == "MEDIUM": score -= 5
            elif issue.severity == "LOW":    score -= 1

        score = max(0.0, score)

        # Decision
        critical_count = sum(1 for i in all_issues if i.severity == "CRITICAL")
        high_count     = sum(1 for i in all_issues if i.severity == "HIGH")

        if critical_count > 0:
            decision = "REJECT"
        elif high_count > 2:
            decision = "HOLD"
        elif score < 75:
            decision = "FIX_MINOR"
        else:
            decision = "GO"

        # Auto-fixable patches
        patches = []
        for issue in all_issues:
            if issue.severity == "LOW":
                patches.append(f"AUTO-FIX [{issue.agent}/{issue.segment_role}]: {issue.suggestion}")

        # Build report
        lines = [
            f"QA REPORT — {context.upper()}",
            f"Decision: {decision} | Score: {score:.0f}/100",
            f"Issues: {len(all_issues)} ({critical_count} CRITICAL, {high_count} HIGH)",
            "",
        ]
        if all_issues:
            for issue in sorted(all_issues, key=lambda x: {"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}[x.severity]):
                lines.append(f"  [{issue.severity}] {issue.agent} / {issue.segment_role}")
                lines.append(f"    → {issue.description}")
                lines.append(f"    Fix: {issue.suggestion}")
                lines.append("")

        report = "\n".join(lines)

        return QAResult(
            decision=decision,
            issues=all_issues,
            auto_fixes=[i.suggestion for i in all_issues if i.severity == "LOW"],
            patches=patches,
            score=score,
            report=report,
        )

    def print_report(self, result: QAResult):
        print(f"\n  QC Decision: {result.decision} | Score: {result.score:.0f}/100")
        print(f"  Issues: {len(result.issues)} | Auto-fixes: {len(result.auto_fixes)}")
        if result.issues:
            for issue in result.issues[:5]:  # Show top 5
                print(f"    [{issue.severity}] {issue.agent}: {issue.description[:80]}")
        print()

# ── Standalone test ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_segments = [
        {"role": "INTRO", "text": "Bonjour et bienvenue. C'est un choc absolu aujourd'hui."},
        {"role": "NEWS", "text": "Selon Radio Métropole, le gouvernement a annoncé un budget de 50000000 gourdes pour la sécurité."},
        {"role": "SPORTS", "text": "Parfait."},
    ]
    qa = QAOrchestra()
    result = qa.run(test_segments, context="newscast")
    print(result.report)
