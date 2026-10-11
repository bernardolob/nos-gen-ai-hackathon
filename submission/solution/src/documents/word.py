"""DOCX package editing without rebuilding paragraphs, runs or drawings."""

import copy
import posixpath
import zipfile
from pathlib import PurePosixPath

from lxml import etree as ET

from .common import DocumentAdapter, DocumentError, mapped_lines

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W}
MAX_EXPANDED_BYTES = 100_000_000
MAX_PARTS = 2048
STORIES = ("document", "header", "footer", "footnotes", "endnotes")


def xml(data):
    root = ET.fromstring(data, ET.XMLParser(
        resolve_entities=False, no_network=True, load_dtd=False))
    if root.getroottree().docinfo.doctype:
        raise DocumentError("XML com DTD não suportado.")
    return root


def encode(root):
    return ET.tostring(root, encoding="UTF-8", xml_declaration=True)


def target_part(owner, target):
    if target.startswith("/"):
        path = posixpath.normpath(target.lstrip("/"))
    else:
        path = posixpath.normpath(posixpath.join(
            posixpath.dirname(owner), target))
    if path.startswith("../") or path in {".", ".."}:
        raise DocumentError("Relação de documento inválida.")
    return path


def relationship_owner(name):
    if name == "_rels/.rels":
        return ""
    directory, filename = name.rsplit("/_rels/", 1)
    return directory + "/" + filename[:-5]


def sanitize_tree(root):
    """Accept the displayed revision, remove history and field source text."""
    deleted = {"del", "moveFrom", "commentRangeStart", "commentRangeEnd",
               "commentReference", "instrText", "delInstrText", "fldChar",
               "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart",
               "moveToRangeEnd", "docVars"}
    wrappers = {"ins", "moveTo", "fldSimple", "hyperlink"}
    for node in list(root.iter()):
        name = ET.QName(node)
        if name.namespace != W or node.getparent() is None:
            continue
        local = name.localname
        if local in deleted or local.endswith("PrChange"):
            node.getparent().remove(node)
        elif local in wrappers:
            parent = node.getparent()
            index = parent.index(node)
            for child in list(node):
                parent.insert(index, child)
                index += 1
            parent.remove(node)
    for node in root.iter():
        if ET.QName(node).localname == "docPr":
            node.set("name", "Image")
        for attribute in list(node.attrib):
            local = ET.QName(attribute).localname
            if local.startswith("rsid") or local in {"descr", "title"}:
                del node.attrib[attribute]


