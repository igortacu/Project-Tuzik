"""Real Q&A pairs used to measure retrieval quality. Filled in by hand."""

from dataclasses import dataclass


@dataclass
class EvalQuestion:
    question: str
    # Expected source note path(s), relative to the vault root (matches
    # index_pipeline's source_file metadata). A list means the answer
    # genuinely requires pulling chunks from multiple notes -- hit requires
    # ALL of them to be retrieved, not just one. "NONE" is the sentinel for
    # negative controls (see run_eval._NEGATIVE_CONTROL). "" means not yet
    # mapped to a note (see the flagged questions below).
    expected_source: str | list[str]


QUESTIONS: list[EvalQuestion] = [
    # --- Career / AI-ML transition ---
    EvalQuestion("What did I decide about targeting Sigmoid vs staying in QA?", "TuzikVault/career_sigmoid.md"),
    # NOTE: reworded from "What was my answer to a specific Sigmoid technical
    # interview question?" -- career_sigmoid.md says no technical interview
    # was actually done (accepted via hackathon placement instead), so the
    # original question's premise was false. This version is also a genuine
    # multi-note test: a full answer needs interview-prep content from
    # career_sigmoid.md plus the two topics practiced (ATF ThreadLocal, RAG
    # fundamentals), which live in two other notes.
    EvalQuestion(
        "What did I practice for interview prep, and how did I actually get the Sigmoid offer?",
        ["TuzikVault/career_sigmoid.md", "TuzikVault/atf-arhitecture.md", "TuzikVault/rag_pipeline_design.md"],
    ),
    EvalQuestion("What's the architecture of my naive RAG pipeline built from scratch?", "TuzikVault/rag_pipeline_design.md"),
    # NOTE: no note covers a Codwer internship resume edit -- write one or drop this question.
    EvalQuestion("What edits did I make to my resume regarding the Codwer internship?", ""),
    EvalQuestion("What's my reasoning for choosing AI engineering over ML research?", "TuzikVault/career_sigmoid.md"),
    EvalQuestion("Why did I conclude mid-level roles are the right entry point, not junior?", "TuzikVault/career_sigmoid.md"),

    # --- Endava / ATF technical ---
    EvalQuestion("How does the OTP Gateway locking mechanism work in my ATF?", "TuzikVault/atf-arhitecture.md"),
    EvalQuestion("What's the ThreadLocal browser management pattern I used?", "TuzikVault/atf-arhitecture.md"),
    EvalQuestion("What HikariCP/JDBC connection pool settings did I choose and why?", "TuzikVault/atf-arhitecture.md"),
    EvalQuestion("What did I present in the Confirmation of Payee demo?", "TuzikVault/atf-arhitecture.md"),

    # --- Hackathons (verified) ---
    EvalQuestion("Who was on my team for the XMAS FAF Hackathon 2025 Architecture Challenge?", "TuzikVault/xmas_faf_hackathon.md"),
    EvalQuestion("What was the Architecture Challenge about at XMAS FAF Hackathon 2025?", "TuzikVault/xmas_faf_hackathon.md"),
    EvalQuestion("What did my team build or propose for the Architecture Challenge?", "TuzikVault/xmas_faf_hackathon.md"),

    # --- Hackathons (memory-only -- no note was added for these, confirmed
    # absent from the 11 new notes. Write one up or drop the question.) ---
    EvalQuestion("What did I work on for the Democracy Hackathon in Strasbourg?", ""),
    EvalQuestion("What did I explore for the CTF AI SaaS Security challenge?", ""),
    EvalQuestion("What multi-agent frameworks did I consider for hackathon use?", ""),

    # --- LucAuto: rim classifier (built) ---
    EvalQuestion("What's the JSON schema classify_rims.py returns?", "TuzikVault/lucauto_rim_classifier.md"),
    EvalQuestion("What retry/backoff strategy did I implement in the rim classifier?", "TuzikVault/lucauto_rim_classifier.md"),
    EvalQuestion("Why did I set temperature=0 in the rim damage classifier?", "TuzikVault/lucauto_rim_classifier.md"),

    # --- LucAuto: in-progress design work ---
    EvalQuestion("What's the current architecture I designed for the WhatsApp triage assistant, and what's still open?", "TuzikVault/lucauto_triage_assistant.md"),
    EvalQuestion("What's my plan for the AI rim quote assistant using vision models?", "TuzikVault/lucauto_triage_assistant.md"),
    EvalQuestion("What's the post-appointment WhatsApp/SMS review-request flow I designed?", "TuzikVault/lucauto_reviews_pipeline.md"),
    EvalQuestion("What's my Google review acquisition funnel strategy for LucAuto?", "TuzikVault/lucauto_reviews_pipeline.md"),

    # --- LucAuto: shipped/operational ---
    EvalQuestion("Which tire suppliers does the scraping pipeline pull from?", "TuzikVault/lucauto_operations.md"),
    EvalQuestion("How does LucAuto's booking system integrate with Google Calendar?", "TuzikVault/lucauto_operations.md"),
    EvalQuestion("What's LucAuto's follower count and which platforms is it active on?", "TuzikVault/lucauto_operations.md"),

    # --- Investing / VMS ---
    EvalQuestion("What's the tax treatment of Moldovan VMS securities?", "TuzikVault/vms_investing.md"),
    EvalQuestion("How did I compare garsoniera rental yield vs VMS returns?", "TuzikVault/vms_investing.md"),
    EvalQuestion("What conclusion did I reach on fiscal reform impact on VMS yields?", "TuzikVault/vms_investing.md"),

    # --- Car research ---
    EvalQuestion("What did I conclude about DSG gearbox reliability across VAG models?", "TuzikVault/car_research.md"),
    EvalQuestion("What did I learn about verifying hybrid battery health on Korean imports?", "TuzikVault/car_research.md"),

    # --- Personal / life admin ---
    EvalQuestion("What's in my wedding budget model?", "TuzikVault/wedding_and_crete.md"),
    EvalQuestion("What did I decide about Crete vacation planning?", "TuzikVault/wedding_and_crete.md"),

    # --- Meta: second brain / RAG project itself ---
    EvalQuestion("What chunking strategy did I decide on for the Obsidian RAG pipeline?", "TuzikVault/rag_pipeline_design.md"),
    EvalQuestion("Which vector store did I choose for the second brain, and why over alternatives?", "TuzikVault/rag_pipeline_design.md"),

    # --- Negative controls (should retrieve nothing / low confidence — don't force an answer) ---
    EvalQuestion("What did I decide about buying a Tesla?", "NONE"),
    EvalQuestion("What's my strategy for learning Mandarin?", "NONE"),
]
