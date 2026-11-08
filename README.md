# c2pa_scan.py

Szybka diagnostyka pochodzenia obrazu (OSINT): czy plik nosi slady generowania AI,
edycji lub podpisanego manifestu C2PA (Content Credentials).

Czysty Python 3, bez zaleznosci.

## Co robi

1. Czyta strukture pliku: segmenty JPEG / chunki PNG.
2. Wyciaga metadane: EXIF / XMP / IPTC oraz manifesty C2PA (JPEG APP11 / JUMBF, PNG caBX, iTXt).
3. Klasyfikuje: wygenerowane przez AI / edytowane / brak sladow.
4. Wypisuje generator, akcje C2PA, typ zrodla i znaczniki czasu.

## Uzycie

```bash
python c2pa_scan.py obraz.jpg [ obraz2.png ... ]
python c2pa_scan.py katalog/   # przeskanuje *.jpg *.jpeg *.png *.webp
```

Przyklad wyjscia:

```
PLIK: obraz.png  (1234567 B)
  format: PNG; chunki: IHDR, pHYs, iTXt, caBX, IEND
  C2PA/JUMBF obecne: tak
  markery AI: ['trainedAlgorithmicMedia']
  generator/podpisujacy: ['gpt-image']
  akcje: c2pa.created
  znaczniki czasu: ['2025-11-07T12:34:56.789012']
  manifest: urn:c2pa:...
  >>> WERDYKT: slady generowania AI / tresc syntetyczna
```

## Jak wykrywa

Generatory (OpenAI, Google, Azure) i coraz wiecej edytorow dopisuja do pliku podpisany
manifest C2PA:

- `c2pa.actions.v2` / `action = c2pa.created` -> asset powstal w tym narzedziu,
- `digitalSourceType = .../trainedAlgorithmicMedia` -> tresc z modelu AI,
- `claim_generator` / `softwareAgent` = `gpt-image`, `Azure OpenAI ImageGen`, ...
- certyfikat podpisujacego: `Google LLC`, `OpenAI`, ...
- znaczniki czasu (kiedy wygenerowano).

## Ograniczenia

Brak manifestu NIE dowodzi autentycznosci - metadane mozna usunac lub nie dodawac
w ogole. Werdykt "brak sladow" nalezy traktowac jako "nieskonczone", nie "prawdziwe".

## Licencja

MIT
