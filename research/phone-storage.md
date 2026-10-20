# Phone storage: how safe is browser data on iPhone and Android?

Research for issue #23 (20 Oct 2026). Setup we are checking: a static page on GitHub Pages, phone only, all data in
the phone's browser, installable as a home-screen app (PWA), manual Backup (save one JSON file) / Restore (pick the file).
Two parts on the same site: `/live` and `/demo`.

## Short answer

- **Browser data is "mostly safe, never guaranteed".** Treat the backup file as the real copy, the phone as a working copy.
- **iPhone, plain Safari tab: the big risk.** Safari wipes ALL site data (localStorage, IndexedDB, service worker) after
  7 days of use of Safari without the user touching the site. So the app must be used from the home screen.
- **iPhone, home-screen app: much safer.** It has its own storage and its own 7-day counter that only counts days the
  app itself is used, so opening it at least once a week keeps it. Deleting the icon deletes its data. Data typed in
  the Safari tab does NOT move into the home-screen app (separate storage): set up after installing, or restore a backup.
- **Android Chrome (tab or installed): safe in normal use.** Chrome only deletes when the phone runs out of space (least
  recently used site first) or when the user clears site data. Installed apps are almost always granted `persist()`,
  which protects even from the out-of-space clean-up.
- **`navigator.storage.persist()`: call it on both.** Chrome grants it silently for installed / often-used sites. Safari 17+
  supports it and uses "opened as a home-screen app" as one reason to grant it. Neither shows a prompt. It never protects
  against the user clearing data or deleting the app.
- **Use IndexedDB, not localStorage.** Both are wiped together by the same rules, but IndexedDB is far bigger, async and
  transactional (no half-written saves). localStorage is ~5 MB of strings and fine only for tiny settings.
- **Backup file: works on all three, with one trick.** Android: `<a download>` with a Blob saves to Downloads.
  iPhone: the Share sheet (`navigator.share({files})`) is the reliable way, especially in the home-screen app (Save to
  Files, Google Drive, Mail); `<a download>` works in the Safari tab but is flaky inside the home-screen app. Restore with
  `<input type="file">` works everywhere (Files, iCloud Drive, Google Drive, Downloads).
- **GitHub Pages catch:** every project site of one account shares ONE origin (`user.github.io`). Any other page on that
  account can read the data, and they share quota and wipes. Keep only this app on that account, or use a custom domain.

## Risk → what we do about it

