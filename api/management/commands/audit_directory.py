"""Read-only census of directory data quality. No network, no API keys."""

import collections

from django.core.management.base import BaseCommand
from django.db.models import Count, Q

from api.hygiene.classify import PRODUCT, classify, host_of, normalized_name
from api.hygiene.signals import lookup_tranco, open_tranco
from api.models import Tool


def _pct(part: int, whole: int) -> str:
    return f"{(100.0 * part / whole):5.1f}%" if whole else "  n/a"


class Command(BaseCommand):
    help = "Report directory data quality without changing anything."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Only audit the first N tools (0 = all).",
        )

    def handle(self, *args, **options):
        queryset = Tool.objects.all().only(
            "id",
            "name",
            "website",
            "short_description",
            "description",
            "logo_url",
            "tags",
            "use_cases",
            "pricing_from",
            "rating",
            "review_count",
            "views_count",
        )
        if options["limit"]:
            queryset = queryset[: options["limit"]]

        total = 0
        empty = collections.Counter()
        entry_types = collections.Counter()
        flags = collections.Counter()
        names = collections.Counter()
        tag_vocab = collections.Counter()
        product_hosts: list[str] = []
        zero_signal = 0

        for tool in queryset.iterator(chunk_size=500):
            total += 1
            for field_name in (
                "short_description",
                "description",
                "logo_url",
                "website",
                "tags",
                "use_cases",
                "pricing_from",
            ):
                if not getattr(tool, field_name):
                    empty[field_name] += 1

            entry_type, name_flags = classify(tool.name, tool.website or "")
            entry_types[entry_type] += 1
            if entry_type == PRODUCT:
                host = host_of(tool.website or "")
                if host:
                    product_hosts.append(host)
            for flag in name_flags:
                flags[flag] += 1
            names[normalized_name(tool.name)] += 1
            for tag in tool.tags or []:
                tag_vocab[tag] += 1
            if not (tool.review_count or tool.views_count):
                zero_signal += 1

        if not total:
            self.stdout.write("No tools found.")
            return

        write = self.stdout.write
        write(f"\n=== DIRECTORY AUDIT ({total:,} tools) ===\n")

        write("-- Missing fields --")
        for field_name, count in empty.most_common():
            write(f"  {field_name:<22} {count:>7,}  {_pct(count, total)}")

        write("\n-- What these rows actually are --")
        for entry_type, count in entry_types.most_common():
            write(f"  {entry_type:<22} {count:>7,}  {_pct(count, total)}")

        write("\n-- Name quality flags --")
        if flags:
            for flag, count in flags.most_common():
                write(f"  {flag:<22} {count:>7,}  {_pct(count, total)}")
        else:
            write("  none")

        collisions = sum(1 for count in names.values() if count > 1)
        write(f"\n-- Duplicates --\n  near-duplicate names   {collisions:>7,}")

        write(
            f"\n-- Ranking signal --\n"
            f"  no reviews and no views {zero_signal:>6,}  {_pct(zero_signal, total)}"
        )
        self._write_tranco_coverage(write, product_hosts, entry_types[PRODUCT])

        untagged = empty["tags"]
        write(
            f"\n-- Tag vocabulary --\n"
            f"  distinct tags in use   {len(tag_vocab):>7,}\n"
            f"  tools with zero tags   {untagged:>7,}  {_pct(untagged, total)}"
        )

        counts = Tool.objects.aggregate(
            featured=Count("id", filter=Q(is_featured=True)),
            verified=Count("id", filter=Q(verified=True)),
            inactive=Count("id", filter=Q(is_active=False)),
            hygiened=Count("id", filter=Q(last_hygiene_at__isnull=False)),
            stored_product=Count("id", filter=Q(entry_type="product")),
            stored_gpt=Count("id", filter=Q(entry_type="gpt_store")),
            stored_app=Count("id", filter=Q(entry_type="app_listing")),
            stored_ext=Count("id", filter=Q(entry_type="extension")),
            stored_market=Count("id", filter=Q(entry_type="marketplace")),
            stored_no_url=Count("id", filter=Q(entry_type="no_url")),
            logos=Count("id", filter=~Q(logo_url="") & Q(logo_url__isnull=False)),
            tagged=Count("id", filter=~Q(tags=[])),
            broken=Count("id", filter=Q(link_status="broken")),
            unreachable=Count("id", filter=Q(link_status="unreachable")),
            parked=Count("id", filter=Q(link_status="parked")),
            malformed=Count("id", filter=Q(link_status="malformed")),
            ok_link=Count("id", filter=Q(link_status__in=["ok", "redirected"])),
        )
        write(
            f"\n-- Status --\n"
            f"  featured {counts['featured']:,} | verified {counts['verified']:,} | "
            f"inactive {counts['inactive']:,} | hygiened {counts['hygiened']:,}\n"
        )
        write("-- Stored entry_type (after hygiene; default is product) --")
        for label, key in (
            ("product", "stored_product"),
            ("gpt_store", "stored_gpt"),
            ("app_listing", "stored_app"),
            ("extension", "stored_ext"),
            ("marketplace", "stored_market"),
            ("no_url", "stored_no_url"),
        ):
            write(f"  {label:<22} {counts[key]:>7,}  {_pct(counts[key], total)}")
        write(
            f"\n-- Stored quality --\n"
            f"  with logo_url          {counts['logos']:>7,}  "
            f"{_pct(counts['logos'], total)}\n"
            f"  with tags              {counts['tagged']:>7,}  "
            f"{_pct(counts['tagged'], total)}\n"
            f"  link ok/redirected     {counts['ok_link']:>7,}\n"
            f"  link broken            {counts['broken']:>7,}\n"
            f"  link unreachable       {counts['unreachable']:>7,}\n"
            f"  link parked            {counts['parked']:>7,}\n"
            f"  link malformed         {counts['malformed']:>7,}\n"
        )

    def _write_tranco_coverage(
        self, write, product_hosts: list[str], product_rows: int
    ):
        """Local sqlite lookup -- still no network."""
        connection = open_tranco()
        if connection is None:
            write(
                "\n-- Tranco coverage --\n"
                "  database missing; run manage.py refresh_tranco"
            )
            return

        unique_hosts = list(dict.fromkeys(product_hosts))
        ranked = 0
        inherited = 0
        try:
            for host in unique_hosts:
                rank, was_inherited = lookup_tranco(host, connection)
                if rank:
                    ranked += 1
                    if was_inherited:
                        inherited += 1
        finally:
            connection.close()

        write(
            f"\n-- Tranco coverage (live-classified products) --\n"
            f"  product rows            {product_rows:>7,}\n"
            f"  unique product hosts    {len(unique_hosts):>7,}\n"
            f"  hosts with a rank       {ranked:>7,}  "
            f"{_pct(ranked, len(unique_hosts))}\n"
            f"  of which inherited      {inherited:>7,}\n"
        )
