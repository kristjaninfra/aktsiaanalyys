# Aktsiaanalüüs

Kohalik rakendus: otsi aktsiat nime või tickeri järgi (pakub ise valikuid) → hind, graafik, tehniline ja fundamentaalne
analüüs, analüütikute sihid ning 4 / 12 / 26 nädala hinnang koos hinnavahemikuga. Vahelehel „📘 Õpetus“ on seletatud, kuidas iga rida lugeda.

## Käivitamine

Topeltklõpsa `start.command` (esimesel korral: paremklõps → Open). Avaneb
brauseris aadressil http://localhost:8501. Peatamiseks sulge Terminali aken.

## Failid

- `app.py` – kasutajaliides (Streamlit)
- `analysis.py` – andmed (Yahoo Finance), indikaatorid, skoorid, ajalooline test
- `requirements.txt` – Pythoni paketid

## Mudel lühidalt

- 4 gruppi: tehniline lühiajaline, tehniline ülevenitatus, fundamentaal, analüütikud
- Horisondi kaalud: lühike vaade → tehniline, pikk vaade → fundamentaal + analüütikud
- Hinna kaugus keskmistest ja momentum on **pööratud** (keskmisele naasmine):
  2022–2026 testis 20 USA suurettevõttel ennustas "trend üles = ost" vastupidiselt.
  Kontrolltest 20 teise aktsiaga: korrelatsioon positiivne 70–90% aktsiatest,
  ostusignaali järel keskmine tootlus 12 näd 6,6% (baas 4,2%), 26 näd 10,6% (baas 8,8%).
- Hinnavahemik = aktsia enda volatiilsus (80%), keskpunkti nihutab skoor.

Informatiivne tööriist, mitte investeerimisnõuanne.
