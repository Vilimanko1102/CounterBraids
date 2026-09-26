# Counter Braids — implementacija i verifikacija

Implementacija algoritma iz:

> Y. Lu, A. Montanari, B. Prabhakar, S. Dharmapurikar, A. Kabbani,
> **"Counter Braids: A Novel Counter Architecture for Per-Flow Measurement"**,
> ACM SIGMETRICS 2008. (`08counterbraidsCONF.pdf` u ovom projektu)

Counter Braids je struktura brojača za merenje mrežnog saobraćaja po flow-u
("per-flow measurement") koja **kompresuje dok broji** — tačno rekonstruiše
veličinu svakog flow-a koristeći znatno manje memorije nego kad bi se držao
jedan (npr. 16-bitni) brojač po flow-u.

## Sadržaj projekta

| Fajl | Šta je |
|---|---|
| `prototype.py` | **Jedina skripta u projektu.** Kompletna implementacija: arhitektura, message-passing dekoder, density evolution prag, pravila dizajna iz rada, i demo koji sve pokreće. |
| `08counterbraidsCONF.pdf` | Originalni rad. |
| `counter_braids_graph.png` | Dijagram bipartitnog grafa za toy primer iz `prototype.py` (flow1=3, flow2=5, flow3=2) — prikazuje koji flow hešuje na koji L1 brojač, i koji L1 brojač carry-uje na koji L2 brojač. |
| `full_step1_initial.png` ... `full_step5_final.png` | Vizuelni korak-po-korak prikaz **dekodiranja** istog toy primera: od početnog stanja, preko dekodiranja L2 sloja (overflow brojevi), foldinga (sklapanje pune L1 vrednosti), do message-passing "raspetljavanja" na L1 sloju i konačnog tačnog rezultata. |

## Šta `prototype.py` implementira

- **`k_hash_edges`** — k pseudo-slučajnih heš funkcija, flow↔brojač i brojač↔brojač mapiranje (Sekcija 3.2 rada).
- **`density_evolution_threshold`** — tačna implementacija Theorem 2 (Sekcija 5): računa β* (minimalan broj brojača po flow-u potreban da dekoder konvergira ka nultoj grešci), preko density evolution rekurzije `f(γ,x)` i praga `γ*`.
- **`CounterBraids`** klasa:
  - `encode()` — dvoslojno kodiranje sa status bitovima (Exhibit 1): svaki paket uvećava k brojača, overflow se carry-uje u L2 sloj.
  - `message_passing_decode()` — tačan min/max message-passing dekoder (Exhibit 2), ne naivni "peeling".
  - `decode()` — dvoslojno dekodiranje (Exhibit 3): prvo L2 (overflow brojevi), zatim se ti brojevi "fold-uju" nazad u L1, pa se dekoduju stvarne veličine flow-ova.
- **`design_counter_braids`** — pravila dizajna iz Sekcije 6: iz α (heavy-tail eksponent) i pretpostavljene maksimalne veličine flow-a, računa β*, m1, m2, d1, d2 tačno po receptu iz rada, uz malu sigurnosnu marginu (rad sam napominje da je β* tačan samo asimptotski — "1 bit iznad praga daje <1/1000 grešaka" na konačnom n).
- **`run_toy_example()`** — verbose ispis kodiranja i dekodiranja na malom primeru (3 flow-a), koji je i osnova za priložene dijagrame.
- **`main()`** — pokreće toy primer, zatim dizajnira i testira Counter Braids na n=1000 flow-ova generisanih iz power-law raspodele (P(f>x)=x⁻ᵅ, tačno raspodela koju rad koristi za sopstvenu evaluaciju), i na kraju proverava robusnost preko 30 nezavisnih uzoraka saobraćaja.

## Rezultat

```
DESIGN
epsilon = P(f>1)     = 0.354
beta*                = 0.709  (density evolution prag)
provisioned beta1    = 0.850  (beta* x 1.20 sigurnosna margina)
m1 = 851, m2 = 86, d1 = 5, d2 = 13, k = 3

RESULT
Perr (greška rekonstrukcije)          = 0.00%
r (memorija po flow-u)                = 6.22 bita
ušteda memorije vs. naivnih 16 bita   = 61.1%

ROBUSTNESS CHECK (30 nezavisnih uzoraka)
failures: 0/30
```