| Risk | Where | What we do about it |
| --- | --- | --- |
| 7-day wipe when used in a Safari tab | iPhone Safari | Tell the user to install to the home screen and use only the icon. Show a banner in a plain Safari tab (`navigator.standalone` is false): "Add to Home Screen or your data can vanish". |
| 7-day wipe of the home-screen app if not opened for 7+ days of use | iPhone PWA | Fine for a daily money app. Show "Last backup: N days ago" and nag after 7 days. |
| Data typed in Safari tab is not in the home-screen app | iPhone | First run inside the installed app; if the user started in Safari: Backup there, Restore in the app. |
| User deletes the home-screen icon | iPhone (data gone), Android (may be kept in Chrome, do not rely on it) | Warning in the help text; backup reminder. |
| Phone low on space: browser deletes least-used sites | Both | Call `navigator.storage.persist()` at start (and again after install / on a tap). Show the result ("Protected: yes/no") on a settings line. |
| User clears history / site data / app storage | Both (Safari: Settings > Safari > Clear History and Website Data; Chrome: Clear browsing data > site data) | Nothing can stop it: backup file + "Last backup" reminder. |
| Private / Incognito tab: data lives only for that session | Both | Detect very small `estimate().quota` or failed writes and show "Private tab: nothing is kept". Tell the user not to use private tabs. |
| Half-written save (app closed mid-write) | Both | IndexedDB: one transaction per change, so it saves fully or not at all. |
| Running out of room | Both | Not a real risk: a few years of spends is well under 1 MB. Quota is huge (Chrome up to 60% of disk per site; Safari 17+ up to 60% per origin in Safari, 15% in other apps). Show `navigator.storage.estimate()` usage on settings for peace of mind. |
| `/live` and `/demo` mixing data (same origin) | Both | Separate IndexedDB databases (`ft-live`, `ft-demo`) and prefixed localStorage keys (`ft-live:`, `ft-demo:`). Backup file says which one it came from; Restore refuses a demo file in live (or asks). Give each its own manifest `id`, `start_url` and `scope` (`/live/`, `/demo/`) and its own service worker scope. |
| Other pages on `user.github.io` share the origin | Both | Use a dedicated GitHub account/org for this app only, or a custom domain. Never put other experiments on the same account. |
| Backup download does nothing / navigates away inside iPhone home-screen app | iPhone PWA | Use the Share sheet first: `navigator.canShare({files:[file]})` then `navigator.share({files:[file]})`, called straight from the button tap. Fall back to `<a download>` with a Blob URL. |
| Share sheet refuses a `.json` file | Android Chrome (only listed file types can be shared; JSON is not clearly on the list) | Always check `canShare` first. If it says no, use `<a download>` (Android saves to Downloads, works well). Option: share as `text/plain` with a `.txt` name; Restore accepts both. |
| Restore picker greys out the file | iPhone | Do not over-restrict `accept`; use `accept=".json,.txt,application/json,text/plain"` or none, and check the content in code (version field, app name). |
| Backup file is readable by anyone who gets it | Both | It holds money data in plain text. Say so; option later: password-encrypt with Web Crypto. |

## Platform notes

### iPhone (Safari / WebKit, all iOS browsers use it)
- **7-day rule (ITP, since iOS 13.4):** after 7 days of Safari use with no interaction on the site, WebKit deletes all
  script-writable storage: IndexedDB, localStorage, sessionStorage, service worker registrations and Cache.
  Home-screen web apps are not part of Safari: they have their own counter of days of use, which matches real use of the
  app. web.dev: the policy does not apply to installed PWAs added to the home screen in the same way. Reports exist of
  home-screen apps still losing cookies after 7 days, so a backup habit is still needed.
- **Separate storage:** a home-screen app's storage is separate from Safari's (nothing carries over either way).
- **Quota (Safari 17 / iOS 17+):** origin quota up to 60% of disk for browser apps, 15% for other apps; overall up to
  80% / 20%. No more "use more space?" prompts. Over the overall quota, WebKit evicts whole origins, least recently used
  first; persistent origins are skipped.
- **`persist()` / `estimate()`:** supported since Safari 17. Granted or refused without a prompt, using heuristics; being
  opened as a home-screen web app is one of them. Not documented to override the 7-day rule, so ask on every start.
- **Private browsing:** storage is temporary and goes when the private session ends.

### Android (Chrome)
- **No time limit.** Data stays until the device is short of space (Chrome evicts best-effort sites, least recently used
  first) or the user clears it. Chrome's own research: eviction of regularly visited sites is very rare.
- **Quota:** up to 60% of disk per origin (best-effort), `estimate()` reports it.
- **`persist()`:** granted automatically, no prompt, based on engagement, being installed or bookmarked, or having
  notification permission. Installed PWAs are typically granted. Persistent data is only removed by the user.
- **Incognito:** data is in memory/temporary and deleted when Incognito closes; quota is small.
- An installed PWA uses the same storage as the site in Chrome (same origin).

### localStorage vs IndexedDB
| | localStorage | IndexedDB |
| --- | --- | --- |
| Size | ~5 MB per origin (strings only) | Shares the big origin quota (GBs) |
| Speed | Synchronous: blocks the page | Async |
| Safety | No transactions; a crash mid-save can leave mixed data | Transactions: all or nothing |
| Wiped by 7-day rule / clearing / eviction | Yes | Yes (same rules) |
| Verdict | Small settings only (e.g. folded cards) | All money data |

