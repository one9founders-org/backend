"""Indian-fintech vendors we are willing to score from published pages.

Hand-reviewed rows were scored by a person and are skipped unless the
ingest command is passed --overwrite-reviewed. New rows are product
descriptions only — compliance claims come from crawled pages.
"""

from __future__ import annotations

from dataclasses import dataclass

STACK_KYC = "kyc"
STACK_CREDIT = "credit"
STACK_FRAUD = "fraud"


@dataclass(frozen=True)
class CatalogVendor:
    slug: str
    name: str
    website: str
    stack: str
    one_liner: str
    india_relevance: str
    hand_reviewed: bool = False


VENDORS: tuple[CatalogVendor, ...] = (
    CatalogVendor(
        slug="signzy",
        name="Signzy",
        website="https://www.signzy.com/",
        stack=STACK_KYC,
        one_liner="KYC, KYB, and AML APIs plus a no-code onboarding platform sold to banks and fintechs.",
        india_relevance="Headquarters in Bengaluru. Hand-reviewed preview rating.",
        hand_reviewed=True,
    ),
    CatalogVendor(
        slug="hyperverge",
        name="HyperVerge",
        website="https://hyperverge.co/",
        stack=STACK_KYC,
        one_liner="AI eKYC, passive liveness, face authentication, and video KYC used for digital onboarding.",
        india_relevance="Offices in Bengaluru, Mumbai, and Coimbatore. Hand-reviewed preview rating.",
        hand_reviewed=True,
    ),
    CatalogVendor(
        slug="idfy",
        name="IDfy",
        website="https://www.idfy.com/",
        stack=STACK_KYC,
        one_liner="India-native KYC, video KYC, and fraud APIs, plus Privy for DPDP consent and privacy ops.",
        india_relevance="Mumbai-based (Baldor Technologies). Hand-reviewed preview rating.",
        hand_reviewed=True,
    ),
    CatalogVendor(
        slug="karza",
        name="Karza",
        website="https://karza.in/",
        stack=STACK_KYC,
        one_liner="Identity, business, and financial-data APIs used in Indian lending onboarding.",
        india_relevance="Indian KYC/data APIs; Karza was acquired by Perfios. Confirm the live contracting entity.",
    ),
    CatalogVendor(
        slug="authbridge",
        name="AuthBridge",
        website="https://authbridge.com/",
        stack=STACK_KYC,
        one_liner="KYC, KYB, and background-verification APIs sold to Indian enterprises and BFSI.",
        india_relevance="Gurugram-based verification company. Confirm India residency in the KYC contract.",
    ),
    CatalogVendor(
        slug="surepass",
        name="Surepass",
        website="https://surepass.io/",
        stack=STACK_KYC,
        one_liner="Digital KYC, CKYC, Aadhaar/PAN, and onboarding APIs for Indian businesses.",
        india_relevance="India onboarding APIs including CKYC and Aadhaar flows. Confirm DPDP terms.",
    ),
    CatalogVendor(
        slug="zoop",
        name="Zoop",
        website="https://www.zoop.one/",
        stack=STACK_KYC,
        one_liner="Identity APIs covering DigiLocker, CKYC, and Indian ID checks.",
        india_relevance="Sells Indian identity rails (DigiLocker, CKYC). Confirm data residency.",
    ),
    CatalogVendor(
        slug="decentro",
        name="Decentro",
        website="https://decentro.tech/",
        stack=STACK_KYC,
        one_liner="Modular identity, KYC, and banking-stack APIs for Indian fintechs.",
        india_relevance="Bengaluru API platform used by Indian fintechs. Confirm KYC hosting region.",
    ),
    CatalogVendor(
        slug="setu",
        name="Setu",
        website="https://setu.co/",
        stack=STACK_KYC,
        one_liner="Account Aggregator, KYC, and data-sharing APIs built for India.",
        india_relevance="Indian AA / KYC rails. Confirm DPDP consent and residency on published pages.",
    ),
    CatalogVendor(
        slug="gridlines",
        name="Gridlines",
        website="https://gridlines.io/",
        stack=STACK_KYC,
        one_liner="KYC APIs for Indian IDs, CKYC, DigiLocker, and video KYC.",
        india_relevance="Indian verification APIs marketed to fintechs. Confirm certifications on-site.",
    ),
    CatalogVendor(
        slug="digitap",
        name="Digitap",
        website="https://digitap.ai/",
        stack=STACK_KYC,
        one_liner="Income and identity APIs used in Indian digital lending onboarding.",
        india_relevance="Indian lender-facing identity/income APIs. Confirm residency and DPDP pages.",
    ),
    CatalogVendor(
        slug="bureau",
        name="Bureau",
        website="https://www.bureau.id/",
        stack=STACK_KYC,
        one_liner="Identity, device intelligence, and onboarding APIs used by fintechs.",
        india_relevance="Has an India presence. Confirm where KYC data is stored for Indian customers.",
    ),
    CatalogVendor(
        slug="onfido",
        name="Onfido",
        website="https://onfido.com/",
        stack=STACK_KYC,
        one_liner="Document and biometric identity verification used globally, including by some Indian NBFCs.",
        india_relevance="Global vendor (Entrust). Public pages may be multi-region — confirm the India contract.",
    ),
    CatalogVendor(
        slug="sumsub",
        name="Sumsub",
        website="https://sumsub.com/",
        stack=STACK_KYC,
        one_liner="KYC/KYB orchestration, liveness, and AML screening for online onboarding.",
        india_relevance="Global KYC vendor. Confirm India data residency before using in a regulated stack.",
    ),
    CatalogVendor(
        slug="kychub",
        name="KYC Hub",
        website="https://www.kychub.com/",
        stack=STACK_KYC,
        one_liner="No-code KYC/KYB orchestration and case-management for regulated onboarding.",
        india_relevance="Used in some Indian onboarding stacks. Confirm local hosting and DPDP terms.",
    ),
    CatalogVendor(
        slug="shuftipro",
        name="Shufti Pro",
        website="https://shuftipro.com/",
        stack=STACK_KYC,
        one_liner="Identity verification, AML screening, and KYB checks sold globally.",
        india_relevance="Global vendor with Indian ID coverage. Confirm residency, not just ID type support.",
    ),
    CatalogVendor(
        slug="perfios",
        name="Perfios",
        website="https://perfios.ai/",
        stack=STACK_CREDIT,
        one_liner="Bank-statement, GST, and ITR analysers plus AI credit decisioning sold to banks and NBFCs.",
        india_relevance="Bengaluru-headquartered. Hand-reviewed preview rating.",
        hand_reviewed=True,
    ),
    CatalogVendor(
        slug="scienaptic",
        name="Scienaptic",
        website="https://www.scienaptic.ai/",
        stack=STACK_CREDIT,
        one_liner="AI credit decisioning with scorecards, a business-rule engine, and adverse-action reason codes.",
        india_relevance="Indian entity in Bengaluru. Hand-reviewed preview rating.",
        hand_reviewed=True,
    ),
    CatalogVendor(
        slug="finbox",
        name="FinBox",
        website="https://www.finbox.in/",
        stack=STACK_CREDIT,
        one_liner="Digital lending OS with BankConnect, DeviceConnect, and Sentinel decisioning used by Indian NBFCs.",
        india_relevance="Bengaluru HQ (Moshpit Technologies). Hand-reviewed preview rating.",
        hand_reviewed=True,
    ),
    CatalogVendor(
        slug="experian-india",
        name="Experian India",
        website="https://www.experian.in/",
        stack=STACK_CREDIT,
        one_liner="Credit bureau, analytics, and decisioning products sold to Indian lenders.",
        india_relevance="Licensed Indian credit bureau / analytics. Confirm which product the NBFC actually buys.",
    ),
    CatalogVendor(
        slug="crif-high-mark",
        name="CRIF High Mark",
        website="https://www.crifhighmark.com/",
        stack=STACK_CREDIT,
        one_liner="Indian credit bureau and analytics used by banks and NBFCs.",
        india_relevance="RBI-recognised Indian credit information company. Score only published product pages.",
    ),
    CatalogVendor(
        slug="transunion-cibil",
        name="TransUnion CIBIL",
        website="https://www.transunioncibil.com/",
        stack=STACK_CREDIT,
        one_liner="Indian credit bureau scores and analytics used across retail lending.",
        india_relevance="RBI-recognised Indian credit information company. Confirm product vs bureau report.",
    ),
    CatalogVendor(
        slug="equifax-india",
        name="Equifax India",
        website="https://www.equifax.co.in/",
        stack=STACK_CREDIT,
        one_liner="Credit information and analytics for Indian lenders.",
        india_relevance="Indian credit information company. Confirm analytics/AI product pages separately.",
    ),
    CatalogVendor(
        slug="lentra",
        name="Lentra",
        website="https://www.lentra.ai/",
        stack=STACK_CREDIT,
        one_liner="Lending platform and AI decisioning sold to Indian banks and NBFCs.",
        india_relevance="Indian lending-platform vendor. Confirm where underwriting data is stored.",
    ),
    CatalogVendor(
        slug="finezza",
        name="Finezza",
        website="https://finezza.in/",
        stack=STACK_CREDIT,
        one_liner="Loan origination and credit-decision workflows for Indian NBFCs.",
        india_relevance="Indian LOS / decisioning vendor. Confirm DPDP and residency on published pages.",
    ),
    CatalogVendor(
        slug="trusting-social",
        name="Trusting Social",
        website="https://www.trustingsocial.com/",
        stack=STACK_CREDIT,
        one_liner="Alternative credit scoring and identity insights used in emerging-market lending.",
        india_relevance="Operates in India. Confirm India processing and fairness testing on their domain.",
    ),
    CatalogVendor(
        slug="arya-ai",
        name="Arya.ai",
        website="https://arya.ai/",
        stack=STACK_CREDIT,
        one_liner="Document intelligence and underwriting AI used by Indian financial institutions.",
        india_relevance="Mumbai-based AI vendor selling to Indian FIs. Confirm model-explainability pages.",
    ),
    CatalogVendor(
        slug="tookitaki",
        name="Tookitaki",
        website="https://www.tookitaki.com/",
        stack=STACK_FRAUD,
        one_liner="AML transaction monitoring and community-driven typologies for banks and fintechs.",
        india_relevance="Singapore HQ with Indian bank customers. Confirm India data hosting.",
    ),
    CatalogVendor(
        slug="clari5",
        name="Clari5",
        website="https://www.clari5.com/",
        stack=STACK_FRAUD,
        one_liner="Real-time fraud and AML surveillance sold to Indian banks.",
        india_relevance="Indian fraud/AML vendor used by banks. Confirm certifications on published pages.",
    ),
    CatalogVendor(
        slug="feedzai",
        name="Feedzai",
        website="https://www.feedzai.com/",
        stack=STACK_FRAUD,
        one_liner="AI financial-crime risk management for payments, banking, and AML.",
        india_relevance="Global FRM vendor. Confirm India residency before putting it in an NBFC stack.",
    ),
    CatalogVendor(
        slug="complyadvantage",
        name="ComplyAdvantage",
        website="https://complyadvantage.com/",
        stack=STACK_FRAUD,
        one_liner="AML screening, adverse media, and transaction monitoring used by fintechs.",
        india_relevance="Global AML vendor. Confirm where screening data for Indian customers is stored.",
    ),
    CatalogVendor(
        slug="seon",
        name="SEON",
        website="https://seon.io/",
        stack=STACK_FRAUD,
        one_liner="Device, digital-footprint, and fraud APIs used in onboarding and payments.",
        india_relevance="Global fraud vendor used by some Indian fintechs. Confirm DPDP/residency pages.",
    ),
    CatalogVendor(
        slug="sardine",
        name="Sardine",
        website="https://www.sardine.ai/",
        stack=STACK_FRAUD,
        one_liner="Fraud, AML, and KYC orchestration with device and behavior signals.",
        india_relevance="Global vendor. Confirm India processing if used by a regulated Indian entity.",
    ),
    CatalogVendor(
        slug="featurespace",
        name="Featurespace",
        website="https://www.featurespace.com/",
        stack=STACK_FRAUD,
        one_liner="Adaptive behavioral analytics for payments fraud and AML.",
        india_relevance="Global FRM vendor. Confirm India hosting and explainability pages.",
    ),
    CatalogVendor(
        slug="napier",
        name="Napier AI",
        website="https://www.napier.ai/",
        stack=STACK_FRAUD,
        one_liner="AML platform covering screening, monitoring, and client risk assessment.",
        india_relevance="Global AML vendor. Confirm whether Indian FI deployments keep data in India.",
    ),
    CatalogVendor(
        slug="unit21",
        name="Unit21",
        website="https://www.unit21.ai/",
        stack=STACK_FRAUD,
        one_liner="No-code transaction monitoring, AML case management, and fraud ops.",
        india_relevance="Global AML/fraud ops vendor. Confirm India data-residency claims on-site.",
    ),
)


def vendors_for(
    stack: str | None = None,
    slug: str | None = None,
) -> list[CatalogVendor]:
    rows = list(VENDORS)
    if stack and stack != "all":
        rows = [row for row in rows if row.stack == stack]
    if slug:
        needle = slug.strip().lower()
        rows = [row for row in rows if row.slug == needle]
    return rows
