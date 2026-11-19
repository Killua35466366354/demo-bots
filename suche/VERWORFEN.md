# Verworfen-Archiv

Verworfen heißt gemerkt, nicht vergessen (Kiron, 19.11.2026). Hier steht alles, was Kiron verworfen hat oder in einem
Test durchgefallen ist, mit Grund, damit derselbe Fehler nicht noch einmal passiert. Vor jeder neuen Idee hier und in
`suche/IDEEN.md` nachsehen. Für Gold gibt es dazu die Ideen- und Fehlerliste des Gold-Threads im Projektordner
(`gold-bot/lernjournal/ideen.jsonl`, `gold-bot/lernjournal/fehler.jsonl`).

Stand 2026-11-19, 94 Einträge. Gebaut aus dem Strategie-Katalog (Projektordner
`strategie-katalog/verworfen/verworfen.json`). Einträge werden nie gelöscht, nur ergänzt.

## Lehren

1. **Kosten.** Kurze Trades unter etwa einer Stunde verlieren nach Spread und Rutschen fast immer. Das war in jeder Runde so, von den Scalpern bis zu Bollinger mit RSI.
2. **Umdrehen.** Einen Verlierer umzudrehen hilft meist nicht. Bei der Gold-Matrix waren 97 % der Verluste Kosten, und die zahlt auch die Gegenrichtung (dreimal getestet, 0 von 8). Bollinger auf Stunden umgedreht blieb bei 0,86 (19.11.2026). Einen Gewinner wie den Nikkei-Scalper umzudrehen verliert sicher, seinen Gewinn und zweimal die Kosten. Es hilft nur, wenn der Verlust vor den Kosten entsteht und die Kosten klein sind, wie bei Bollinger auf Krypto (0,69 wurde 1,07, aber immer noch zu wenig).
3. **Auswahl danach.** Einen Markt erst nach dem Ergebnis auszuwählen ist Zufall. Beispiele sind Supertrend nur auf Gold, NR7 nur auf DAX oder AUD/USD umgedreht.
4. **Zu wenige Trades.** Unter 100 Trades sagt ein hoher Gewinnfaktor wenig. Williams %R hatte 2,66 bei 77 Trades, Bitcoin short nach Schocktagen 4,16 bei 6 Trades.
5. **Vorher festlegen.** Ein Test zählt nur, wenn die Regel vorher versiegelt war. Nachbessern nach dem Ergebnis zählt nicht, sonst findet man immer etwas.
6. **Viele Varianten.** Wer sehr viele Varianten rechnet, findet Glückstreffer. Darum gilt Holm über alle Varianten. Die Gold-Matrix hatte 54.375 Varianten und keine bestand.
7. **2026 zählt.** Viele Regeln liefen früher gut und sind 2026 schwach, etwa Supertrend (0,55), der Tag vor der Fed (0,49) und die Kreuzkurs-Rückkehr (0,57). Darum zählt 2024 bis 2026 am meisten.
8. **Zufall prüfen.** Ein Test braucht den Vergleich mit Zufall, und vorher einen Probelauf auf einem erfundenen Markt ohne Vorteil. Drei Fehler in der Methode wurden so gefunden (11.11.2026).
9. **Uhrzeit der Daten.** Die HistData-Uhr war im Sommer eine Stunde falsch umgerechnet. Alles mit Uhrzeit zwischen März und Oktober war eine Stunde verschoben (gefunden 11.11.2026).
10. **Einstiegskerze.** Beim Vortag-Test hängt das Ergebnis daran, wie man die Einstiegskerze liest. Streng gelesen wären 87 % der Trades in der Einstiegskerze gestoppt worden. Live wurden 6 von 6 gestoppt (18.11.2026). Prüfung auf 1-Min.-Kerzen steht aus.
11. **Ausstieg gebucht.** Der Gold-Bot buchte einen Ausstieg mit dem falschen Kurs, +44 € statt +113 € (18.11.2026). Seitdem wird der echte Kurs beim Broker nachgelesen.
12. **Ein Markt.** Sieben Gold-Bots auf einem Markt verlieren oft gemeinsam. Vor einem weiteren Gold-Bot erst diese auswerten.
13. **Pausen.** Eine Verlustgrenze mit Pause kostet mehr, als sie spart. Ein guter Monat sagt den nächsten nicht voraus.
14. **Übernacht.** Trendfolge über Wochen verliert bei CFDs an der Übernachtgebühr, auch wenn sie vor Kosten leicht positiv ist.
15. **Ausstieg ändern.** Ein anderer Ausstieg macht aus einer Regel ohne Vorteil keine gute. Früheres Ziel, Stufen-Stop oder länger halten halfen am 19.11.2026 nur dort, wo große Ziele selten erreicht wurden (Montag 0,69 auf 0,97, 4-Std.-Ausbruch 1,24 auf 1,30). Ein Stop auf Einstand nahm pine-k5 die Hälfte des Gewinns, weil viele Trades erst zurücklaufen und dann weiter steigen.

