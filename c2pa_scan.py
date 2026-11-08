#!/usr/bin/env python3
"""
c2pa_scan.py - szybka diagnostyka pochodzenia obrazu.

Co robi:
  1) czyta strukturę pliku (JPEG segmenty / PNG chunki),
  2) wyciąga metadane: EXIF/XMP/IPTC oraz manifesty C2PA (Content Credentials),
  3) klasyfikuje: wygenerowane przez AI / edytowane / brak śladów,
  4) wypisuje generator, akcję, typ źródła i datę.

Użycie:
    python c2pa_scan.py obraz.jpg [ obraz2.png ... ]
    python c2pa_scan.py katalog/            # przeskanuje *.jpg *.jpeg *.png *.webp

Dlaczego to działa:
  Generatory (OpenAI, Google, Azure) i coraz więcej edytorów dopisują do pliku
  podpisany manifest C2PA. W JPEG leży on w segmencie APP11 (0xFFEB) jako
  kontener JUMBF ("jumb"), w PNG w chunku caBX / iTXt z XMP. Manifest zawiera
  m.in.:
    - c2pa.actions.v2 / action = c2pa.created  -> asset POWSTAŁ w tym narzędziu
    - digitalSourceType = .../trainedAlgorithmicMedia -> treść z modelu AI
    - claim_generator / softwareAgent = "gpt-image", "Azure OpenAI ImageGen"
    - certyfikat podpisującego: "Google LLC", "OpenAI", ...
    - znaczniki czasu (kiedy wygenerowano)
  Brak manifestu NIE dowodzi autentyczności - metadane można usunąć.
"""
import sys
import os
import glob
import re
import struct
import zlib

AI_MARKERS = [
    b"trainedAlgorithmicMedia", b"compositeWithTrainedAlgorithmicMedia",
    b"Made with Google AI", b"Generated with AI", b"SynthID",
    b"imagen", b"gpt-image", b"Azure OpenAI ImageGen", b"dall-e", b"DALL",
    b"firefly", b"Midjourney", b"stable diffusion",
]
GENERATORS = [b"gpt-image", b"Azure OpenAI ImageGen", b"Google", b"OpenAI",
              b"Adobe Firefly", b"Midjourney", b"Microsoft Designer"]


def png_chunks(b):
    out = []
    i = 8
    while i < len(b) - 8:
        ln = struct.unpack(">I", b[i:i + 4])[0]
        typ = b[i + 4:i + 8].decode("latin1")
        data = b[i + 8:i + 8 + ln]
        out.append((typ, ln, data))
        i += 12 + ln
        if typ == "IEND":
            break
    return out


def jpeg_segments(b):
    out = []
    i = 2
    while i < len(b) - 1:
        if b[i] != 0xFF:
            break
        m = b[i + 1]
        if m == 0xD8:
            i += 2
            continue
        if m == 0xDA:
            out.append(("SOS", i, b""))
            break
        ln = struct.unpack(">H", b[i + 2:i + 4])[0]
        out.append((f"FF{m:02X}", i, b[i + 4:i + 2 + ln]))
        i += 2 + ln
    return out


def printable(b, minlen=6):
    return [s.decode("latin1") for s in re.findall(rb"[\x20-\x7e]{%d,}" % minlen, b)]


def classify(blob):
    hits = [m.decode() for m in AI_MARKERS if m.lower() in blob.lower()]
    gen = [g.decode() for g in GENERATORS if g.lower() in blob.lower()]
    created = b"c2pa.created" in blob
    converted = b"c2pa.converted" in blob
    edited = b"c2pa.edited" in blob
    # digitalSourceType rozstrzyga co do istoty: composite zawiera w sobie
    # substring "trainedAlgorithmicMedia", wiec sprawdzamy composite pierwszy.
    dsc = []
    if b"compositeWithTrainedAlgorithmicMedia" in blob:
        dsc.append("compositeWithTrainedAlgorithmicMedia")
    elif b"trainedAlgorithmicMedia" in blob:
        dsc.append("trainedAlgorithmicMedia")
    if b"digitalCapture" in blob:
        dsc.append("digitalCapture")
    return hits, gen, created, converted, edited, dsc