class WordDocument(DocumentAdapter):
    format = "docx"

    def __init__(self, path, folder):
        super().__init__(path, folder)
        with zipfile.ZipFile(path) as package:
            parts = package.infolist()
            if (len(parts) > MAX_PARTS or
                    sum(p.file_size for p in parts) > MAX_EXPANDED_BYTES):
                raise DocumentError("O conteúdo Word é demasiado grande.")
            names = [p.filename for p in parts]
            if len(names) != len(set(names)):
                raise DocumentError("O documento tem partes duplicadas.")
            for name in names:
                if ("\\" in name or PurePosixPath(name).is_absolute() or
                        ".." in PurePosixPath(name).parts):
                    raise DocumentError("Parte de documento inválida.")
            self.parts = {p.filename: package.read(p) for p in parts
                          if not p.is_dir()}
        if ("word/document.xml" not in self.parts or
                "[Content_Types].xml" not in self.parts):
            raise DocumentError("Documento Word .docx inválido.")
        if any(name.startswith(("word/embeddings/", "customXml/"))
               for name in self.parts):
            raise DocumentError(
                "Objetos incorporados ou dados XML externos não suportados.")
        self.trees = {}
        for name, data in self.parts.items():
            if name.endswith((".xml", ".rels")):
                root = xml(data)
                if name.startswith("word/"):
                    sanitize_tree(root)
                self.trees[name] = root
        types = self.trees["[Content_Types].xml"]
        if any("macroEnabled" in node.get("ContentType", "")
               for node in types):
            raise DocumentError("Documentos com macros não suportados.")
        self._inventory()
        self._extract()
        if not self.lines and not self.images:
            raise DocumentError("O documento não tem texto nem imagens.")

    def _inventory(self):
        for name, root in self.trees.items():
            if not name.endswith(".rels"):
                continue
            owner = relationship_owner(name)
            if "comments" in owner:
                continue
            for relation in root:
                kind = relation.get("Type", "").rsplit("/", 1)[-1]
                if kind in {"aFChunk", "oleObject", "package"}:
                    raise DocumentError("Objeto Word não suportado.")
                if kind != "image":
                    continue
                if relation.get("TargetMode") == "External":
                    raise DocumentError("Imagens externas não suportadas.")
                target = target_part(owner, relation.get("Target", ""))
                if target not in self.parts:
                    raise DocumentError("Imagem incorporada em falta.")
                owner_tree = self.trees.get(owner)
                if owner_tree is None:
                    raise DocumentError("Parte de imagem não suportada.")
                rid = relation.get("Id")
                placements = [node for node in owner_tree.iter()
                              if rid in (node.get("{%s}embed" % R),
                                         node.get("{%s}id" % R),
                                         node.get("{urn:schemas-microsoft-com:"
                                                  "office:office}relid"))]
                # Alternate SVG/bitmap representations must all be processed;
                # unsupported encodings fail instead of retaining a fallback.
                for index, _ in enumerate(placements):
                    label = PurePosixPath(owner).stem.replace(
                        "document", "Body")
                    self.add_image(self.parts[target], {
                        "part": target, "owner": owner,
                        "label": "%s · image %d" % (label, index + 1),
                    })

    def _extract(self):
        self.nodes = []
        raw, references = [], []
        names = sorted(name for name in self.trees if name.startswith("word/")
                       and name.endswith(".xml") and
                       PurePosixPath(name).stem.startswith(STORIES))
        for name in names:
            for paragraph in self.trees[name].iter("{%s}p" % W):
                for node in paragraph.iter():
                    # Text boxes have nested paragraphs; don't read them twice.
                    closest = next((ancestor for ancestor in
                                    node.iterancestors()
                                    if ancestor.tag == "{%s}p" % W), None)
                    if closest is not paragraph:
                        continue
                    if node.tag == "{%s}t" % W:
                        index = len(self.nodes)
                        self.nodes.append((name, node))
                        text = node.text or ""
                        raw.append(text)
                        references.extend([(index, offset)
                                           for offset in range(len(text))])
                    elif node.tag == "{%s}tab" % W:
                        raw.append("\t")
                        references.append(None)
                    elif node.tag in {"{%s}br" % W, "{%s}cr" % W}:
                        raw.append("\n")
                        references.append(None)
                raw.append("\n")
                references.append(None)
        self.lines, self.maps = mapped_lines("".join(raw), references)

    def render(self, output, edits, regions):
        # Work on a copy: feedback/export retries always start from originals.
        trees = {name: copy.deepcopy(root)
                 for name, root in self.trees.items()}
        node_copies = {}
        for index, (name, node) in enumerate(self.nodes):
            xpath = node.getroottree().getpath(node)
            node_copies[index] = trees[name].xpath(
                xpath, namespaces={k: v for k, v in
                                   node.nsmap.items() if k})[0]
        for edit in reversed(edits):
            refs = [ref for group in self.maps[edit["line"] - 1][
                edit["start"]:edit["end"]] for ref in group if ref is not None]
            if not refs:
                raise DocumentError(
                    "Não foi possível localizar uma máscara.")
            grouped = {}
            for index, offset in refs:
                grouped.setdefault(index, set()).add(offset)
            first_index, first_offset = refs[0]
            for index, offsets in grouped.items():
                node = node_copies[index]
                text = node.text or ""
                node.text = "".join(char for offset, char in enumerate(text)
                                    if offset not in offsets)
                node.set("{http://www.w3.org/XML/1998/namespace}space",
                         "preserve")
            first = node_copies[first_index]
            text = first.text or ""
            first.text = (text[:first_offset] + edit["replacement"] +
                          text[first_offset:])

        data = dict(self.parts)
        generated = self.redacted_images(regions)
        replacements = {}
        for image in self.images:
            target = "word/media/censored-%s.png" % image.id
            data[target] = generated[image.id]
            for placement in image.placements:
                replacements[placement["part"]] = target
        generated_parts = set(replacements.values())
        removed = {name for name in data if name.startswith((
            "docProps/", "word/comments", "word/_rels/comments",
            "_xmlsignatures/", "word/media/")) and name not in generated_parts}
        for name, root in trees.items():
            if name.endswith(".rels"):
                owner = relationship_owner(name)
                for relation in list(root):
                    if relation.get("Type", "").endswith("/hyperlink"):
                        root.remove(relation)
                        continue
                    if relation.get("TargetMode") == "External":
                        continue
                    target = target_part(owner, relation.get("Target", ""))
                    if target in replacements:
                        relation.set("Target", posixpath.relpath(
                            replacements[target],
                            posixpath.dirname(owner) or "."))
                    elif target in removed:
                        root.remove(relation)
        types = trees["[Content_Types].xml"]
        for node in list(types):
            if node.get("PartName", "").lstrip("/") in removed:
                types.remove(node)
        if not any(node.get("Extension") == "png" for node in types):
            ET.SubElement(types, "{%s}Default" % CT,
                          Extension="png", ContentType="image/png")
        for name, root in trees.items():
            if name not in removed:
                data[name] = encode(root)
        for name in removed:
            data.pop(name, None)
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as package:
            for name, content in data.items():
                package.writestr(name, content)
