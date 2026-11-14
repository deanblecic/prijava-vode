# Fotografije vodomjera za provjeru prepoznavanja

Stvarne fotografije sa zgrade, s točnim stanjem u imenu datoteke (`<vodomjer>-<stanje bez zareza>`).
`ocr-retci.tsv` sadrži za svaku fotografiju točno stanje, prethodno stanje i retke teksta koje OCR
s nje pročita; test `CitacBrojilaTest.zbirkaFotografija` na njima mjeri točnost.

Retci su dobiveni OCR-om na računalu (RapidOCR), ne ML Kitom s mobitela, pa su samo približni
onome što aplikacija vidi. Parovi istog vodomjera (isti serijski broj) koriste stvarno ranije
stanje kao prethodno; ostale fotografije prethodno stanje 6 m³ manje od točnog.

Rezultat na ovih 20 fotografija (prvi ponuđeni broj, s prethodnim stanjem):

| | točno | krivo ponuđeno | ništa (suvlasnik upisuje) |
|---|---|---|---|
| prije (do 14. 11. 2026.) | 7 | 13 | 0 |
| sada | 8 | 2 | 10 |

Na 10 fotografija OCR uopće ne pročita brojilo (mutno, nakošeno, odsjaj, kazaljke); tada je
bolje ne ponuditi ništa nego uvjerljiv krivi broj. Dvije preostale pogreške (`elster-1510133`,
`wehrle-314704`) su fotografije na kojima je OCR ispustio ili dodao znamenku.

## Cijeli broj (m³) uz glasanje

Aplikacija nudi samo cijeli broj prije zareza i čita šest inačica slike (cijela, izrezi 80 % i 60 %,
izrez s kontrastom, izrez zakrenut ±10°), pa bira broj koji se najčešće pročita. Retci za svaku
inačicu su u `ocr-inacice.tsv`; test `zbirkaCijeliBrojGlasanjem`.

| cijeli broj, s prethodnim stanjem | točno | krivo | ništa |
|---|---|---|---|
| jedno čitanje | 9 | 1 | 10 |
| glasanje 6 inačica | 11 | 4 | 5 |

