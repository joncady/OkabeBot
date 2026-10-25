# Content-aware character framework

The renderer consumes structured slots, never titles or raw model instructions.
`source adapter → metadata resolver → content context → reaction plan → character renderer`.
The metadata resolver/parser is deliberately the next increment. Explicit contexts,
fixtures, and manual MCP/API calls exercise the renderer first.

## High-level contract

```json
{
  "kind": "video",
  "format": "sports_highlights",
  "sport": "soccer",
  "genres": [],
  "reaction": null,
  "energy": 0.6,
  "confidence": 1,
  "participants": [
    {"name":"AFC Bournemouth", "short_name":"BOU", "colors":["#b72332","#ffffff"], "crest":"bournemouth"},
    {"name":"AC Milan", "short_name":"MIL", "colors":["#bf2634","#ffffff"], "crest":"ac_milan"}
  ]
}
```

`kind`: unknown/movie/episode/video/music. `format`: catalog video format. `genres`:
up to five movie genre keys, first is dominant. `reaction`: optional explicit visual
mood override; otherwise the preset chooses. `energy` controls movement strength.
`confidence < 0.7` falls back to attentive with no team assertions. Participants are
ordered left/right, at most two. `sport` is explicit: soccer and american_football
are distinct. A missing sport uses a generic ball rather than guessing.

The main catalog is [content-presets.json](../okabebot/assets/content-presets.json).
Use `GET /content/presets` with the controller token to enumerate it. POST the context
above to `/content/context` to apply it to the currently verified app/content ID.
This uses the existing `X-Hardware-Token` authentication. The MCP equivalents are
`get_content_reaction_presets` and `set_content_context(app, content_id, context)`.
The running bridge must share its state directory with MCP. Context expires after
four hours and stops applying when the app/content ID changes. Posting `{}` restores
neutral attentive context for that content. The parser can later use exactly this API.

Crests are local PNG assets in `pi/assets/crests/<key>.png`. The renderer never fetches
arbitrary remote files. Until verified assets are installed, it shows colored badges
with the provided abbreviations. These are prototype badges, not official team logos.
Add actual crests with provenance as an asset task; no guessed team identity or score.
Team colors and initials are supplied, not inferred by the renderer.

## Coverage and visual vocabulary

53 presets, sharing 14 reusable reaction styles and a small prop vocabulary. This is
coverage of inputs and base reactions, not 53 unique hand-animated sequences.

| Family | Cases | Initial visual behavior |
| --- | --- | --- |
| Movie spectacle | action, adventure, fantasy, science_fiction, animation | energetic/curious/wonder, star or planet, small head movement |
| Movie tension | horror, thriller, mystery, crime | concerned/analytical, stiller movement, search token |
| Movie warmth | comedy, romance, family, drama | amused/moved/delighted, heart or sparkle, gentle bob/tilt |
| Movie factual/other | documentary, history, music, war, western, tv_movie | attentive/upbeat/serious, book/note/context token |
| Sports | highlights, live, analysis | ball for selected sport, left/right crest slots, attentive or competitive movement |
| Gaming | game_review, gameplay, esports | controller, analytical/engaged/competitive |
| Comedy/entertainment | comedy_sketch, standup, reaction, film_review, trailer, shorts | amused/curious/analytical; modest motion |
| Learning | tutorial, lecture, science, technology_review, diy | attentive/curious, book/search/planet/context token |
| Talk/factual | news, interview, podcast, nonprofit | serious/attentive/moved; no invented sentiment |
| Lifestyle | vlog, travel, food, fitness, automotive, fashion | engaged/curious/energetic and context props |
| Music/quiet | music_video, concert, nature, animals, asmr, relaxation | upbeat/calm/delighted, note/moon/context props |
| Unknown | unknown format, missing metadata, low confidence | attentive, conservative motion, generic context token |

All prop keys now map to the shared 20-tile pixel-art atlas described below.
Several content families intentionally share one tile (for example cinema for
film/war/western). Sports select soccer, football or basketball artwork; other
sports currently use the generic sports tile until more art is added.

