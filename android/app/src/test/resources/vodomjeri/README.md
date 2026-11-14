# Fotografije vodomjera za provjeru prepoznavanja

Stvarne fotografije na kojima je prepoznavanje griješilo, s točnim stanjem u imenu datoteke
(`<proizvođač>-<stanje bez zareza>.png`). Svaka ima pripadni test u `CitacBrojilaTest`.

| Datoteka | Točno stanje | Aplikacija je pročitala | Uzrok |
|---|---|---|---|
| `siemens-784806.png` | 784,806 | 780,180 | Natpis "PTB018" ispod brojila pretvoren u "P78018" |
