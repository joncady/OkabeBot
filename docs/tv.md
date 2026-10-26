# TV companion

The first pass is a silent **Now playing on TV** card using a Home Assistant media player's actual `media_title`. It uses the existing character notification layout. It does not play audio, change the TV, identify scenes, or generate movie facts. The package is prepared but disabled until the TV and its streaming app have been tested.

## Connect the playback device

Use the integration for the device actually playing the movie: a streaming box may expose more useful information than the screen connected to it.

| Device | Home Assistant integration | What to check |
| --- | --- | --- |
| VIZIO SmartCast | VIZIO SmartCast; optionally Google Cast for content metadata | Pair with the PIN on the TV, leaving the access token blank. SmartCast exposes the active app; do not treat this as a movie title. Verify Cast metadata with the actual streaming app. |
| Android / Google TV | Android TV Remote plus Google Cast | Remote supplies the foreground app but **not playback state or movie title**. Cast may expose content information for supported apps. |
| Chromecast | Google Cast | Play content from the actual streaming app and inspect its media player attributes. Discovery requires mDNS; known-host IPs are supported when discovery fails. |
| Roku / Roku TV | Roku | Enter its IP if discovery fails. Allow local control under System → Advanced → Control by mobile apps → Network access. It polls playback every ten seconds; verify title availability per app. |
| Apple TV | Apple TV | Complete the on-screen pairing prompts. Inspect playback attributes in the actual app; active-app information alone is not a movie identity. |
| Fire TV | Identify the exact model first | Android TV Remote Service is generally absent. Do not assume the Android TV Remote route works. |

