"""Fintech published-evidence ratings.

FintechCheck / FintechRating are the RBI/DPDP layer. They reuse the
assessment_detail shape (version, method, hands_on, criteria with
evidence_url + reasoning) but never write Tool.overall_score,
security_criterion_score, or assessment_detail — those stay the general
directory methodology.
"""

from __future__ import annotations

from datetime import date

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

KYC_REVIEWED_AT = date(2026, 8, 22)

CHECKS = [
    {
        "slug": "dataLocalization",
        "name": "Data Localization",
        "description": "Is your data stored in India per RBI and DPDP requirements?",
        "sort_order": 1,
    },
    {
        "slug": "consentManagement",
        "name": "Consent Management",
        "description": "Does the tool honor consent withdrawal as DPDP mandates?",
        "sort_order": 2,
    },
    {
        "slug": "modelExplainability",
        "name": "Model Explainability",
        "description": "Can the vendor explain how their AI makes decisions?",
        "sort_order": 3,
    },
    {
        "slug": "securityCerts",
        "name": "Security Certs",
        "description": "SOC 2 Type II, ISO 27001, PCI DSS — only if a page claims it.",
        "sort_order": 4,
    },
    {
        "slug": "biasTesting",
        "name": "Bias Testing",
        "description": "Has the model been tested for discriminatory outcomes?",
        "sort_order": 5,
    },
    {
        "slug": "vendorViability",
        "name": "Vendor Viability",
        "description": "Funding, team, MCA filings, or equivalent public proof.",
        "sort_order": 6,
    },
]