## Einträge

| Karte | Name | Markt | Zeitebene | Ergebnis | Stand | Art des Fehlers |
|---|---|---|---|---|---|---|
| 3 | Groß-Box mit 1,5-fachem Stop und Ziel | Gold | Stunden | Gold-Thread 19.11.2026, versiegelt. 806 Trades, Gewinnfaktor 1,27, aber weniger Gewinn als heute (+88 R statt +93 R). Die 1,25-fache Fassung hat bestanden und wird vorwärts gezählt. | im Test durchgefallen | Ausstieg ändern |
| 5 | Gold-Zonen | Gold · Account 2 | 4 Std. | Live −10 €. Test durchgefallen, läuft auf deine Wahl als Vorwärtstest, Urteil nach 40 Trades. | von Kiron verworfen | Gewinnfaktor zu klein |
| 6 | Pine k5 mit Stop auf Einstand ab +1 R | Gold | 5 Min. | Gold-Thread 19.11.2026, versiegelt. 2.294 Trades, Gewinnfaktor 1,04 statt 1,08, +47 R statt +92 R. | im Test durchgefallen | Ausstieg ändern |
| 7 | Pine tp3 mit Stop auf Einstand ab +0,3 R | Gold | 5 Min. | Gold-Thread 19.11.2026, versiegelt. 158 Trades, Gewinnfaktor 0,04. Trades ohne +0,3 R haben weiter keinen Stop. | im Test durchgefallen | Ausstieg ändern |
| 14 | Nikkei-Scalper umgedreht | Nikkei | Minuten | Ohne Rechnung entschieden (Demo-Strategien-Thread, 19.11.2026). Der Scalper ist leicht im Plus (170 Trades, Gewinnfaktor 1,09). Umgedreht verliert er seinen Gewinn und zweimal die Kosten. | ohne Rechnung verworfen | Umdrehen, Kosten |
| 25 | Silver Bullet ohne Ziel bis 16 Uhr New York | US100, US500 | 5 Min. bis Stunden | 1298 Trades, Gewinnfaktor 0,96, 2026 0,9, z -0,02. Durchgefallen. | im Test durchgefallen | Ausstieg ändern |
| 25 | ICT Silver Bullet | US100, US500 | 5 Min., bis 2 Std. | 1.298 Trades, 46 % Treffer, Gewinnfaktor 1,01. Nach Kosten bleibt nichts. Quelle TTrades (908.000 Aufrufe). | im Test durchgefallen | Kosten |
| 26 | NR7-Ausbruch | 11 Märkte | Tage | 1.018 Trades, Gewinnfaktor 0,97. DAX 1,39 und Gold 1,25 sind Zufallsstreuung. Quelle Toby Crabel. | im Test durchgefallen | Zufall |
| 26 | NR7 umgedreht nur auf AUD/USD | AUD/USD | Tage | Nicht gerechnet. Umgedreht wären es etwa 1,66 bei 90 Trades, aber AUD/USD wäre nach dem Ergebnis ausgesucht. | ohne Rechnung verworfen | Auswahl danach, Zu wenige Trades |
| 27 | Supertrend des S&P 500, USD/JPY in Gegenrichtung | USD/JPY | 4 Std. | 67 Trades, Gewinnfaktor 0,97, 2026 0,88, z 0,66. Durchgefallen. | im Test durchgefallen | Gewinnfaktor zu klein |
| 27 | Supertrend 4 Std. | 7 Märkte | 4 Std., Tage | 379 Trades, Gewinnfaktor 0,91, 2026 nur 0,55. Gold allein 2,09 bei 47 Trades. Quelle Trade Pro, TradingLab. | im Test durchgefallen | 2026 schwach, Zu wenige Trades |
| 28 | Bollinger + RSI umgedreht (gespiegelt) | Devisen, Gold, US-Indizes | Stunden | 4001 Trades, Gewinnfaktor 0,86, 2026 0,88, z -0,18. Durchgefallen. | im Test durchgefallen | Umdrehen |
| 28 | Bollinger-Band mit RSI | Devisen, Gold, US-Indizes | 1 Std. | 4.085 Trades, 28 % Treffer, Gewinnfaktor 0,86. Quelle TradingLab (1,9 Mio. Aufrufe). | im Test durchgefallen | Gewinnfaktor zu klein |
| 29 | Bollinger + RSI Krypto umgedreht (gespiegelt) | Bitcoin, Ether | Stunden | 1667 Trades, Gewinnfaktor 0,93, 2026 0,77, z 1,61. Durchgefallen. | im Test durchgefallen | Umdrehen |
| 29 | Bollinger + RSI Krypto umgedreht, Stop 1,5 ATR, Ziel 2 R | Bitcoin, Ether | Stunden | 1150 Trades, Gewinnfaktor 1,07, 2026 1,0, z 3,09. Durchgefallen. | im Test durchgefallen | Umdrehen |
| 29 | Bollinger-Band mit RSI auf Krypto | Bitcoin, Ether | 1 Std. | 1.727 Trades, Gewinnfaktor 0,69, schlechter als 97 % der Zufallsläufe. | im Test durchgefallen | Zufall |
| 31 | 4-Std.-Ausbruch auf Krypto | Bitcoin, Ether | 4 Std. | 319 Trades, Gewinnfaktor 1,23, aber 2026 nur 0,91 und ohne die 5 besten Trades 0,98. | im Test durchgefallen | 2026 schwach, Zu wenige Trades |
| 32 | CME-Lücke mit halber Lücke als Ziel | Bitcoin, Ether | Tage | 160 Trades, Gewinnfaktor 0,61, 2026 0,64, z -1,79. Durchgefallen. | im Test durchgefallen | Ausstieg ändern |
| 32 | CME-Lücke bei Bitcoin | Bitcoin, Ether | Wochenende bis Freitag | 160 Trades, Gewinnfaktor 0,77. Die Lücke schließt sich oft, aber erst nach dem Stop. | im Test durchgefallen | Gewinnfaktor zu klein |
| 33 | Montagsbereich mit Stufen-Stop 1 R | Bitcoin, Ether | Tage | 286 Trades, Gewinnfaktor 0,97, 2026 0,91, z 0,21. Durchgefallen. | im Test durchgefallen | Ausstieg ändern |
| 33 | Montagsbereich mit Ziel 1 R | Bitcoin, Ether | Tage | 286 Trades, Gewinnfaktor 0,9, 2026 0,77, z 0,3. Durchgefallen. | im Test durchgefallen | Ausstieg ändern |
| 33 | Montagsbereich bei Krypto | Bitcoin, Ether | Woche | 286 Trades, Gewinnfaktor 0,69. | im Test durchgefallen | Gewinnfaktor zu klein |
| 34 | 4-Std.-Ausbruch mit Ziel 1 R | DAX, FTSE, Nikkei | 4 Std. | 393 Trades, Gewinnfaktor 1,3, 2026 1,66, z 2,26. Kandidat, zählt als nicht bestanden. | Kandidat, nicht bestanden | Ausstieg ändern |
| 35 | 4-Std.-Ausbruch auf Silber | Silber | 4 Std. | 139 Trades, Gewinnfaktor 1,33, aber der Zufallsvergleich reichte nicht. | im Test durchgefallen | Zufall |
| 36 | 4-Std.-Ausbruch auf US-Indizes | US500, US100 | 4 Std. | 332 Trades, Gewinnfaktor 0,90. | im Test durchgefallen | Gewinnfaktor zu klein |
| 37 | 4-Std.-Ausbruch auf Devisen | 7 Währungspaare | 4 Std. | 955 Trades, Gewinnfaktor 0,79. | von Kiron verworfen | Gewinnfaktor zu klein |
| 38 | Turnaround Tuesday beide Seiten, Ziel 0,5 ATR | US500, US100 | 1 Tag | 247 Trades, Gewinnfaktor 0,98, 2026 0,79, z 0,54. Durchgefallen. | im Test durchgefallen | Gewinnfaktor zu klein |
| 38 | Dienstag-Regel US-Indizes | US500, US100 | 1 Tag | 87 Trades, Gewinnfaktor 0,99. | im Test durchgefallen | Zu wenige Trades |
| 39 | Turnaround Tuesday mit Stufen-Stop 0,5 ATR | DAX, FTSE, Nikkei | 1 Tag | 188 Trades, Gewinnfaktor 0,94, 2026 0,75, z -0,33. Durchgefallen. | im Test durchgefallen | Ausstieg ändern |
| 39 | Dienstag-Regel DAX, FTSE, Nikkei | DAX, FTSE 100, Nikkei | 1 Tag | 188 Trades, Gewinnfaktor 1,13, 2026 0,83. | im Test durchgefallen | 2026 schwach |
| 41 | Verlierer umdrehen | Gold | alle | 0 von 8 bestanden. Auch umgedreht verlieren 7 von 8, weil rund 97 % der Verluste Kosten sind. Nicht wiederholen. | von Kiron verworfen | Kosten |
| 42 | Signal-Box aus den TikTok-Streams | Gold | 15 Min., 1 Std., 4 Std. | 15 Min. 0,93 (8.389 Trades), 1 Std. 0,96, 4 Std. 1,12. Durchgefallen. | im Test durchgefallen | Gewinnfaktor zu klein |
| 43 | Groß und klein | Gold | 15 Min. bis 4 Std. | Drei Ebenen 0,98, zwei Ebenen 1,05. Durchgefallen. | im Test durchgefallen | Gewinnfaktor zu klein |
| 44 | KI-Level von TradingTop | Gold | 1 Std., 4 Std. | 1 Std. und 4 Std. je 0,87. Durchgefallen. | im Test durchgefallen | Gewinnfaktor zu klein |
| 45 | Stream-Box verbessert | Gold | 15 Min., 1 Std. | Alle 8 durchgefallen, beste die Box auf 1 Std. mit 1,13. | im Test durchgefallen | Gewinnfaktor zu klein |
| 46 | Große Box (Test) | Gold | 15 Min. bis 4 Std. | 945 Trades, Gewinnfaktor 1,21, Kontrolle 2022 bis 2024 0,96. Knapp durchgefallen, läuft als Groß-Box auf Account 6. | im Test durchgefallen | Gewinnfaktor zu klein |
| 47 | Alle sieben Boxen in einem Konto | Gold | 15 Min. bis 4 Std. | Mit Gegenrichtung 1,03, ohne 1,16 (Kontrolle 0,94), mit Prüfer 1,13. Durchgefallen. | im Test durchgefallen | Gewinnfaktor zu klein |
| 48 | Long und Short getrennt | Gold | 15 Min. bis 4 Std. | Nur Shorts 0,90, alle Longs 1,16 (2026 0,91), beste Shorts 0,94, große Strategie 1,16 (Kontrolle 0,86). Durchgefallen. | im Test durchgefallen | 2026 schwach |
| 49 | Eröffnungskurse als Linien (montyfinance) | 21 Märkte | Tag bis Jahr | Kein Filter und keine Regel bestanden. Gold-Rücklauf zum Tages-Open 1,37, aber 2026 allein 0,85. | im Test durchgefallen | 2026 schwach |
| 50 | Gold-Bot: andere Ausstiege | Gold | 1 Std. | Alle durchgefallen (Gold-Lernjournal). | im Test durchgefallen | Gewinnfaktor zu klein |
| 51 | Gold-Bot: Phasen, Wende, immer im Markt | Gold | 1 Std. | Alle durchgefallen, bis Idee 62 im Gold-Lernjournal. | im Test durchgefallen | Gewinnfaktor zu klein |
| 52 | Tagesrichtung aus Vorhersagen | Gold | Tag | 0 von 6 Varianten bestanden. | im Test durchgefallen | Gewinnfaktor zu klein |
| 53 | Tag vor der Fed | US500, US100 | 1 Tag | Prüfung 2021 bis 2026 Gewinnfaktor 1,80, aber 2025 und 2026 nur 0,49. Der Effekt wird schwächer. | im Test durchgefallen | 2026 schwach, Zu wenige Trades |
| 54 | Gotobi-Tage | USD/JPY | Stunden | Gewinnfaktor 0,98. Von dir gestrichen. | von Kiron verworfen | Gewinnfaktor zu klein |
| 55 | Monatsende-Fixing bei Devisen | EUR, GBP, JPY | Stunden | Gewinnfaktor 0,71. Der Kurs lief eher gegen die Richtung aus der Studie. | von Kiron verworfen | Gewinnfaktor zu klein |
| 56 | Gold über Nacht kaufen | Gold, Silber | Nacht | Vor Kosten 1,24, nach Kosten 0,73. | im Test durchgefallen | Kosten |
| 57 | Gold tagsüber verkaufen | Gold, Silber | Tag | Gewinnfaktor 0,79. | von Kiron verworfen | Gewinnfaktor zu klein |
| 58 | Index über Nacht | US500, US100 | Nacht | Vor Kosten 1,14, nach Kosten 0,96. Von dir gestrichen. | im Test durchgefallen | Kosten |
| 59 | Kreuzkurs-Rückkehr | EUR/GBP, EUR/CHF, AUD/NZD | Tage | Gewinnfaktor 0,99, mit Wende 0,84. 2025 bis 2026 nur 0,57. | von Kiron verworfen | 2026 schwach |
| 60 | Nacht-Scalper | 9 Währungspaare | Minuten | Gewinnfaktor 0,73. | von Kiron verworfen | Kosten |
| 61 | Stunden-Saison | 20 Märkte | 1 Std. | Es gibt klare Muster, aber keines ist größer als zwei Spreads. Keine Stunde wurde gewählt. | von Kiron verworfen | Gewinnfaktor zu klein |
| 62 | Fixing-Umkehr Europa | EUR, GBP, CHF | Minuten | Schlägt jede zufällige Uhrzeit, verdient aber auch vor Kosten nichts mehr. Gewinnfaktor 0,89. | im Test durchgefallen | Kosten |
| 63 | Fixing-Umkehr Tokio | JPY, AUD, NZD | Minuten | Gewinnfaktor 0,75. | von Kiron verworfen | Kosten |
| 64 | Schwung nach US-Zahlen | Gold, Silber, 7 Dollar-Paare | Stunden | Gewinnfaktor 0,91. Nach dem Schock kommt im Mittel nichts mehr. | im Test durchgefallen | Gewinnfaktor zu klein |
| 65 | Schwung nach der Fed | Gold, Silber, 7 Dollar-Paare | Stunden bis Nacht | Gewinnfaktor 1,25, aber nur 89 Trades, Zufall 72 % und 2025 bis 2026 0,88. | im Test durchgefallen | Zufall, 2026 schwach, Zu wenige Trades |
| 66 | Gold kaufen nach einem Schocktag | Gold | 5 Tage | Gewinnfaktor 0,67. In echten Crashs verkaufen Anleger auch Gold. | von Kiron verworfen | Zu wenige Trades |
| 67 | Bitcoin short nach einem Schocktag | Bitcoin | 5 Tage | Nur 6 Trades seit 2000 bis heute. Viel zu wenige für ein Urteil. | im Test durchgefallen | Zu wenige Trades |
| 68 | Schwache Aktien short nach einem Schocktag | 59 US-Aktien | 5 Tage | Gewinnfaktor 0,85. | von Kiron verworfen | Gewinnfaktor zu klein |
| 69 | Marktphasen-Erkenner | 18 Märkte | Monat | In neuen Jahren blieben nach Kosten nur +6,5 R in 6 Jahren über 18 Märkte. Durchgefallen. | im Test durchgefallen | Kosten |
| 70 | Trendfolge 12 Monate | 41 Märkte | Monate | Prüfung 0,46. Vor Kosten leicht positiv, die Übernachtgebühr frisst den Vorteil. | von Kiron verworfen | Kosten |
| 71 | Trend-Abstimmung | 41 Märkte | Wochen | Prüfung 0,41. | von Kiron verworfen | Gewinnfaktor zu klein |
| 72 | Gleitende Durchschnitte kreuzen (EWMAC) | 41 Märkte | Wochen | Prüfung 0,34. | von Kiron verworfen | Gewinnfaktor zu klein |
| 73 | Donchian-Trend (Turtle) | 41 Märkte | Wochen | Prüfung 0,44. | von Kiron verworfen | Gewinnfaktor zu klein |
| 75 | IBS auf Indizes | Indizes | 1 Tag | Prüfung 0,77. | von Kiron verworfen | Gewinnfaktor zu klein |
| 76 | Double 7 auf Indizes | Indizes | Tage | Prüfung 0,75, auf US-Indizes 1,08. | von Kiron verworfen | Gewinnfaktor zu klein |
| 77 | Monatswechsel auf Indizes | Indizes | Tage | Prüfung 1,01, in der Auswahl 0,70. | von Kiron verworfen | Gewinnfaktor zu klein |
| 78 | Index-Momentum (Reddit) | Indizes | Monate | Prüfung 0,45. | von Kiron verworfen | Zu wenige Trades |
| 79 | Trend-Rücksetzer auf allen Märkten | 41 Märkte | Tage | Prüfung 0,87, auf US-Indizes 1,37. Hält nur dort. | von Kiron verworfen | Gewinnfaktor zu klein |
| 80 | Rücksetzer nach Schwankung | 41 Märkte | Tage | Prüfung 0,75. | von Kiron verworfen | Gewinnfaktor zu klein |
| 82 | Weiter Stop, tagelang halten, 99 % Treffer | 20 Märkte | Tage | Über 90 % Treffer, aber 12 von 21 verloren trotzdem Geld. Zufällige Richtung traf genauso oft. Ein Treffer: Nasdaq nur Long, daraus wurde Nasdaq Noise Long. | von Kiron verworfen | Gewinnfaktor zu klein |
| 83 | Opening Range Breakout 15 Min. | 257 Märkte | 15 Min. | Bester Markt Tesla 1,53, im Siegel 0,44. Video-Fassungen 0,38 und 0,33. | von Kiron verworfen | Auswahl danach |
| 84 | Initial Balance (erste Stunde) | 257 Märkte | 15 Min. | Bester Markt 1,42, im Siegel 0,30. | von Kiron verworfen | Auswahl danach |
| 85 | Asien-Ausbruch | Gold, GBP/NZD | 15 Min. | Gold 1,70, im Siegel 0,62. Video-Fassung auf GBP/NZD bestand knapp (1,17 bei 35 Trades), über 12 Jahre nicht. | von Kiron verworfen | Auswahl danach |
| 86 | Richtung der ersten Kerze | 257 Märkte | 15 Min. | Bester Markt 1,39, im Siegel 0,46. | von Kiron verworfen | Auswahl danach |
| 87 | London-Breakout | 257 Märkte | 15 Min., 1 Std. | Bester Markt 1,89, im Siegel 0,60. Video-Fassung 0,24. | von Kiron verworfen | Auswahl danach |
| 89 | Turtle Soup (Fehlausbruch) | 98 Märkte | 15 Min. | Bester Markt 1,88, im Siegel 0,28. | im Test durchgefallen | Auswahl danach |
| 90 | Lücke schließen (Gap Fill) | 257 Märkte | 15 Min. | Bester Markt Dow 1,79, im Siegel 0,62. Video-Fassungen 0,98 und 0,77. | von Kiron verworfen | Auswahl danach |
| 91 | Larry Williams Volatilitäts-Ausbruch | 257 Märkte | Tag | Standard ohne Markt über 1,2. Video-Fassung USD/JPY 1,87, im Siegel 1,14, aber nicht besser als Zufall. | im Test durchgefallen | Zufall, Auswahl danach |
| 92 | Schlussstunde (Intraday-Momentum) | 257 Märkte | 1 Std. | Bester Markt US100 1,53, im Siegel 0,64. | von Kiron verworfen | Auswahl danach |
| 93 | Noise Band | 257 Märkte | 15 Min. | Bester Markt 1,43, im Siegel 0,48. | von Kiron verworfen | Auswahl danach |
| 94 | Noise Band nur Long | 257 Märkte | 15 Min. | Bester Markt UK100 2,32, im Siegel 0,59. Mit weitem Stop und Haltedauer später der Nasdaq-Bot. | von Kiron verworfen | Auswahl danach |
| 95 | Erste Kerze und EMA 12 (TikTok) | Nasdaq, S&P 500 | 5 Min. | Gewinnfaktor 0,88. Das Video versprach +982 %, ohne Stop. | von Kiron verworfen | Kosten |
| 96 | Noise Band (TikTok #33) | Nasdaq | 5 Min. | Gewinnfaktor 1,14, 8 von 12 Jahren im Plus, aber unter der Hürde von 1,3. | im Test durchgefallen | Kosten |
| 97 | IV-Wände | Nasdaq, S&P 500 | Tag | Gewinnfaktor 0,87 bis 1,14. Durchgefallen. | im Test durchgefallen | Gewinnfaktor zu klein |
| 98 | Gelbe Box | Nasdaq, S&P 500 | 5 Min. | Gewinnfaktor 1,01 und 0,98. | im Test durchgefallen | Kosten |
| 99 | Laplace-Statarb | 20 Aktien | Tage | Sharpe −1,24 und −0,76, also klarer Verlust. | im Test durchgefallen | Gewinnfaktor zu klein |
| 100 | Scalper mit deinen Signalen C und B | bis 26 Märkte | 1 Min. | Runde 1 0 von 32, Runde 2 0 von 72, Runde 3 ein Treffer, der in der Prüfung durchfiel. | von Kiron verworfen | Kosten |
| 101 | Deine Signale C und B auf 19 Märkten | 19 Märkte | 5, 15, 60 Min. | 0 von 342 Kombinationen. Gewinnfaktor im Mittel 0,50 bis 0,60. | von Kiron verworfen | Gewinnfaktor zu klein |
| 102 | Signale C und B auf Aktien | 18 Aktien | 5 Min. bis 1 Std. | 0 von 324 Kombinationen. | von Kiron verworfen | Gewinnfaktor zu klein |
| 103 | Gold-Logik auf 257 Märkten, beste 5 auf Demo | 257 Märkte | 15 bis 60 Min. | Alle sechs Runde-3-Bots verloren 2025 und wurden am 04.11.2026 abgelöst. | von Kiron verworfen | 2026 schwach |
| 104 | Verlustgrenze und Pause nach Verlusten | alle Bots | – | Kostet mehr, als es spart. | von Kiron verworfen | Gewinnfaktor zu klein |
| 105 | Risiko je Trade nach Schwankung | Kombi | – | Schlechter als überall 1 % (Sharpe 0,79 statt 0,82). Kommt nicht wieder. | von Kiron verworfen | Gewinnfaktor zu klein |
| 106 | Nur die letzten 4 Wochen ansehen | alle | – | Ein guter Monat sagt den nächsten nicht voraus. | von Kiron verworfen | Gewinnfaktor zu klein |
| 107 | Vortag-Uhrzeit neu gelernt | Devisen | Stunden | Durchgefallen, kein Zwilling. Die Bots bleiben, wie sie sind. | von Kiron verworfen | Gewinnfaktor zu klein |
