-- Do not delete!! --

- Twitter / X / Truth Social mit einbeziehen.
    - Möglichkeit zu haben Trend Setter welche gerade aktuell sind zu definieren in config file, welche dann analysiert weredn sollen (Trump, Musk etc.)

Sprint 3 mit aufnehmen:
- historical loader wird einmal manuell ausgeführt, dann soll immer automatisch nach gap prüfen (nur handesltage, WE nicht relevant). dann auffüllen

- Logging von Reuqests und Responses Falls du Roh-Responses dauerhaft sehen willst, wäre das eine kleine Änderung in src/utils.py (Debug-Logging des Response-Texts hinter einem Flag). Das ginge, wirkt aber erst ab dem nächsten Lauf — sag Bescheid, ob ich das für Plan 2 vormerken soll.

- Geschäftsberichte mit aufnehmen!


 Unzureichende Kontrollvariablen:
  - Keine Berücksichtigung von Marktweit-Bewegungen (β-Risiko, Marktrendite)
  - Keine Adjustierung für Branchensaisonen
  - Keine Analyse von Konkurrenznachrichten am gleichen Tag


Later:
- jetzt SQLite behalten, später DuckDB/DWH wenn nötig



Prompt:

so ungefähr sollte der prompt aussehen.
Du bist ein erfahrener Aktien- und Finanzmarktexperte mit Spezialisierung auf kurzfristige (intraday bis 48h) Kursprognosen für den S&P 500.
AUFGABE:
Erstelle eine strukturierte Analyse für den heutigen Handelstag. Ziel ist ein nachvollziehbares, mehrdimensionales Ranking der Aktien mit der höchsten Wahrscheinlichkeit zu steigen bzw. zu fallen.
BERÜCKSICHTIGE FOLGENDE DIMENSIONEN JE AKTIE:
1. Marktumfeld / Makro – Fed-Politik, Zinsen, Yields, Inflation, allgemeine Marktstimmung
2. Geopolitik / Policy-Risiko – Konflikte, Sanktionen, Handelspolitik, regulatorische Ereignisse
3. Sektorentwicklung – Sektor-Momentum als Filter (z. B. wenn ein ganzer Sektor fällt, Vorsicht bei Long-Picks in diesem Sektor)
4. Momentum / technische Indikatoren – RSI, ATR, Volumen, überkauft/überverkauft, Trendstruktur
5. Fundamentaldaten – Bewertung (P/E etc.), Earnings-Beats/Misses, Guidance, Analysten-Kursziele
6. Unternehmensqualität – Wettbewerbsposition, Bilanzqualität, strukturelle Stärke/Schwäche
7. Katalysatoren – Earnings-Termine, Index-Aufnahmen/-Ausschlüsse, Produktankündigungen, News-Flow
8. Risiko – Volatilität, Konzentrationsrisiko, Event-Risiko (z. B. bevorstehende Zahlen)
VORGEHEN:
- Recherchiere zunächst die aktuelle Marktlage (letzter Handelstag, Pre-Market/Futures, wichtige News der letzten 24–48h)
- Beziehe explizit ein, was am/an den vorherigen Handelstag(en) auffällig war (z. B. große Sektor-Bewegungen, Ausreißer, Makro-Events)
- Bewerte pro Aktie mindestens zwei der obigen Dimensionen mit konkreter Evidenz (keine reinen Vermutungen)
OUTPUT-FORMAT:
1. Kurzer Marktüberblick (3–5 Sätze): Was ist gestern/heute Nacht passiert, was ist das dominante Marktthema heute
2. Top 10 Ranking als Tabelle:
   | # | Ticker | Richtung (📈/📉) | Erwartete Bewegung (%) | Konfidenz (⭐1-5) | Kernbegründung |
   - 5 Kandidaten mit höchster Steigungswahrscheinlichkeit
   - 5 Kandidaten mit höchster Fallwahrscheinlichkeit
3. Für jeden der 10 Ticker: 1–2 Sätze Begründung, wichtigstes Risiko, auffälliges Signal
4. Abschließende Einordnung: Gibt es ein gespaltenes Bild (z. B. technischer Bounce vs. fundamentale Schwäche)? Welche Wildcards (z. B. Fed-Kommentare, geopolitische Eskalation) könnten das Bild kurzfristig kippen?
WICHTIG:
- Nutze aktuelle, verifizierte Daten (Websuche), keine veralteten Annahmen
- Trenne klar zwischen kurzfristigem technischem Rebound und struktureller/fundamentaler Bewegung
- Wenn ein ganzer Sektor am Vortag stark gefallen/gestiegen ist, weise explizit darauf hin und berücksichtige es als Filter für die Einzelwerte
- Keine reine Wiederholung von Kursbewegungen ohne Kausalzusammenhang — jede Einschätzung braucht eine nachvollziehbare Begründung


dieser dann in Kombination mit den technischen Indikatoren etc.