def report(path):
    b = open(path, "rb").read()
    print("=" * 70)
    print(f"PLIK: {os.path.basename(path)}  ({len(b)} B)")
    if b[:2] == b"\xff\xd8":
        kind = "JPEG"
        segs = jpeg_segments(b)
        containers = [(t, i, d) for t, i, d in segs if t in ("FFEB", "FFE1", "FFED", "FFFE")]
        print("  format: JPEG; segmenty:", ", ".join(f"{t}({len(d)})" for t, i, d in segs[:10]))
    elif b[:8] == b"\x89PNG\r\n\x1a\n":
        kind = "PNG"
        chunks = png_chunks(b)
        containers = [(t, 0, d) for t, l, d in chunks
                      if t in ("iTXt", "zTXt", "tEXt", "eXIf", "caBX", "iDOT")]
        print("  format: PNG; chunki:", ", ".join(t for t, l, d in chunks))
    else:
        print("  format: inny/nieobsługiwany")
        return

    meta_blob = b"".join(d for _, _, d in containers)
    hits, gen, created, converted, edited, dsc = classify(meta_blob)

    print("  C2PA/JUMBF obecne:", "tak" if b"jumb" in b else "NIE")
    print("  markery AI:", hits or "brak")
    print("  generator/podpisujący:", sorted(set(gen)) or "brak")
    print("  akcje:", ", ".join(x for x, f in
                                (("c2pa.created", created), ("c2pa.converted", converted),
                                 ("c2pa.edited", edited)) if f) or "brak")
    print("  typ źródła (digitalSourceType):", ", ".join(dsc) or "brak")

    # daty i identyfikatory
    dates = sorted(set(re.findall(r"20\d\d-\d\d-\d\dT[\d:.]+", meta_blob.decode("latin1", "ignore"))))
    if dates:
        print("  znaczniki czasu:", dates[:4])
    urns = sorted(set(re.findall(r"urn:c2pa:[0-9a-f-]+", b.decode("latin1", "ignore"))))
    if urns:
        print("  manifest:", urns[0])

    # werdykt: najpierw digitalSourceType (rozstrzygajace), potem heurystyka.
    # Uwaga: nazwa firmy w certyfikacie ("Google LLC") to nie dowod generowania -
    # zwykle zdjecie z aparatu tez moze miec c2pa.created i podpis Google.
    if "compositeWithTrainedAlgorithmicMedia" in dsc:
        print("  >>> WERDYKT: edytowane z udziałem AI (compositeWithTrainedAlgorithmicMedia)")
    elif "trainedAlgorithmicMedia" in dsc:
        print("  >>> WERDYKT: ślady generowania AI / treść syntetyczna")
    elif "digitalCapture" in dsc:
        print("  >>> WERDYKT: zdjęcie z aparatu (digitalCapture)")
    elif created and gen:
        print("  >>> WERDYKT: podpisany manifest od narzędzia:",
              ", ".join(sorted(set(gen)) or ["?"]), "- sprawdź digitalSourceType/akcje")
    elif created or edited:
        print("  >>> WERDYKT: podpisany manifest edycji (sprawdź akcje)")
    else:
        print("  >>> WERDYKT: brak manifestu C2PA - NIE rozstrzyga; sprawdź XMP/IPTC/EXIF i wygląd")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    paths = []
    for a in args:
        if os.path.isdir(a):
            for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
                paths += sorted(glob.glob(os.path.join(a, ext)))
        else:
            paths.append(a)
    for p in paths:
        try:
            report(p)
        except Exception as e:
            print("BŁĄD", p, e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
