import logging
import xml.etree.ElementTree as ET

import requests
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime

from research_papers.models import Author, Paper

logger = logging.getLogger(__name__)

ARXIV_API_URL = (
    "http://export.arxiv.org/api/query"
    "?search_query=cat:cs.AI+OR+cat:cs.CL+OR+cat:cs.LG+OR+cat:cs.IR"
    "&sortBy=submittedDate&sortOrder=descending&max_results=100"
)

HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"

ATOM_NS = "{http://www.w3.org/2005/Atom}"


class Command(BaseCommand):
    help = "Ingest papers from arXiv and cross-reference with HuggingFace"

    def handle(self, *args, **options):
        self.stdout.write("Fetching papers from arXiv...")
        arxiv_new = self._ingest_arxiv()

        self.stdout.write("Cross-referencing with HuggingFace daily papers...")
        hf_updated = self._sync_hf()

        self.stdout.write(
            self.style.SUCCESS(
                f"Ingested {arxiv_new} new papers, updated {hf_updated} with HF data"
            )
        )

    def _ingest_arxiv(self):
        try:
            resp = requests.get(ARXIV_API_URL, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.error("Failed to fetch arXiv API: %s", e)
            return 0

        root = ET.fromstring(resp.content)
        entries = root.findall(f"{ATOM_NS}entry")
        self.stdout.write(f"Found {len(entries)} entries from arXiv")

        existing_ids = set(Paper.objects.values_list("arxiv_id", flat=True))

        created = 0
        for entry in entries:
            try:
                arxiv_id = self._extract_arxiv_id(entry)
                if not arxiv_id or arxiv_id in existing_ids:
                    continue

                title = entry.findtext(f"{ATOM_NS}title", "").strip().replace("\n", " ")
                abstract = (
                    entry.findtext(f"{ATOM_NS}summary", "").strip().replace("\n", " ")
                )
                published = entry.findtext(f"{ATOM_NS}published", "")
                updated = entry.findtext(f"{ATOM_NS}updated", "")

                authors = []
                for author_el in entry.findall(f"{ATOM_NS}author"):
                    name = author_el.findtext(f"{ATOM_NS}name", "").strip()
                    if name:
                        authors.append(name)

                categories = []
                for cat_el in entry.findall(f"{ATOM_NS}category"):
                    term = cat_el.get("term", "")
                    if term:
                        categories.append(term)

                pdf_url = ""
                arxiv_url = ""
                for link_el in entry.findall(f"{ATOM_NS}link"):
                    href = link_el.get("href", "")
                    link_type = link_el.get("type", "")
                    if link_type == "application/pdf":
                        pdf_url = href
                    elif link_el.get("rel") == "alternate":
                        arxiv_url = href

                if not pdf_url:
                    pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"
                if not arxiv_url:
                    arxiv_url = f"https://arxiv.org/abs/{arxiv_id}"

                published_dt = parse_datetime(published)
                updated_dt = parse_datetime(updated) if updated else None

                paper = Paper.objects.create(
                    arxiv_id=arxiv_id,
                    title=title,
                    abstract=abstract,
                    authors=authors,
                    categories=categories,
                    published_at=published_dt,
                    updated_at_arxiv=updated_dt,
                    pdf_url=pdf_url,
                    arxiv_url=arxiv_url,
                )

                # Update author records
                for author_name in authors:
                    author_obj, _ = Author.objects.get_or_create(name=author_name)
                    author_obj.papers.add(paper)
                    author_obj.paper_count = author_obj.papers.count()
                    author_obj.save(update_fields=["paper_count"])

                created += 1
                existing_ids.add(arxiv_id)

            except Exception as e:
                logger.warning("Error processing arXiv entry: %s", e)
                continue

        return created

    def _extract_arxiv_id(self, entry):
        id_text = entry.findtext(f"{ATOM_NS}id", "")
        if "/abs/" in id_text:
            return id_text.split("/abs/")[-1].split("v")[0]
        return ""

    def _sync_hf(self):
        try:
            resp = requests.get(HF_DAILY_PAPERS_URL, timeout=30)
            resp.raise_for_status()
            papers_data = resp.json()
        except Exception as e:
            logger.error("Failed to fetch HF daily papers: %s", e)
            return 0

        updated = 0
        for item in papers_data:
            try:
                paper_info = item.get("paper", item)
                arxiv_id = paper_info.get("id", "")
                if not arxiv_id:
                    continue

                try:
                    paper = Paper.objects.get(arxiv_id=arxiv_id)
                except Paper.DoesNotExist:
                    continue

                upvotes = item.get("numUpvotes", paper_info.get("upvotes", 0))
                hf_url = f"https://huggingface.co/papers/{arxiv_id}"

                update_fields = []
                if upvotes and upvotes != paper.hf_upvotes:
                    paper.hf_upvotes = upvotes
                    update_fields.append("hf_upvotes")
                if hf_url and hf_url != paper.hf_url:
                    paper.hf_url = hf_url
                    update_fields.append("hf_url")

                if update_fields:
                    paper.save(update_fields=update_fields)
                    updated += 1

            except Exception as e:
                logger.warning("Error processing HF paper: %s", e)
                continue

        return updated