# Published-page KYC preview. Pass/Fail must include evidence_url.
KYC_VENDORS = [
    {
        "slug": "signzy",
        "name": "Signzy",
        "website": "https://www.signzy.com/",
        "short_description": (
            "KYC, KYB, and AML APIs plus a no-code onboarding platform sold to banks and fintechs."
        ),
        "india_relevance": (
            "Headquarters in Bengaluru. India API Marketplace is pitched to banks, "
            "NBFCs, and insurers, with a published RBI/UIDAI compliance claim."
        ),
        "ratings": [
            {
                "check": "dataLocalization",
                "result": "pass",
                "rationale": (
                    "India API Marketplace FAQ claims data residency within India; "
                    "About also lists regional data-residence including India. Global "
                    "privacy policy still names US and other jurisdictions — confirm the India contract."
                ),
                "evidence_url": "https://www.signzy.com/india-api-marketplace",
                "evidence_label": "India API Marketplace FAQ",
            },
            {
                "check": "consentManagement",
                "result": "unknown",
                "rationale": (
                    "Privacy policy lets users withdraw consent, but as a processor "
                    "Signzy redirects those requests to the customer. No DPDP "
                    "consent-manager / withdrawal product page found."
                ),
            },
            {
                "check": "modelExplainability",
                "result": "pass",
                "rationale": (
                    "Vendor blog on AI fake-ID KYC claims multi-signal risk scores "
                    "with explainability for each flagged signal. Not a model card for every KYC model."
                ),
                "evidence_url": "https://www.signzy.com/blogs/ai-fake-id-kyc-detection-prevention",
                "evidence_label": "AI fake-ID KYC blog",
            },
            {
                "check": "securityCerts",
                "result": "pass",
                "rationale": (
                    "About page states ISO 27001, SOC 2 Type II, and PCI-DSS. "
                    "Homepage separately marks ISO 27001 Certified and SOC 2 Compliant."
                ),
                "evidence_url": "https://www.signzy.com/about-us",
                "evidence_label": "About us — security FAQ",
            },
            {
                "check": "biasTesting",
                "result": "unknown",
                "rationale": (
                    "No published fairness study, disparate-impact test, or "
                    "bias-audit report found for Signzy KYC/biometric models."
                ),
            },
            {
                "check": "vendorViability",
                "result": "pass",
                "rationale": (
                    "Company blog republishes that Signzy raised ₹210 crore (~$26M) "
                    "from Gaja Capital, Vertex Ventures, and Arkam Ventures. "
                    "Bengaluru HQ and three India offices are listed on About."
                ),
                "evidence_url": "https://www.signzy.com/blogs/signzy-raises-210cr",
                "evidence_label": "Signzy funding post",
            },
        ],
    },
    {
        "slug": "hyperverge",
        "name": "HyperVerge",
        "website": "https://hyperverge.co/",
        "short_description": (
            "AI eKYC, passive liveness, face authentication, and video KYC used for digital onboarding."
        ),
        "india_relevance": (
            "Offices in Bengaluru, Mumbai, and Coimbatore. NBFC page claims "
            "RBI-compliant onboarding; homepage shows Video KYC and Indian ID checks."
        ),
        "ratings": [
            {
                "check": "dataLocalization",
                "result": "unknown",
                "rationale": (
                    "No vendor page found that says customer KYC data is stored or "
                    "processed in India. Blogs discuss localization as a buyer "
                    "requirement, not a named India data-centre claim."
                ),
            },
            {
                "check": "consentManagement",
                "result": "pass",
                "rationale": (
                    "HyperTrust product page advertises DPDP consent capture, review, "
                    "and withdrawal tracking with immutable consent logs. That is a "
                    "consent product, not a claim about the KYC API itself."
                ),
                "evidence_url": "https://hyperverge.co/dpdpa-consent-management-hypertrust/",
                "evidence_label": "HyperTrust DPDP consent",
            },
            {
                "check": "modelExplainability",
                "result": "unknown",
                "rationale": (
                    "Homepage describes AI liveness and deepfake detection. No page "
                    "found that explains individual KYC/AI decisions or publishes a model card."
                ),
            },
            {
                "check": "securityCerts",
                "result": "pass",
                "rationale": (
                    "Homepage “Certified, Compliant, and Patented” block displays "
                    "AICPA SOC 2 and ISO 27018. Type I vs Type II is not stated. "
                    "ISO 27001 was not claimed on that page."
                ),
                "evidence_url": "https://hyperverge.co/",
                "evidence_label": "HyperVerge homepage certs",
            },
            {
                "check": "biasTesting",
                "result": "unknown",
                "rationale": (
                    "Homepage slogan “Built to Verify Every Demographic, Without Bias” "
                    "is marketing copy, not a published fairness test or audit."
                ),
            },
            {
                "check": "vendorViability",
                "result": "pass",
                "rationale": (
                    "About page states HyperVerge has scaled to $19M+ ARR while raising "
                    "$1.1M, and lists India offices in Bengaluru, Mumbai, and Coimbatore."
                ),
                "evidence_url": "https://hyperverge.co/about-us/",
                "evidence_label": "About us",
            },
        ],
    },
    {
        "slug": "idfy",
        "name": "IDfy",
        "website": "https://www.idfy.com/",
        "short_description": (
            "India-native KYC, video KYC, and fraud APIs, plus Privy for DPDP consent and privacy ops."
        ),
        "india_relevance": (
            "Mumbai-based (Baldor Technologies). KYC page claims RBI, SEBI, and "
            "IRDAI alignment. Funding post names Indian FI clients including HDFC Bank."
        ),
        "ratings": [
            {
                "check": "dataLocalization",
                "result": "pass",
                "rationale": (
                    "Company blog states full compliance with RBI data-localization "
                    "requirements and that customer-sensitive data is stored and processed in India."
                ),
                "evidence_url": (
                    "https://www.idfy.com/blog/soc-2-compliance--beyond-certifications-that-power-idfys-security-standards/"
                ),
                "evidence_label": "SOC 2 / compliance blog",
            },
            {
                "check": "consentManagement",
                "result": "pass",
                "rationale": (
                    "Privy by IDfy is published as a DPDP platform covering consent "
                    "lifecycle, including collection, updates, and revocation, with audit-ready artifacts."
                ),
                "evidence_url": "https://www.idfy.com/privy/dpdp-compliance-platform/",
                "evidence_label": "Privy by IDfy",
            },
            {
                "check": "modelExplainability",
                "result": "unknown",
                "rationale": (
                    "KYC product pages describe OCR, FaceMatch, and liveness. No cited "
                    "page explains how those AI models decide, or publishes reason codes for KYC outcomes."
                ),
            },
            {
                "check": "securityCerts",
                "result": "pass",
                "rationale": (
                    "Homepage claims ISO 27001 and SOC 2 Type 2. A company blog also "
                    "states SOC 2 Type II and ISO 27001:2022 for the VKYC platform."
                ),
                "evidence_url": "https://www.idfy.com/",
                "evidence_label": "IDfy homepage",
            },
            {
                "check": "biasTesting",
                "result": "unknown",
                "rationale": (
                    "IDfy blogs discuss bias auditing as something lenders should do. "
                    "No published bias test of IDfy’s own KYC or biometric models was found."
                ),
            },
            {
                "check": "vendorViability",
                "result": "pass",
                "rationale": (
                    "Company blog: Series D of ₹86 crore led by TransUnion and Blume "
                    "Ventures (Oct 2021). Legal entity named as Baldor Technologies Pvt. Ltd."
                ),
                "evidence_url": (
                    "https://www.idfy.com/blog/id-verification-company-idfy-raises-inr-86-crore-from-transunion-and-blume-ventures/"
                ),
                "evidence_label": "Series D announcement",
            },
        ],
    },
]


