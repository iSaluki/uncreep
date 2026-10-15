"""Minimal editor for Android binary XML (compiled AndroidManifest.xml).

Many large apps' resources cannot be recompiled with apktool/aapt2, so instead of
decoding and rebuilding the manifest, uncreep edits the compiled file in place.
Only two operations are needed:

* remove an element together with all of its children, and
* change the value of a boolean attribute that already exists (exported, enabled, a
  boolean <meta-data> value).

Removing elements only deletes XML node chunks; the string pool and the
resource-id map are left untouched (unused strings are harmless).
"""

import struct

RES_XML_TYPE = 0x0003
RES_STRING_POOL_TYPE = 0x0001
RES_XML_RESOURCE_MAP_TYPE = 0x0180
RES_XML_START_ELEMENT_TYPE = 0x0102
RES_XML_END_ELEMENT_TYPE = 0x0103

TYPE_STRING = 0x03
TYPE_INT_BOOLEAN = 0x12

ANDROID_NS = "http://schemas.android.com/apk/res/android"


class Attr:
    def __init__(self, doc, offset):
        self.doc = doc
        self.offset = offset  # absolute offset of the 20-byte attribute struct

    def _u32(self, i):
        return struct.unpack_from("<I", self.doc.data, self.offset + 4 * i)[0]

    @property
    def name(self):
        return self.doc.string(self._u32(1))

    @property
    def raw_value(self):
        idx = self._u32(2)
        return None if idx == 0xFFFFFFFF else self.doc.string(idx)

    @property
    def data_type(self):
        return self.doc.data[self.offset + 15]

    @property
    def data(self):
        return struct.unpack_from("<I", self.doc.data, self.offset + 16)[0]

    @property
    def value(self):
        if self.raw_value is not None:
            return self.raw_value
        if self.data_type == TYPE_STRING:
            return self.doc.string(self.data)
        if self.data_type == TYPE_INT_BOOLEAN:
            return self.data != 0
        return self.data

    def set_bool(self, value):
        if self.data_type != TYPE_INT_BOOLEAN:
            raise ValueError(f"attribute {self.name} is not a boolean")
        struct.pack_into("<I", self.doc.data, self.offset + 8, 0xFFFFFFFF)  # no raw string
        struct.pack_into("<I", self.doc.data, self.offset + 16, 0xFFFFFFFF if value else 0)


class Element:
    def __init__(self, doc, start, depth):
        self.doc = doc
        self.start = start  # offset of START_ELEMENT chunk
        self.end = None  # offset just past the matching END_ELEMENT chunk
        self.depth = depth
        self.children = []
        self.parent = None

    @property
    def tag(self):
        name_idx = struct.unpack_from("<I", self.doc.data, self.start + 20)[0]
        return self.doc.string(name_idx)

    @property
    def attrs(self):
        d = self.doc.data
        ext = self.start + 16
        attr_start, attr_size, attr_count = struct.unpack_from("<HHH", d, ext + 8)
        base = ext + attr_start
        return [Attr(self.doc, base + i * attr_size) for i in range(attr_count)]

    def attr(self, name):
        for a in self.attrs:
            if a.name == name:
                return a
        return None

    def get(self, name, default=None):
        a = self.attr(name)
        return default if a is None else a.value

    def iter(self, tag=None):
        for c in self.children:
            if tag is None or c.tag == tag:
                yield c
            yield from c.iter(tag)

    def __repr__(self):
        return f"<{self.tag} name={self.get('name')!r}>"


class AXML:
    def __init__(self, data: bytes):
        self.data = bytearray(data)
        self._removed = []  # list of (start, end) byte ranges to drop on save
        self._parse()

    # -- string pool -------------------------------------------------------
    def _parse_strings(self, off):
        d = self.data
        _, header_size, _ = struct.unpack_from("<HHI", d, off)
        count, _style_count, flags, strings_start, _ = struct.unpack_from("<IIIII", d, off + 8)
        utf8 = bool(flags & (1 << 8))
        offsets = struct.unpack_from(f"<{count}I", d, off + header_size)
        base = off + strings_start
        out = []
        for o in offsets:
            p = base + o
            if utf8:
                # utf-16 length (skip) then utf-8 byte length, each 1 or 2 bytes
                n = d[p]
                p += 2 if n & 0x80 else 1
                n = d[p]
                if n & 0x80:
                    n = ((n & 0x7F) << 8) | d[p + 1]
                    p += 2
                else:
                    p += 1
                out.append(bytes(d[p:p + n]).decode("utf-8", "replace"))
            else:
                n = struct.unpack_from("<H", d, p)[0]
                p += 2
                if n & 0x8000:
                    n = ((n & 0x7FFF) << 16) | struct.unpack_from("<H", d, p)[0]
                    p += 2
                out.append(bytes(d[p:p + 2 * n]).decode("utf-16-le", "replace"))
        self.strings = out

    def string(self, idx):
        if idx == 0xFFFFFFFF:
            return None
        return self.strings[idx]

    # -- tree --------------------------------------------------------------
    def _parse(self):
        d = self.data
        typ, header_size, size = struct.unpack_from("<HHI", d, 0)
        if typ != RES_XML_TYPE:
            raise ValueError("not a binary XML file")
        off = header_size
        stack = []
        self.root = None
        while off < size:
            ctype, chs, csize = struct.unpack_from("<HHI", d, off)
            if ctype == RES_STRING_POOL_TYPE:
                self._parse_strings(off)
            elif ctype == RES_XML_START_ELEMENT_TYPE:
                el = Element(self, off, len(stack))
                if stack:
                    el.parent = stack[-1]
                    stack[-1].children.append(el)
                elif self.root is None:
                    self.root = el
                stack.append(el)
            elif ctype == RES_XML_END_ELEMENT_TYPE:
                el = stack.pop()
                el.end = off + csize
            off += csize

    def remove(self, el: Element):
        if el.parent is not None and el in el.parent.children:
            el.parent.children.remove(el)
        self._removed.append((el.start, el.end))

    def to_bytes(self) -> bytes:
        out = bytearray()
        pos = 0
        for start, end in sorted(self._removed):
            if start < pos:  # nested inside an already removed range
                continue
            out += self.data[pos:start]
            pos = end
        out += self.data[pos:]
        struct.pack_into("<I", out, 4, len(out))
        return bytes(out)
