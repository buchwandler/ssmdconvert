from __future__ import annotations

import posixpath
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from ..errors import SSMDConvertError
from ..models import Document, Section, SourceInfo
from .html import html_to_markdown


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _child_text(parent: ET.Element, local_name: str) -> str | None:
    for child in parent.iter():
        if _local(child.tag) == local_name and child.text and child.text.strip():
            return child.text.strip()
    return None


def _resolve(base: str, href: str) -> str:
    href = unquote(href.split("#", 1)[0])
    return posixpath.normpath(posixpath.join(posixpath.dirname(base), href))


class EpubAdapter:
    name = "epub"

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() == ".epub"

    def load(self, source: Path) -> Document:
        try:
            archive = zipfile.ZipFile(source)
        except zipfile.BadZipFile as exc:
            raise SSMDConvertError(f"Invalid EPUB ZIP container: {source}") from exc

        with archive:
            try:
                container = ET.fromstring(archive.read("META-INF/container.xml"))
            except (KeyError, ET.ParseError) as exc:
                raise SSMDConvertError("EPUB is missing a valid META-INF/container.xml") from exc
            rootfile = next(
                (
                    item.attrib.get("full-path")
                    for item in container.iter()
                    if _local(item.tag) == "rootfile" and item.attrib.get("full-path")
                ),
                None,
            )
            if not rootfile:
                raise SSMDConvertError("EPUB container does not declare a package document")
            try:
                package = ET.fromstring(archive.read(rootfile))
            except (KeyError, ET.ParseError) as exc:
                raise SSMDConvertError(f"EPUB package document is invalid: {rootfile}") from exc

            metadata_node = next((x for x in package if _local(x.tag) == "metadata"), None)
            manifest_node = next((x for x in package if _local(x.tag) == "manifest"), None)
            spine_node = next((x for x in package if _local(x.tag) == "spine"), None)
            if manifest_node is None or spine_node is None:
                raise SSMDConvertError("EPUB package requires manifest and spine")

            metadata: dict[str, str] = {}
            if metadata_node is not None:
                title = _child_text(metadata_node, "title")
                author = _child_text(metadata_node, "creator")
                language = _child_text(metadata_node, "language")
                if title:
                    metadata["title"] = title
                if author:
                    metadata["author"] = author
                if language:
                    metadata["language"] = language
            metadata.setdefault("title", source.stem)

            manifest: dict[str, tuple[str, str, str]] = {}
            for item in manifest_node:
                if _local(item.tag) != "item":
                    continue
                item_id = item.attrib.get("id")
                href = item.attrib.get("href")
                if item_id and href:
                    manifest[item_id] = (
                        href,
                        item.attrib.get("media-type", ""),
                        item.attrib.get("properties", ""),
                    )

            sections: list[Section] = []
            for index, itemref in enumerate(spine_node, start=1):
                if _local(itemref.tag) != "itemref":
                    continue
                idref = itemref.attrib.get("idref")
                if not idref or idref not in manifest:
                    continue
                href, media_type, _properties = manifest[idref]
                if media_type and media_type not in {"application/xhtml+xml", "text/html"}:
                    continue
                member = _resolve(rootfile, href)
                try:
                    raw = archive.read(member)
                except KeyError:
                    continue
                html = raw.decode("utf-8", errors="replace")
                markdown, page_title, first_heading = html_to_markdown(html)
                if not markdown.strip():
                    continue
                sections.append(
                    Section(
                        id=f"section-{index:04d}",
                        title=first_heading or page_title,
                        markdown=markdown,
                        source_ref=str(PurePosixPath(member)),
                    )
                )
            if not sections:
                raise SSMDConvertError("EPUB spine did not yield any readable text sections")
            return Document(
                source=SourceInfo(source, "epub", "application/epub+zip"),
                sections=sections,
                metadata=metadata,
            )