def assessment_detail_from_ratings(ratings, *, stack: str) -> dict:
    """Same envelope as Tool.assessment_detail, plus result (pass/fail/unknown)."""
    criteria = {}
    unassessed = []
    reviewed_at = None
    for row in ratings:
        check = row.check
        criteria[check.slug] = {
            "name": check.name,
            "score": None,
            "result": row.result,
            "evidence_url": row.evidence_url or None,
            "evidence_label": row.evidence_label or None,
            "reasoning": row.rationale,
            "automated": True,
        }
        if row.result == row.RESULT_UNKNOWN:
            unassessed.append(check.slug)
        if reviewed_at is None or row.reviewed_at > reviewed_at:
            reviewed_at = row.reviewed_at
    return {
        "version": 1,
        "method": "published_evidence",
        "hands_on": False,
        "model": None,
        "stack": stack,
        "reviewed_at": reviewed_at.isoformat() if reviewed_at else None,
        "criteria": criteria,
        "unassessed": unassessed,
        "manual_only": [],
    }


CREDIT_REVIEWED_AT = date(2026, 8, 24)

# CreditVidya skipped: acquired by CRED (2022). Public surface is a 2019
# engineering blog, not a live product Indian NBFCs still buy.
CREDIT_VENDORS = [
    {
        "slug": "perfios",
        "name": "Perfios",
        "website": "https://perfios.ai/",
        "short_description": (
            "Bank-statement, GST, and ITR analysers plus AI credit decisioning "
            "sold to banks and NBFCs."
        ),
        "india_relevance": (
            "Bengaluru-headquartered (Perfios Software Solutions). Series D press "
            "and About pitch underwriting to Indian FIs. Trust Centre lists India "
            "as a data-residency option, not the only region."
        ),
        "ratings": [
            {
                "check": "dataLocalization",
                "result": "pass",
                "rationale": (
                    "Trust Centre Data Localization section says Perfios can store "
                    "and process data in specific regions including India, the EU, "
                    "or other locations. Confirm the India contract region."
                ),
                "evidence_url": "https://perfios.ai/trust-centre/",
                "evidence_label": "Perfios Trust Centre",
            },
            {
                "check": "consentManagement",
                "result": "pass",
                "rationale": (
                    "Consent Manager product page describes DPDP Section 6 consent, "
                    "grant/modify/withdrawal, and audit-ready records. That is a "
                    "consent product, not a claim about CreditAssist itself."
                ),
                "evidence_url": (
                    "https://perfios.ai/in/products/consent-management-platform/"
                ),
                "evidence_label": "Perfios Consent Manager",
            },
            {
                "check": "modelExplainability",
                "result": "pass",
                "rationale": (
                    "CreditAssist blog says the product delivers plain-language "
                    "narratives for every decision-driving insight. Not a model "
                    "card for every scorecard."
                ),
                "evidence_url": (
                    "https://perfios.ai/resources/blogs/bias-in-credit-decisioning-"
                    "how-perfios-creditassist-uses-responsible-ai-for-inclusive-lending/"
                ),
                "evidence_label": "CreditAssist responsible-AI blog",
            },
            {
                "check": "securityCerts",
                "result": "pass",
                "rationale": (
                    "Trust Centre lists ISO 27001, SOC 2, ISO 27701, ISO 27017, "
                    "and CSA STAR Level 2 as Perfios certifications. Type I vs "
                    "Type II is not stated on that page."
                ),
                "evidence_url": "https://perfios.ai/trust-centre/",
                "evidence_label": "Perfios Trust Centre",
            },
            {
                "check": "biasTesting",
                "result": "unknown",
                "rationale": (
                    "CreditAssist blog describes data guardrails and bias "
                    "guardrails as product design. No published fairness study, "
                    "disparate-impact test, or audit of Perfios models was found."
                ),
            },
            {
                "check": "vendorViability",
                "result": "pass",
                "rationale": (
                    "About us lists $435.1 Mn funding, Series D $229M (2023), "
                    "and 1000+ customers. Founded 2008 as Perfios Software Solutions."
                ),
                "evidence_url": "https://perfios.ai/about-us/",
                "evidence_label": "About us",
            },
        ],
    },
    {
        "slug": "scienaptic",
        "name": "Scienaptic",
        "website": "https://www.scienaptic.ai/",
        "short_description": (
            "AI credit decisioning with scorecards, a business-rule engine, and "
            "adverse-action reason codes."
        ),
        "india_relevance": (
            "Indian entity Scienaptic Systems Pvt Ltd (Bengaluru). Published "
            "CreditAccess Grameen underwriting win. Public underwriting pages "
            "are US credit-union / NCUA framed."
        ),
        "ratings": [
            {
                "check": "dataLocalization",
                "result": "unknown",
                "rationale": (
                    "No vendor page found that says customer credit data is stored "
                    "or processed in India. Underwriting pages describe US credit-"
                    "union deployments."
                ),
            },
            {
                "check": "consentManagement",
                "result": "unknown",
                "rationale": (
                    "India blogs mention Account Aggregator consent as market "
                    "infrastructure. No DPDP consent-manager or withdrawal "
                    "product page found."
                ),
            },
            {
                "check": "modelExplainability",
                "result": "pass",
                "rationale": (
                    "Underwriting page: every decline includes regulator-ready "
                    "reason codes; “No black box.” The page is written for US "
                    "credit unions / NCUA, not RBI model-risk guidance."
                ),
                "evidence_url": "https://www.scienaptic.ai/underwriting",
                "evidence_label": "Scienaptic underwriting",
            },
            {
                "check": "securityCerts",
                "result": "unknown",
                "rationale": (
                    "No Scienaptic-domain page found that claims SOC 2, ISO 27001, "
                    "or PCI for the credit platform."
                ),
            },
            {
                "check": "biasTesting",
                "result": "unknown",
                "rationale": (
                    "Underwriting page claims disparate-impact analysis on every "
                    "model attribute. That is a product claim, not a published "
                    "fairness study or audit report."
                ),
            },
            {
                "check": "vendorViability",
                "result": "pass",
                "rationale": (
                    "India page republishes that CreditAccess Grameen selected "
                    "Scienaptic to underwrite group and two-wheeler loans. About "
                    "blurb names banks, NBFCs, and MFIs as customers."
                ),
                "evidence_url": "https://www.scienaptic.ai/global",
                "evidence_label": "Scienaptic India / CA Grameen",
            },
        ],
    },
    {
        "slug": "finbox",
        "name": "FinBox",
        "website": "https://www.finbox.in/",
        "short_description": (
            "Digital lending OS with BankConnect, DeviceConnect, and Sentinel "
            "decisioning used by Indian NBFCs."
        ),
        "india_relevance": (
            "Bengaluru HQ (Moshpit Technologies Pvt. Ltd.; CIN on About). Named "
            "Indian FI clients include IIFL Finance and Muthoot FinCorp ONE."
        ),
        "ratings": [
            {
                "check": "dataLocalization",
                "result": "unknown",
                "rationale": (
                    "No FinBox page found that says customer credit data is stored "
                    "in India. Security page lists certs, not residency."
                ),
            },
            {
                "check": "consentManagement",
                "result": "unknown",
                "rationale": (
                    "Multi-AA product is RBI Account Aggregator consent rails. No "
                    "DPDP consent-manager or withdrawal product page found."
                ),
            },
            {
                "check": "modelExplainability",
                "result": "unknown",
                "rationale": (
                    "Underwriting page describes Sentinel as a no-code policy "
                    "engine. No page found that publishes reason codes or a model "
                    "card for FinBox scores."
                ),
            },
            {
                "check": "securityCerts",
                "result": "pass",
                "rationale": (
                    "Security & Compliance page claims ISO 27001:2013 and SOC 2 "
                    "Type II, plus Cert-In empanelled Safe-to-Host / VAPT."
                ),
                "evidence_url": "https://www.finbox.in/security-and-compliance",
                "evidence_label": "Security & Compliance",
            },
            {
                "check": "biasTesting",
                "result": "unknown",
                "rationale": (
                    "Homepage and About use “fairer” credit as marketing copy. No "
                    "published fairness study or bias-audit report found."
                ),
            },
            {
                "check": "vendorViability",
                "result": "pass",
                "rationale": (
                    "About us lists Bengaluru headquarters, Gurugram registered "
                    "office, and legal entity Moshpit Technologies Pvt. Ltd. "
                    "(CIN U72200HR2015PTC055079)."
                ),
                "evidence_url": "https://www.finbox.in/about-us",
                "evidence_label": "About us",
            },
        ],
    },
]


