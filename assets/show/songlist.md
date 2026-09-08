# Songs in the show mix

Reference data from Tunebat (Spotify audio features of the *original* release).
The mix is trimmed and may be re-pitched, so **our own per-song analysis
(`make songs` → out/songs.json) is the authority for timing**; Tunebat is the
sanity check for tempo (it settles half-time ambiguity) and the source for
key/energy/mood. Energy, danceability, happiness are 0–100.

| # | Mix time | Song | Artist | BPM (ref) | BPM (ours) | Key | Energy | Dance | Happy | Notes |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0:00 | Carol of the Bells | Lindsey Stirling | 168 | 166.7 ✓ | E minor | 66 | 23 | 27 | dark, driving, low danceability → gesture not groove |
| 2 | 1:23 | Run Rudolph Run | Chuck Berry | 152 | 76 (= half) | G minor | 72 | 68 | 96 | happiest track in the set; rock'n'roll |
| 3 | 3:10 | Dance of the Sugar Plum Fairy (Trap Remix) | Trap Music Now (YouTube) | n/a | 64.6 (= half of ~129) | — | — | — | — | not on Tunebat; trap feel is half-time by nature |
| 4 | 4:48 | Jingle Bells (feat. The Puppini Sisters) | Michael Bublé | 123 | 123 ✓ | F major | avg | high | exuberant | 3/4 swing per SongBPM; female chorus = the Puppini Sisters |
| 5 | 6:44 | Rockin' Around the Christmas Tree | Brenda Lee (1958 original, per the mix's Deck-the-Halls quote and sax solo) | 142 (SongBPM lists 71 half-time) | 69.8 (= half) | — | — | — | — | |
| 6 | 8:11 | Winter Wonderland | Brooks & Dunn | 130 | 64.6 (= half) | C major | 89 | 54 | 72 | highest energy in the set; country |
| 7 | 10:21 | Snowman | Sia | 105 | 69.8 ✗ (tracker off; use 105) | C♯ major | 51 | 72 | 33 | melancholic, mid-energy, groovy |
| 8 | 11:12 | Feliz Navidad | José Feliciano | 149 | 73.8 (= half) | — | — | — | — | |
| 9 | 12:43 | God Rest Ye Merry Gentlemen | Pentatonix | 136 | 136 ✓ | C♯ minor | 40 | 76 | 70 | a cappella; low energy, high groove |

Sources: [Jingle Bells (SongBPM)](https://songbpm.com/@michael-buble/jingle-bells-feat-the-puppini-sisters), [Rockin' Around (SongBPM)](https://songbpm.com/@brenda-lee/rockin-around-the-christmas-tree), [Feliz Navidad (SongBPM)](https://songbpm.com/@jose-feliciano/feliz-navidad); tunebat.com pages for
[Carol of the Bells](https://tunebat.com/Info/Carol-Of-The-Bells-Lindsey-Stirling/0byPyCPX9mfGMiAGVZxasq),
[Run Rudolph Run](https://tunebat.com/Info/Run-Rudolph-Run-Chuck-Berry/2pnPe4pJtq7689i5ydzvJJ),
[Winter Wonderland](https://tunebat.com/Info/Winter-Wonderland-Brooks-Dunn/0rnSw3KGSSCOZP43xBvhLW),
[Snowman](https://tunebat.com/Info/Snowman-Sia/3mj6prXmzqkj3PA3lg5ySK),
[God Rest Ye Merry Gentlemen](https://tunebat.com/Info/God-Rest-Ye-Merry-Gentlemen-Pentatonix/6dVa1lUKHU2Jqkh6530irt).