Preciznost nije "skoro tačna" — dekoder ili **tačno zna** vrednost flow-a ili
**zna da ne zna** (kad se gornja i donja granica njegovih poruka ne poklope).
Nema tihih, neotkrivenih grešaka. To je posledica toga što je message-passing
dekoder matematički dokazan (Lemma 1-2 u radu) da sendvičuje pravu vrednost
odozgo i odozdo — ako se sendvič zatvori, vrednost je nužno tačna.

## Toy primer i dijagrami

`run_toy_example()` koristi tri flow-a (`flow1=3, flow2=5, flow3=2`) i
namerno mali broj brojača (m1=4, m2=3, d1=2 → overflow na 4), tako da:

- **overflow mehanizam** se vidi u akciji (3 od 4 L1 brojača overflow-uju),
- **pravo iterativno "raspetljavanje"** message-passing algoritma je
  vidljivo: `flow3` nema nijedan privatni brojač (oba njegova brojača dele
  flow1 i flow2), pa prva iteracija daje pogrešnu procenu (Count-Min stil,
  gornja granica preko deljenog brojača), a tek druga iteracija — pošto su
  flow1 i flow2 već razrešeni i njihov doprinos oduzet sa deljenih brojača —
  daje tačnu vrednost za flow3.

Priloženi dijagrami (`counter_braids_graph.png` i `full_step*.png`) prikazuju
tačno ovaj tok:

1. **`counter_braids_graph.png`** — statična slika strukture: koji flow ide
   na koji L1 brojač (plave→zelene strelice), i koji L1 brojač carry-uje na
   koji L2 brojač (zelene isprekidane strelice).
2. **`full_step1_initial.png`** — početno stanje pre dekodiranja: brojači su
   poznati, flow veličine nepoznate.
3. **`full_step2_l2_decoding.png`** — dekodiranje L2 sloja: iz L2 vrednosti
   (1, 2, 3) se message-passing-om izvlači koliko je puta svaki L1 brojač
   overflow-ovao.
4. **`full_step3_l1_reconstruction.png`** — folding: rezidual + (overflow
   broj × 4) daje punu, korigovanu vrednost svakog L1 brojača.
5. **`full_step4_l1_decoding.png`**, **`full_step4a_initial_incorrect.png`**,
   **`full_step4b_aggregation.png`**, **`full_step4b_peeling_corrected.png`**
   — samo srce algoritma: prva iteracija (MIN) daje `flow3` pogrešnu
   procenu zbog kolizije na deljenom brojaču; agregacija poruka i druga
   iteracija (MAX/peeling) tu procenu ispravlja na tačnu vrednost, pošto se
   doprinos flow1 i flow2 prvo "otpetlja" i oduzme.
6. **`full_step5_final.png`** — svi tokovi tačno rekonstruisani (3, 5, 2).

## Kako pokrenuti

```bash
python3 prototype.py
```

Nema spoljnih zavisnosti osim standardne biblioteke Pythona (`hashlib`,
`math`, `random`).

## Ključne teorijske tačke iz rada koje implementacija sledi

- **β* (Theorem 2)** je prag broja brojača po flow-u iznad kojeg message
  passing dekoder konvergira ka tačnoj rekonstrukciji; ispod praga, dokazano
  postoji pozitivan procenat flow-ova koji se ne mogu tačno rekonstruisati.
- **Status biti** (Sekcija 3.1) smanjuju potreban broj L2 brojača — L2 sloj
  tada dekoduje samo overflow-ovane L1 brojače (minimalna vrednost 1), ne sve.
- **Pravila palca** (Sekcija 6): dvoslojni CB, status biti, k=3 heš funkcije
  po sloju; d1=5 bita za α≥1.1, d1=8 bita za teži rep (α<1.1); m2=0.1·β*·n.
- Na konačnom n, tačno na pragu β* ponašanje je fazni prelaz (ili čisto
  konvergira ili skoro uopšte ne) — otuda mala sigurnosna margina u
  `design_counter_braids()`.