State handling is orthogonal: PLAYING animates; PAUSED freezes props/movement;
BUFFERING freezes and retains context; IDLE/other app/disconnect clears it.
Notifications, speaking, thinking, and push-to-talk listening take precedence.
Classification describes the overall content. A horror movie does not imply a scare
just occurred; a soccer highlight does not imply a goal. Event reactions such as
celebrate, gasp, win/loss, or laugh-at-a-joke require an explicit, timestamped event
source before enabling. Avoid outcome spoilers from scores/metadata.

## Automated coverage pass

`examples/content/cases.json` enumerates all 53 presets × four playback states.
`tests/test_content.py` renders every case on all four characters (848 combinations),
checks low-confidence fallback, content scoping, sports variants, and priority yielding.
`scripts/preview-content.py` makes a reviewable contact sheet. This is synthetic
coverage, not a benchmark of inferred genres and not a live test of every app.

A parser evaluation set should add 5–10 verified examples per format, ambiguous and
misleading titles, mixed genres, missing IDs, live streams, ads, title changes,
resumes/seeks, expired metadata, and app/disconnect transitions. Store expected slots
and confidence/abstention, not pixel snapshots. Split channels/titles across train and
test to avoid memorizing channel names. Measure wrong-team rate and abstention as
well as format accuracy. The renderer should never decide team identities itself.

## Representative app integration pass

These are representative targets, not a ranked popularity claim. Discover the actual
Cast app and record available fields while the user plays each app; do not launch or
interrupt apps just to probe. The current TV verified Spotify and YouTube only.

| App group | First adapter | Additional enrichment | Current evidence |
| --- | --- | --- | --- |
| YouTube / YouTube TV | Cast media callbacks | YouTube video category/channel/tags; explicit format classifier | YouTube title, ID, position, duration, state verified; YouTube TV untested |
| Spotify | Cast callbacks | existing local audio energy meter | TV track/artist/state verified |
| Netflix, Prime Video, Disney+, Hulu, Max, Apple TV+ | capability probe via Cast/HA on actual app/device | resolve verified title/year/ID to genre provider; manual context fallback | Not tested; no promise of title, position, or genre access |
| Plex | HA Plex media player / server metadata | library genres and stable item ID | Official HA integration supports now-playing/status; not connected here |
| Jellyfin | HA media sessions / server metadata | library genres and stable item ID | Official HA integration supports media info/progress; not connected here |
| Twitch | capability probe while actually casting | channel/category metadata adapter if credentials are added | Not tested |

No universal movie genre field is promised by Cast. Use app-specific metadata first,
then a cached resolver with exact identity, then manual context, then unknown.
No additional cloud keys or accounts are required for this renderer-first stage.