def ensure_checks(check_model=None):
    from .models import FintechCheck

    Check = check_model or FintechCheck
    checks = {}
    for spec in CHECKS:
        obj, _ = Check.objects.update_or_create(
            slug=spec["slug"],
            defaults={
                "name": spec["name"],
                "description": spec["description"],
                "sort_order": spec["sort_order"],
            },
        )
        checks[obj.slug] = obj
    return checks


def seed_stack(
    vendors,
    *,
    stack: str,
    reviewed_at,
    check_model=None,
    rating_model=None,
    tool_model=None,
):
    from .models import FintechRating, Tool

    Rating = rating_model or FintechRating
    ToolModel = tool_model or Tool

    checks = ensure_checks(check_model=check_model)

    tag = "kyc" if stack == "kyc" else stack
    for vendor in vendors:
        tool = ToolModel.objects.filter(slug=vendor["slug"]).first()
        if tool is None:
            tool = ToolModel.objects.filter(name=vendor["name"]).first()
        if tool is None:
            tool = ToolModel(
                slug=vendor["slug"],
                name=vendor["name"],
                description=vendor["short_description"],
                short_description=vendor["short_description"][:200],
                website=vendor["website"],
                startup_benefits=vendor["india_relevance"],
                is_active=True,
                is_featured=False,
                tags=["fintech", tag],
            )
            tool.save()
        elif not tool.startup_benefits:
            tool.startup_benefits = vendor["india_relevance"]
            tool.save(update_fields=["startup_benefits"])
        for rating in vendor["ratings"]:
            obj, _ = Rating.objects.update_or_create(
                tool=tool,
                check=checks[rating["check"]],
                stack=stack,
                defaults={
                    "result": rating["result"],
                    "rationale": rating["rationale"],
                    "evidence_url": rating.get("evidence_url") or "",
                    "evidence_label": rating.get("evidence_label") or "",
                    "reviewed_at": reviewed_at,
                    "india_relevance": vendor["india_relevance"],
                },
            )
            cleaner = getattr(obj, "full_clean", None)
            if callable(cleaner):
                cleaner()


