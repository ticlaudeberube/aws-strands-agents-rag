#!/usr/bin/env python3
"""Resolve relative document links to absolute URLs at ingestion time.

This script processes responses.json and converts relative markdown links to full URLs,
ensuring all links are web-compliant before the data is cached.

Usage:
    python document-loaders/resolve_document_links.py
    python document-loaders/resolve_document_links.py --input data/responses.json --output data/responses_resolved.json
"""

import json
import re
import sys
import logging
from pathlib import Path
from typing import Dict, Tuple
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class LinkResolution:
    """Track a link resolution."""

    original: str
    resolved: str
    type: str  # 'relative', 'anchor', 'invalid', 'valid'
    source_question: str


class DocumentLinkResolver:
    """Resolve relative document links to absolute URLs."""

    # Base URLs for different documentation sources
    BASE_URLS = {
        "milvus": "https://milvus.io/docs",
        "local": "file:///docs",  # For local file references
    }

    # Mapping of relative paths to full URLs
    LINK_MAPPINGS = {
        "embeddings.md": "https://milvus.io/docs/embeddings.md",
        "index.md": "https://milvus.io/docs/index.md",
        "manage-collections.md": "https://milvus.io/docs/manage-collections.md",
    }

    def __init__(self, base_url: str = "https://milvus.io/docs"):
        """Initialize resolver.

        Args:
            base_url: Base URL for resolving relative links
        """
        self.base_url = base_url
        self.resolutions = []

    def resolve_markdown_link(
        self, text: str, url: str, question: str = ""
    ) -> Tuple[str, str, str]:
        """Resolve a single markdown link.

        Args:
            text: Link display text
            url: Link URL (may be relative)
            question: Source question (for logging)

        Returns:
            Tuple of (original_url, resolved_url, resolution_type)
        """
        # Already absolute URL
        if url.startswith("http://") or url.startswith("https://"):
            return url, url, "valid"

        # Anchor-only link (no file referenced)
        if url.startswith("#"):
            return url, url, "anchor"

        # Check explicit mapping first
        if url in self.LINK_MAPPINGS:
            resolved = self.LINK_MAPPINGS[url]
            self.resolutions.append(
                LinkResolution(
                    original=url, resolved=resolved, type="mapped", source_question=question
                )
            )
            return url, resolved, "mapped"

        # Relative markdown file: filename.md → base_url/filename.md
        if url.endswith(".md") and not url.startswith("/"):
            resolved = f"{self.base_url}/{url}"
            self.resolutions.append(
                LinkResolution(
                    original=url, resolved=resolved, type="relative", source_question=question
                )
            )
            return url, resolved, "relative"

        # Unknown format
        logger.warning(f"Cannot resolve link: '{url}' in question: {question}")
        return url, url, "invalid"

    def resolve_text(self, text: str, source_context: str = "") -> str:
        """Resolve all markdown links in text.

        Args:
            text: Text containing markdown links
            source_context: Context for logging (question or description)

        Returns:
            Text with resolved links
        """
        if not text:
            return text

        def replace_link(match):
            link_text = match.group(1)
            link_url = match.group(2)
            original_url, resolved_url, resolution_type = self.resolve_markdown_link(
                link_text, link_url, source_context
            )
            return f"[{link_text}]({resolved_url})"

        # Find and replace all markdown links: [text](url)
        resolved_text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", replace_link, text)

        return resolved_text

    def process_responses_file(self, input_path: str, output_path: str = None) -> Dict:
        """Process responses.json file to resolve all relative links.

        Args:
            input_path: Path to input responses.json
            output_path: Path to output file (defaults to input_path)

        Returns:
            Processed data structure
        """
        if output_path is None:
            output_path = input_path

        # Load input file
        input_path = Path(input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        logger.info(f"Loading responses from: {input_path}")
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Process each Q&A pair
        qa_pairs = data.get("qa_pairs", [])
        logger.info(f"Processing {len(qa_pairs)} Q&A pairs...")

        resolved_count = 0
        for qa in qa_pairs:
            original_response = qa.get("answer", "")
            question = qa.get("question", "")

            # Resolve links in response
            resolved_response = self.resolve_text(original_response, question)

            if resolved_response != original_response:
                qa["answer"] = resolved_response
                resolved_count += 1

        # Log summary
        logger.info(f"✓ Resolved {len(self.resolutions)} links across {resolved_count} Q&A pairs")

        # Print resolution summary
        if self.resolutions:
            logger.info("\nLink Resolution Summary:")
            resolution_types = {}
            for res in self.resolutions:
                resolution_types[res.type] = resolution_types.get(res.type, 0) + 1
                logger.debug(f"  {res.type}: {res.original} → {res.resolved}")

            for res_type, count in resolution_types.items():
                logger.info(f"  • {res_type}: {count}")

        # Save output
        output_path = Path(output_path)
        logger.info(f"Saving resolved answers to: {output_path}")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("✓ Processing complete")
        return data

    def get_resolution_report(self) -> str:
        """Get a detailed report of all resolutions made.

        Returns:
            Formatted report string
        """
        if not self.resolutions:
            return "No links resolved"

        report = ["Link Resolution Report", "=" * 60]

        by_type = {}
        for res in self.resolutions:
            if res.type not in by_type:
                by_type[res.type] = []
            by_type[res.type].append(res)

        for res_type, resolutions in sorted(by_type.items()):
            report.append(f"\n{res_type.upper()} ({len(resolutions)} links):")
            for res in resolutions:
                report.append(f"  Original: {res.original}")
                report.append(f"  Resolved: {res.resolved}")
                report.append(f"  Question: {res.source_question[:50]}...")
                report.append("")

        return "\n".join(report)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Resolve relative document links in responses.json"
    )
    parser.add_argument(
        "--input",
        default="data/responses.json",
        help="Input responses.json file (default: data/responses.json)",
    )
    parser.add_argument("--output", help="Output file (default: same as input)")
    parser.add_argument(
        "--base-url",
        default="https://milvus.io/docs",
        help="Base URL for relative link resolution (default: https://milvus.io/docs)",
    )
    parser.add_argument("--report", action="store_true", help="Print detailed resolution report")

    args = parser.parse_args()

    # Create resolver
    resolver = DocumentLinkResolver(base_url=args.base_url)

    # Process file
    try:
        resolver.process_responses_file(args.input, args.output or args.input)

        # Print report if requested
        if args.report:
            print("\n" + resolver.get_resolution_report())

        logger.info("\u2713 Successfully resolved document links")
        return 0

    except Exception as e:
        logger.error(f"Failed to process responses: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