Research sources: [YouTube video metadata](https://developers.google.com/youtube/v3/docs/videos)
(categoryId, tags, channel and title are available in the Data API, not all in Cast),
[YouTube categories](https://developers.google.com/youtube/v3/docs/videoCategories/list),
[TMDB movie genre endpoint](https://developer.themoviedb.org/reference/genre-movie-list),
[IMDb genre guide](https://help.imdb.com/article/contribution/titles/genres/GZDRMS6R742JRGAG),
[Cast media fields](https://developers.google.com/cast/docs/media/messages),
[Plex](https://www.home-assistant.io/integrations/plex/),
[Jellyfin](https://www.home-assistant.io/integrations/jellyfin/).

## Progress during callback silence

A connected PLAYING session keeps its last-known state. The controller compensates
for transport delay, then the Pi extrapolates from its own monotonic clock at the
reported playback rate, clamped to duration. It does not expire after 30 seconds.
Pause/buffering freezes position; a new callback corrects a seek/drift. App change,
IDLE, or connection loss clears playback. A disconnected controller itself cannot
confirm new TV state; a future transport-health lease can show an uncertainty marker
without pretending playback stopped. Live/unknown-duration media has no percent bar.


## Standalone previews and crest sources

Developer mode's Content reaction preview always uses `POST /content/preview`.
It needs no app or content ID. Sport and left/right team selectors fill the same
structured context slots; Real Madrid and Barcelona currently have Wikipedia-sourced
crests. `POST /content/preview/stop` restores the actual media state. Previews expire
after 90 seconds, with a 95-second display-side safety timeout if the controller exits.
They are labeled as previews and have no invented playback timeline. The scoped
`/content/context` route remains for detected content; a missing identity falls back
to standalone preview for compatibility with older cached controllers.

`pi/assets/crests/sources.json` preserves each article, file description, image URL,
and rights metadata retrieved from Wikipedia. These third-party club marks are not
covered by this project's MIT license. The downloaded PNGs are rendered locally with
preserved aspect ratio; no request to Wikipedia runs inside the animation loop.
The initial assets are [Real Madrid](https://en.wikipedia.org/wiki/File:Real_Madrid_CF.svg)
and [Barcelona](https://en.wikipedia.org/wiki/File:FC_Barcelona_(crest).svg).


## First automatic parser: YouTube sports titles

`okabebot/content_parser.py` is a local rules adapter, invoked when there is no scoped
manual override. It requires YouTube with a content ID. It recognizes explicit
league/sport terms, highlights/recap, analysis/breakdown, and explicit LIVE metadata.
Two registered teams separated by v/vs/versus can also establish the sport. It does
not use generic “football” alone to distinguish soccer from American football.
Video-game markers such as EA FC/FIFA/Madden switch to gaming and omit match crests.

The small registry `okabebot/assets/teams.json` currently covers Real Madrid,
Barcelona, Sunderland, Leeds, Bournemouth and AC Milan. It includes aliases, sport,
colors, abbreviation, and Wikipedia article identity. Expand this registry with
verified clubs; `scripts/fetch-team-crests.py <keys>` downloads selected article
thumbnails and rights/source metadata ahead of deployment. Unknown teams are omitted.
Aliases can still be ambiguous: the current resolver explicitly rejects Inter Milan
as AC Milan, and abstains if a side matches multiple registered teams. This is an
initial rules implementation, not a general entity linker or a measured classifier.
Confidence values are rule-strength heuristics, not calibrated probabilities.

The `/state` response includes `content_parse` with slots, evidence and unresolved
fields; Developer mode shows a short summary. A scoped manual context overrides the
automatic plan; standalone previews temporarily override its display. No video score,
goal timing, win/loss, or current on-screen action is extracted. Genre and broader
video-format parsing remain follow-up work.

Initial live fixture: “Sunderland v. Leeds United | PREMIER LEAGUE HIGHLIGHTS |
10/25/2026” → sports_highlights / soccer / Sunderland left / Leeds right. The Pi
shows the two cached crests and soccer ball with the competitive reaction. Playback
state and progress come separately from Cast; classification is title-based only.


## Pi rendering performance

The Tk display uses retained scene items, two cached crest images, and four cached
soccer sprite frames. The canonical Pillow preview still renders the same artwork
from shape primitives. Crests occupy 64×64 canonical pixels; the 16×16 soccer sprite
is enlarged with nearest-neighbor pixels and rolls/bounces near the lower edge.

The title is one cached image in a clipped child canvas. Scrolling changes its X
coordinate instead of rendering and PNG-encoding a strip on every frame. The UI loop
targets 30 updates/sec and subtracts rendering time from its timer delay. Display
status exposes `render_metrics.fps` and `work_ms` (EMA); these measure software loop
cadence/work, not physical LCD refresh or acoustic timing. Higher-rate animations
can increase CPU; inspect measured cadence and thermal/throttle state on actual Pis.

## On-demand resolution (no team registration)

`TeamResolver` enriches YouTube and Fubo matchup titles on the controller, using a
single background worker. The bundled registry is an optional fast seed, not a
requirement for new teams. Wikipedia search resolves each name; Wikidata P641 (sport)
and P31 (entity type) validate a sporting team/club. Exact identities, not arbitrary
first search hits, select the crest. Ambiguous sides abstain. Unsupported sports
use the generic sport prop after entity validation; dedicated artwork still uses
the renderer's known sport vocabulary. Individual athletes are not yet resolved.

Positive team lookups persist for 30 days in ignored `sports-resolver.sqlite3`;
misses last one day. Requests are paced and respect 429 backoff, with transient
failures retried later rather than cached as permanent misses. A bounded worker
resolves the current title; API requests never run inside the Pi animation or voice
loop. Warm-cache appearances avoid a new lookup. Initial uncached resolution can
take tens of seconds, and provider failures leave the known title reaction in place.
These heuristics reduce false matches; they do not guarantee every alias resolves.

Crests are downloaded from Wikimedia only when their file identity suggests a
logo/crest, resized to at most 64px on the controller, and sent via an idempotent
`cache_crest` RPC. The Pi validates PNG size/key and writes only `wiki_q<number>`
assets. Rights and source file/article links remain in the resolver cache. Missing
crests use a text badge. No per-team SSH copy or manual registry edit is needed.

Fubo title handling accepts `fuboTV` receiver variants and classifies matchup titles
as `sports_live` even while BUFFERING or lacking a media ID. If the sport has not
resolved, its confidence remains low until enrichment finishes. A failed media load
can retain the receiver's `Casting: <title>` text as BUFFERING; this is context only,
not evidence that playback succeeded. Fubo playback URLs may contain credentials,
so the adapter exposes a stable hashed title identity instead. Live streams have no
percentage progress bar. Native apps that expose no title still need another
metadata source; an app name alone cannot identify teams.


## Shared pixel-art prop slot (v1)

All content families now use `pi/prop_art.py`: one lower-left slot at canonical
(46,208), size 56×56. The semantic `prop` key and optional sport choose a tile from
`pi/assets/content-props-v1.png`; the parser never specifies pixel positions.
The 20-tile generated atlas shares a limited palette, dark outline, shading and
pixel scale. `content-props.json` maps semantic names to source rectangles. The tile
is fitted to a transparent 32px logical grid, then enlarged with nearest-neighbor
pixels. Alpha and aspect ratio are preserved. Cropping is asset extraction, with
explicit bounds to avoid clipping the generated sheet's uneven gutters.

The same slot covers soccer/football/basketball, gaming, cinema, comedy, learning,
romance, mystery, science, horror, music, nature, food, fitness, travel, talk, DIY,
technology, and relaxation. Several genres intentionally share a family prop.
The old rolling soccer animation is replaced by this shared asset behavior: a
small common float during PLAYING, frozen while paused/buffering. Team crests keep
their side positions. Notifications and active speech still take precedence.

The live Pi caches one Tk image for the selected prop; there are no per-frame
bitmap uploads or hundreds of prop rectangles. Canonical previews render the same
sprite through cached color runs. The atlas was created with the built-in image
generation tool; the exact prompt is in `docs/content-props-prompt.txt`.

### Progressive matchup parsing

A title with two opponents and explicit match/highlights/live context can supply
participant labels immediately, across video apps. No team registration or
league keyword is required. Those labels are literal title text, not verified
club identities: show neutral initial badges with no claimed crest or colors.
The sport can remain `unknown` independently of the sports format; use the
neutral content prop until sport enrichment succeeds.

Wikipedia/Wikidata resolution enriches identity, sport and crests in the
background. Provider errors retain the title-derived matchup. Retry respects
rate-limit backoff, and temporary failures are not stored as negative identity
results. True misses are cached for five minutes; verified identities for 30
days. Old negative results are invalidated once when this cache policy is
introduced. An exact full canonical club name can finish lookup early; a token
similarity score alone cannot. Women's, youth and reserve squads require the
corresponding qualifier. Movie/debate versus titles and video-game markers
remain excluded from real-match decoration.

This is progressive rule-based extraction and verified entity enrichment, not
an LLM reading video frames. Semantic classification for less structured titles
can be added behind the same context contract later.