def seed_kyc_preview():
    from .models import FintechRating

    seed_stack(KYC_VENDORS, stack=FintechRating.STACK_KYC, reviewed_at=KYC_REVIEWED_AT)


def seed_credit_preview():
    from .models import FintechRating

    seed_stack(
        CREDIT_VENDORS,
        stack=FintechRating.STACK_CREDIT,
        reviewed_at=CREDIT_REVIEWED_AT,
    )


def serialize_stack(stack: str) -> dict:
    from .models import FintechRating, Tool

    ratings = (
        FintechRating.objects.filter(stack=stack)
        .select_related("tool", "check")
        .order_by("tool__name", "check__sort_order")
    )
    by_tool: dict[int, list] = {}
    tools: dict[int, Tool] = {}
    for row in ratings:
        by_tool.setdefault(row.tool_id, []).append(row)
        tools[row.tool_id] = row.tool

    results = []
    for tool_id, rows in by_tool.items():
        tool = tools[tool_id]
        india = next((r.india_relevance for r in rows if r.india_relevance), "")
        website = tool.website or ""
        host = website.split("://", 1)[-1].split("/", 1)[0].removeprefix("www.")
        results.append(
            {
                "slug": tool.slug,
                "name": tool.name,
                "website": website,
                "website_label": host,
                "one_liner": tool.short_description or tool.description[:200],
                "india_relevance": india,
                "assessment_detail": assessment_detail_from_ratings(rows, stack=stack),
            }
        )
    results.sort(key=lambda row: row["name"].lower())
    reviewed_dates = [
        row["assessment_detail"].get("reviewed_at")
        for row in results
        if row["assessment_detail"].get("reviewed_at")
    ]
    return {
        "stack": stack,
        "method": "published_evidence",
        "hands_on": False,
        "reviewed_at": max(reviewed_dates) if reviewed_dates else None,
        "count": len(results),
        "results": results,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def list_fintech_ratings(request):
    from .models import FintechRating

    stack = (
        (request.query_params.get("stack") or FintechRating.STACK_KYC).strip().lower()
    )
    allowed = {
        FintechRating.STACK_KYC,
        FintechRating.STACK_CREDIT,
        FintechRating.STACK_FRAUD,
    }
    if stack not in allowed:
        return Response({"error": "Unknown stack."}, status=status.HTTP_400_BAD_REQUEST)
    return Response(serialize_stack(stack))