Official setup references: [VIZIO SmartCast](https://www.home-assistant.io/integrations/vizio/), [Android TV Remote](https://www.home-assistant.io/integrations/androidtv_remote/), [Google Cast](https://www.home-assistant.io/integrations/cast/), [Roku](https://www.home-assistant.io/integrations/roku/), [Apple TV](https://www.home-assistant.io/integrations/apple_tv/).

On the current Mac Docker installation, automatic LAN discovery may be unavailable. Add the integration manually using the TV/streaming box's IP if supported. Keep it on the same home network. There is no need to publish Home Assistant to the internet for local TV discovery.

## Verify and enable title cards

1. In **Settings → Devices & services**, add the correct integration and complete any pairing displayed on the TV.
2. Play a movie. In **Developer Tools → States**, select its `media_player` entity. Check that its state is `playing` and that `media_title` is the actual title, not just “Netflix” or an HDMI input. Check `app_name`, `media_content_type`, `media_series_title`, and episode attributes if present. Do not assume every app exposes these.
3. Pause, resume, switch titles, and return to the TV home screen. Make sure the entity updates and does not retain an old title while something else plays. If metadata is missing or stale, leave cards disabled for this entity; an app name is insufficient to fetch facts.
4. Copy [tv.yaml](../examples/home-assistant/tv.yaml) into the private Home Assistant `packages` directory. Replace both `media_player.replace_with_your_tv` placeholders. It depends on the REST command and secrets in [okabebot.yaml](../examples/home-assistant/okabebot.yaml).
5. Validate the Home Assistant configuration, reload automations, and enable **OkabeBot - TV now playing**. `initial_state: false` deliberately disables it again after a reload/restart; once tested, remove that line to preserve the enabled state.
6. Start another title. A silent card should arrive after about three seconds plus the integration's update delay. Pause/resume should not repeat it. The example deduplicates a title per player per calendar day and has a 30-second cooldown. A different title started during that cooldown is deliberately skipped. The existing REST command expires cards after 60 seconds.

This example ignores startup/unavailable-to-playing transitions. To test after enabling, change playback or the title; **Run actions** has no real state trigger and is not an equivalent test. The normal notification priority is visual-only. Turn the automation off to stop cards without affecting playback.

## Context and facts: next increment

Start with a tablet **About this title** action, followed by an optional card when playback is paused. Use verified title plus year or a provider ID to resolve an exact movie; for TV, retain series, season, and episode separately. Ask the user to choose when matches are ambiguous. A manual title selection is a useful fallback when a streaming app supplies no metadata.

Fetch a small set of sourced production facts (release year, director, filming location), cache the result by resolved ID, and retain a source URL. Avoid plot summaries, cast roles that reveal surprises, episode synopses, and guesses derived only from the app name. General trivia datasets cannot guarantee spoiler-free content, so automatic trivia should remain off until its selection policy has been tested.

Playback position is not scene recognition. Do not infer who's currently on screen or what just happened from a timestamp. A future facts provider should be separate from the TV adapter; no provider credentials or speculative lookup service are installed in this first pass. Show one short card on request, with the character remaining visible, and leave spoken facts opt-in.

## Content-aware reactions

See [content-reactions.md](content-reactions.md) for the parser-independent slot contract, 53 presets, automated coverage, and app integration plan. In Developer mode, use Content reaction preview to apply a preset to the current video. This is explicit input, not automatic title classification.

## Verified Cast app behavior (2026-10-25)

| App | Observed metadata | Display behavior |
| --- | --- | --- |
| YouTube | Title, content ID and playback timeline | Pixel YouTube mark, title and supported content reactions |
| Spotify | Track/artist and playback state | Pixel Spotify mark and listen-along |
| Fubo | Matchup title, playback state; live timeline varies | Pixel Fubo mark and sports parsing |
| HBO Max | “The Lego Batman Movie”, provider ID, playing position and duration | Pixel Max mark, title and progress; automatic movie genre lookup remains backlog |
| Prime Video (phone Cast) | PLAYING and duration, **no title** in this test | Pixel Prime mark and “Title unavailable”; no guessed movie identity, genre or progress |

These observations are specific to the tested receiver/app sessions, not a
promise that all titles or app versions expose the same fields. Title-less
active apps still show an app card. A one-time media-status request on app
transition helps when receiver and media callbacks arrive in the opposite
order; it does not continuously poll the TV.

App marks use the same small pixel drawing system as the existing YouTube
icon. Aliases are centralized in `pi.scene.MEDIA_APPS`; unknown apps retain the
TV icon. These are simplified pixel marks, not fetched official logo files.
The native display and preview share the same mapping. Receiver `icon_url`
is exposed for diagnostics but is not downloaded or rendered.

## Automatic general content classification

The parser now accepts normalized provider `metadata.kind` (`movie`/`episode`)
and genre labels. Cast's movie/TV metadata type and genre fields are retained when
present; providers frequently omit them. Explicit title format markers cover game
and film reviews, trailers, gameplay/esports, comedy/standup, music/concerts,
science, news, interviews/podcasts, tutorials, travel/food/fitness/nature/animals,
ASMR/relaxation, DIY, automotive, fashion, shorts and nonprofit content. These map
to the existing high-level reaction catalog and pixel-art props. Generic words
such as "highlights", "football", or "review" alone do not establish a subtype.

For unclassified titled movie/series receivers (Netflix, Prime Video, Max, Disney+,
Apple TV and Hulu), or a provider's explicit movie/episode metadata type, a
background Wikidata lookup can supply genres. It requires exact English labels
or aliases, a verified film/television work type, and a unique candidate; a year
suffix can distinguish remakes. Ambiguous/no-match results remain neutral. Positive
results persist for 30 days, misses for five minutes; transient errors retry after
two minutes. Wikimedia requests share pacing/backoff with team resolution. No
plots, scene events or spoilers are retrieved. A new work-type adapter can supply
normalized metadata without adding a title catalog or changing character drawing.
No automatic inference is possible when the TV provides no title.

`tests/test_content_coverage.py` uses representative **synthetic** titles across
11 sports, four receiver names, common formats and false positives. It is regression
coverage, not a measured real-world accuracy score. Existing renderer tests exercise
all presets/characters, playback states, missing assets and priority suppression.
Athlete portraits and automatic individual-athlete identity resolution remain
unsupported; tennis/combat titles can show names and the appropriate sport prop.
Live multi-app switching, unfamiliar teams, women/youth squads, and Pi visual/timing
review remain a separate human checklist in the GitHub roadmap.

Live cross-sport checks verified Boston Celtics, Kansas City Chiefs, Toronto Maple
Leafs, New York Yankees, Chennai Super Kings and Leinster Rugby. This exposed two
resolver fixes: probe an exact canonical page before relying on search ranking;
and accept sport-specific team/club/franchise types as evidence when generic sport
claims conflict. Existing sport/league checks and reserve-squad ambiguity guards
remain. A Celtics/Lakers NBA highlight fixture resolved both identities, fetched
and delivered both crests, and rendered on the Pi through the shared preview API.
These examples are validation results, not a hardcoded title/team registry.
