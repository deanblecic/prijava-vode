/* Service worker web aplikacije Očitanje vode (verzija {{ verzija }}).
   Sprema ljusku aplikacije da se otvara i bez mreže te prikazuje podsjetnike (Web Push).
   Podaci s /api/ se nikad ne spremaju. */
const SPREMNIK = "ocitanje-vode-{{ verzija }}";
const LJUSKA = ["/app/", "/app/manifest.webmanifest"{% for d in datoteke %}, "{{ d|escapejs }}"{% endfor %}];

self.addEventListener("install", (dogadaj) => {
  dogadaj.waitUntil(
    caches.open(SPREMNIK).then((s) => s.addAll(LJUSKA)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (dogadaj) => {
  dogadaj.waitUntil(
    caches.keys()
      .then((imena) => Promise.all(
        imena.filter((ime) => ime.startsWith("ocitanje-vode-") && ime !== SPREMNIK).map((ime) => caches.delete(ime))
      ))
      .then(() => self.clients.claim())
  );
});

function zaLjusku(url) {
  return url.origin === self.location.origin &&
    (url.pathname === "/app/" || url.pathname === "/app/manifest.webmanifest" || url.pathname.startsWith("/static/app/"));
}

// Prvo mreža (da se izmjene vide odmah), a bez mreže spremljena kopija.
self.addEventListener("fetch", (dogadaj) => {
  const zahtjev = dogadaj.request;
  if (zahtjev.method !== "GET") return;
  const url = new URL(zahtjev.url);
  if (!zaLjusku(url)) return;
  const kljuc = url.pathname.startsWith("/static/") ? url.pathname : zahtjev;
  dogadaj.respondWith(
    fetch(zahtjev)
      .then((odgovor) => {
        if (odgovor.ok) {
          const kopija = odgovor.clone();
          caches.open(SPREMNIK).then((s) => s.put(kljuc, kopija));
        }
        return odgovor;
      })
      .catch(() => caches.match(kljuc, {ignoreSearch: true}).then((s) => s || caches.match("/app/")))
  );
});

self.addEventListener("push", (dogadaj) => {
  let podaci = {};
  try { podaci = dogadaj.data ? dogadaj.data.json() : {}; } catch (e) { podaci = {tekst: dogadaj.data && dogadaj.data.text()}; }
  const naslov = podaci.naslov || "Očitanje vode";
  dogadaj.waitUntil(self.registration.showNotification(naslov, {
    body: podaci.tekst || "Vrijeme je za očitanje vodomjera.",
    icon: "{{ datoteke.2|escapejs }}",
    badge: "{{ datoteke.2|escapejs }}",
    tag: podaci.oznaka || "podsjetnik",
    data: {url: podaci.url || "/app/"},
  }));
});

self.addEventListener("notificationclick", (dogadaj) => {
  dogadaj.notification.close();
  const cilj = new URL((dogadaj.notification.data && dogadaj.notification.data.url) || "/app/", self.location.origin);
  dogadaj.waitUntil(
    self.clients.matchAll({type: "window", includeUncontrolled: true}).then((prozori) => {
      for (const prozor of prozori) {
        if (new URL(prozor.url).pathname.startsWith("/app/") && "focus" in prozor) return prozor.focus();
      }
      return self.clients.openWindow(cilj.href);
    })
  );
});
