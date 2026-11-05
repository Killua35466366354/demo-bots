# Pine strategies (A and B from Kiron, received 2026-10-29 16:07 UTC, pasted in chat; C see below)

Rule: these files are never edited. Any change is proposed separately.

SHA-256 over the text with trailing spaces at line ends removed and line endings normalised to \n
(chat copy and paste can change trailing spaces; the Pine logic is not affected by them).

| File | Lines | SHA-256 |
| --- | --- | --- |
| A_long_vixfix_stochrsi_v2.pine | 82 | a567a920063123a94a194d0661e85e06f2c1086fd68fa9db4f70e585a24733ba |
| B_short_vixfix_meanrev_v6.pine | 188 | a809fbdc27e386abf0b3d6895fc6e5929bc3a7f532cb3c7783a33da98276f17e |
| C_long_vixfix_meanrev_v6.pine | 188 | f10b2e0c8a060f838898e813d9a1c597277a789d0bd611474d2e81900b072a97 |

C was written by Claude on 2026-10-29 at Kiron's request (the long "Vix Fix Mean Reversion v6" mentioned in B's
header never existed): an exact mirror of B whose defaults give A's signals. Same rule from now on: Kiron pastes
it into TradingView unchanged, and any later change is a new file.

Note: B arrived with the first line `/@version=6` (one slash). In TradingView it must read `//@version=6`;
most likely a copy error in the chat. Stored exactly as received. Kiron's Pine Editor photos (2026-10-29)
confirm `//@version=6` in TradingView and show the rest of A and B identical to these files.

Check: python3 -c "import hashlib,sys;t=open(sys.argv[1],encoding='utf-8').read().replace('\r\n','\n');print(hashlib.sha256(('\n'.join(l.rstrip() for l in t.split('\n')).strip()+'\n').encode()).hexdigest())" FILE