Use a tiny wrapper (or the `idb` library from a pinned CDN URL) so the code stays simple.

### Backup and restore
- **Download:** `const url = URL.createObjectURL(new Blob([json], {type:'application/json'}));` then a temporary
  `<a href=url download="money-backup-2026-10-20.json">` clicked inside the tap handler.
  Android Chrome: saves to Downloads. iPhone Safari tab (iOS 13+): asks, then saves to Files > Downloads.
  iPhone home-screen app: unreliable (blob may open a viewer with a Share button, or do nothing; some iOS versions had
  blob bugs, e.g. 17.4.1). Never point the link at a same-scope URL: it can navigate the app window away with no way back.
- **Share sheet:** `navigator.share({files:[new File([json], name, {type})], title})` must run directly from a tap.
  Safari 15+ shares files (Save to Files, Google Drive, Mail, AirDrop). Chrome Android shares files, but only allowed
  types (images, audio, video, PDF, some text); check `navigator.canShare({files})` first, it can still fail, so catch
  errors and fall back to download. `AbortError` = user cancelled, not a failure.
- **Restore:** `<input type="file">` opens the system picker on both (iPhone: Files / iCloud Drive / Google Drive if
  installed; Android: Downloads / Drive). Read with `file.text()`, `JSON.parse`, check app name + version + live/demo,
  show a summary ("142 spends, last 18 Oct"), confirm, then replace in one IndexedDB transaction.
- **Recommended button order:** iPhone = "Share backup" (main) + "Download" (small); Android = "Download" (main) +
  "Share" if `canShare` says yes.

### What to test on real phones before deciding
1. iPhone home-screen app: Share sheet with a `.json` file and with a `.txt` file; Save to Files; Restore from Files.
2. iPhone: `navigator.storage.persist()` result in the Safari tab vs the home-screen app.
3. Android Chrome installed: `persist()` result; download lands in Downloads; Share to Drive with `.json`.

## Sources
- WebKit, Updates to Storage Policy (Safari 17 quotas, persist, home-screen heuristic): https://webkit.org/blog/14403/updates-to-storage-policy/
- WebKit, Full Third-Party Cookie Blocking and More (7-day cap; home-screen apps have their own counter): https://webkit.org/blog/10218/full-third-party-cookie-blocking-and-more/
- WebKit Features in Safari 17.0: https://webkit.org/blog/14445/webkit-features-in-safari-17-0/
- MDN, Storage quotas and eviction criteria: https://developer.mozilla.org/en-US/docs/Web/API/Storage_API/Storage_quotas_and_eviction_criteria
- MDN, Storage API: https://developer.mozilla.org/docs/Web/API/Storage_API
- MDN issue, Safari storage quota accuracy: https://github.com/mdn/content/issues/40394
- web.dev, Storage for the web: https://web.dev/articles/storage-for-the-web
- web.dev, Persistent storage: https://web.dev/articles/persistent-storage
- web.dev, Web Share API: https://web.dev/articles/web-share
- web.dev, How to share files: https://web.dev/articles/files/share-files
- Apple Developer Forums, Safari iOS PWA data persistence beyond 7 days: https://developer.apple.com/forums/thread/710157
- Apple Developer Forums, Blob URLs not working on iOS 17.4.1: https://developer.apple.com/forums/thread/751063
- Apple Developer Forums, Download locally generated text in a PWA: https://developer.apple.com/forums/thread/119017
- WebKit Bugzilla 237350 (home-screen app cookies cleared after 7 days): https://bugs.webkit.org/show_bug.cgi?id=237350
- Example: PDF download in an installed iOS PWA (blob viewer vs share): https://github.com/kerti/uruni/issues/475
- The Register, Apple clarification on home-screen apps (2020): https://www.theregister.com/2020/03/26/apple_relax_were_not_totally

Note: webkit.org, MDN and web.dev could not be opened directly from the research machine (network block); their content
was taken from search-engine extracts of those pages. The "what to test" list covers the points that sources leave open.
