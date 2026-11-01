/* Web aplikacija Očitanje vode za suvlasnike (iPhone, Android, računalo).
   Koristi isti API kao Android aplikacija: /api/prijava/, /api/ja/, /api/ocitanja/ ... */
(function () {
  "use strict";

  const POSTAVKE = window.OCITANJE || {};
  const KLJUC_TOKENA = "ocitanje_token";
  const KLJUC_SKRIVENE_UPUTE = "ocitanje_bez_uputa";
  const MAKS_STRANICA_SLIKE = 1600;
  const ekran = document.getElementById("ekran");
  const izbornik = document.getElementById("izbornik");
  const izbornikGumb = document.getElementById("izbornik-gumb");

  let ja = null; // zadnji odgovor /api/ja/
  let ponudaInstalacije = null; // Chrome/Android: beforeinstallprompt

  // --- Pomoćne funkcije ---------------------------------------------------------------------------

  function spremi(kljuc, vrijednost) {
    try {
      if (vrijednost === null) localStorage.removeItem(kljuc); else localStorage.setItem(kljuc, vrijednost);
    } catch (e) { /* privatni način: prijava traje dok je aplikacija otvorena */ }
  }
  function procitaj(kljuc) {
    try { return localStorage.getItem(kljuc); } catch (e) { return null; }
  }
  let token = procitaj(KLJUC_TOKENA);

  function el(oznaka, svojstva, ...djeca) {
    const e = document.createElement(oznaka);
    for (const [k, v] of Object.entries(svojstva || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "klasa") e.className = v;
      else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
      else if (k === "tekst") e.textContent = v;
      else e.setAttribute(k, v === true ? "" : v);
    }
    for (const d of djeca.flat()) {
      if (d === null || d === undefined || d === false) continue;
      e.append(d instanceof Node ? d : document.createTextNode(String(d)));
    }
    return e;
  }

  function dodaj(roditelj, ...djeca) {
    roditelj.append(...djeca.flat().filter((d) => d !== null && d !== undefined && d !== false));
  }

  function prikazi(...djeca) {
    ekran.replaceChildren(...djeca.flat().filter(Boolean));
    window.scrollTo(0, 0);
  }

  function poruka(vrsta, tekst) {
    return el("div", {klasa: "poruka " + vrsta, role: vrsta === "greska" ? "alert" : "status"}, tekst);
  }

  function ucitavanje(tekst) {
    prikazi(el("div", {klasa: "ucitavanje"}, tekst || "Učitavanje…"));
  }

  const BROJ = new Intl.NumberFormat("hr-HR", {maximumFractionDigits: 3});
  function broj(v) {
    const n = Number(v);
    return Number.isFinite(n) ? BROJ.format(n) : "–";
  }
  function datum(iso) {
    if (!iso) return "";
    const [g, m, d] = iso.slice(0, 10).split("-");
    return `${Number(d)}.${Number(m)}.${g}.`;
  }
  function mjesec(razdoblje) {
    const [g, m] = (razdoblje || "").split("-");
    return m ? `${m}/${g}` : "";
  }

  function jeIos() {
    return /iPhone|iPad|iPod/.test(navigator.userAgent) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  }
  function jeInstalirana() {
    return window.navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;
  }

  // --- Poziv API-ja -------------------------------------------------------------------------------

  class GreskaApi extends Error {
    constructor(status, podaci) {
      super((podaci && (podaci.poruka || podaci.detail)) || "Nešto nije u redu. Pokušajte ponovno.");
      this.status = status;
      this.kod = podaci && podaci.kod;
      this.podaci = podaci;
    }
  }

  async function api(putanja, opcije) {
    opcije = opcije || {};
    const zaglavlja = {"Accept": "application/json"};
    if (token) zaglavlja["Authorization"] = "Token " + token;
    let tijelo = opcije.tijelo;
    if (tijelo && !(tijelo instanceof FormData)) {
      zaglavlja["Content-Type"] = "application/json";
      tijelo = JSON.stringify(tijelo);
    }
    let odgovor;
    try {
      odgovor = await fetch("/api/" + putanja, {
        method: opcije.metoda || "GET", headers: zaglavlja, body: tijelo, credentials: "omit", cache: "no-store",
      });
    } catch (e) {
      throw new GreskaApi(0, {poruka: "Nema veze s internetom. Provjerite mrežu i pokušajte ponovno."});
    }
    if (odgovor.status === 204) return null;
    let podaci = null;
    try { podaci = await odgovor.json(); } catch (e) { podaci = null; }
    if (odgovor.status === 401 && putanja !== "prijava/") {
      odjaviLokalno();
      prijava("Prijava je istekla. Prijavite se ponovno.");
      throw new GreskaApi(401, {kod: "neprijavljen", poruka: "Prijava je istekla."});
    }
    if (!odgovor.ok) {
      if (podaci && !podaci.poruka && typeof podaci === "object") {
        // Greške provjere polja iz DRF-a: {"novo_stanje": ["..."]}
        const prve = Object.values(podaci).flat().filter((x) => typeof x === "string");
        if (prve.length) podaci.poruka = prve.join(" ");
      }
      throw new GreskaApi(odgovor.status, podaci);
    }
    return podaci;
  }

  // --- Izbornik -----------------------------------------------------------------------------------

  function zatvoriIzbornik() {
    izbornik.hidden = true;
    izbornikGumb.setAttribute("aria-expanded", "false");
  }
  izbornikGumb.addEventListener("click", () => {
    izbornik.hidden = !izbornik.hidden;
    izbornikGumb.setAttribute("aria-expanded", String(!izbornik.hidden));
  });
  izbornik.addEventListener("click", (d) => {
    const cilj = d.target.closest("[data-idi]");
    if (!cilj) return;
    zatvoriIzbornik();
    const kamo = cilj.getAttribute("data-idi");
    if (kamo === "pocetna") pocetna();
    else if (kamo === "povijest") povijest();
    else if (kamo === "lozinka") promjenaLozinke(false);
    else if (kamo === "instalacija") uputeInstalacije(true);
    else if (kamo === "odjava") odjava();
  });
  function prikaziIzbornik(da) {
    izbornikGumb.hidden = !da;
    if (!da) zatvoriIzbornik();
  }

  // --- Upute za „Dodaj na početni zaslon” ---------------------------------------------------------

  const IKONA_DIJELI =
    '<svg class="dijeli" viewBox="0 0 18 22" aria-label="Dijeli" role="img"><path d="M9 1v12M5 5l4-4 4 4" ' +
    'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<path d="M6 8H3v13h12V8h-3" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>';

  function karticaInstalacije(uvijek) {
    if (jeInstalirana()) return null;
    if (!uvijek && procitaj(KLJUC_SKRIVENE_UPUTE)) return null;
    const kartica = el("div", {klasa: "kartica"});
    if (jeIos()) {
      const korak1 = el("li");
      korak1.innerHTML = "U Safariju dodirnite gumb <b>Dijeli</b> " + IKONA_DIJELI + " na dnu ekrana.";
      dodaj(kartica, 
        el("h2", {}, "Dodajte aplikaciju na početni zaslon"),
        el("ol", {klasa: "koraci"},
          korak1,
          el("li", {}, "Pomaknite popis prema dolje i odaberite ", el("b", {}, "Dodaj na početni zaslon"), "."),
          el("li", {}, "Dodirnite ", el("b", {}, "Dodaj"), ". Na početnom zaslonu pojavit će se ikona Očitanje vode."),
          el("li", {}, "Otvorite aplikaciju preko te ikone i prijavite se. Tada rade i podsjetnici na rok."),
        ),
        el("p", {klasa: "tiho"}, "Treba iOS 16.4 ili noviji za podsjetnike. Ako ne vidite gumb Dijeli, otvorite ovu stranicu u Safariju."),
      );
    } else if (ponudaInstalacije) {
      dodaj(kartica, 
        el("h2", {}, "Instalirajte aplikaciju"),
        el("p", {klasa: "tiho"}, "Aplikacija će se otvarati s početnog zaslona, kao i druge aplikacije."),
        el("button", {klasa: "gumb glavni", type: "button", onclick: async () => {
          ponudaInstalacije.prompt();
          await ponudaInstalacije.userChoice;
          ponudaInstalacije = null;
          kartica.remove();
        }}, "Instaliraj"),
      );
    } else if (uvijek) {
      dodaj(kartica, 
        el("h2", {}, "Dodajte aplikaciju na početni zaslon"),
        el("p", {}, "U izborniku preglednika (⋮ ili ⋯) odaberite „Dodaj na početni zaslon” ili „Instaliraj aplikaciju”."),
      );
    } else {
      return null;
    }
    if (!uvijek) {
      dodaj(kartica, el("button", {klasa: "gumb tihi", type: "button", onclick: () => {
        spremi(KLJUC_SKRIVENE_UPUTE, "1");
        kartica.remove();
      }}, "Sakrij"));
    }
    return kartica;
  }

  function uputeInstalacije() {
    const kartica = karticaInstalacije(true);
    prikazi(
      el("h1", {}, "Na početni zaslon"),
      kartica || poruka("uspjeh", "Aplikacija je već dodana na početni zaslon i otvorena kao aplikacija."),
      el("button", {klasa: "gumb", type: "button", onclick: pocetna}, "Natrag"),
    );
  }

  window.addEventListener("beforeinstallprompt", (d) => {
    d.preventDefault();
    ponudaInstalacije = d;
  });

  // --- Prijava i lozinka --------------------------------------------------------------------------

  function prijava(obavijest) {
    prikaziIzbornik(false);
    const greska = el("div");
    const ime = el("input", {id: "ime", name: "username", autocomplete: "username", autocapitalize: "none",
      autocorrect: "off", spellcheck: "false", required: true});
    const lozinka = el("input", {id: "lozinka", name: "password", type: "password", autocomplete: "current-password",
      required: true});
    const gumb = el("button", {klasa: "gumb glavni", type: "submit"}, "Prijava");
    const forma = el("form", {klasa: "kartica", onsubmit: async (d) => {
      d.preventDefault();
      gumb.disabled = true;
      greska.replaceChildren();
      try {
        const odgovor = await api("prijava/", {metoda: "POST", tijelo: {korisnicko_ime: ime.value.trim(), lozinka: lozinka.value}});
        token = odgovor.token;
        spremi(KLJUC_TOKENA, token);
        if (odgovor.mora_promijeniti_lozinku) promjenaLozinke(true);
        else pocetna();
      } catch (e) {
        greska.replaceChildren(poruka("greska", e.message));
        gumb.disabled = false;
      }
    }},
      el("label", {for: "ime"}, "Korisničko ime"), ime,
      el("label", {for: "lozinka"}, "Lozinka"), lozinka,
      gumb,
    );
    prikazi(
      el("h1", {}, "Prijava"),
      obavijest ? poruka("info", obavijest) : null,
      greska,
      forma,
      el("p", {klasa: "tiho"}, "Korisničko ime i lozinku dobili ste od ovlaštenog predstavnika suvlasnika. " +
        "Ako ste zaboravili lozinku, javite mu se da vam postavi novu."),
      karticaInstalacije(false),
    );
  }

  function promjenaLozinke(obavezno) {
    prikaziIzbornik(!obavezno);
    const greska = el("div");
    const stara = obavezno ? null : el("input", {id: "stara", type: "password", autocomplete: "current-password", required: true});
    const nova = el("input", {id: "nova", type: "password", autocomplete: "new-password", required: true, minlength: "8"});
    const ponovo = el("input", {id: "ponovo", type: "password", autocomplete: "new-password", required: true});
    const gumb = el("button", {klasa: "gumb glavni", type: "submit"}, "Spremi lozinku");
    prikazi(
      el("h1", {}, obavezno ? "Postavite svoju lozinku" : "Promjena lozinke"),
      obavezno ? poruka("info", "Lozinku vam je postavio ovlašteni predstavnik. Prije nastavka upišite svoju novu lozinku.") : null,
      greska,
      el("form", {klasa: "kartica", onsubmit: async (d) => {
        d.preventDefault();
        greska.replaceChildren();
        if (nova.value !== ponovo.value) {
          greska.replaceChildren(poruka("greska", "Lozinke se ne podudaraju."));
          return;
        }
        gumb.disabled = true;
        try {
          const tijelo = {nova_lozinka: nova.value};
          if (stara) tijelo.stara_lozinka = stara.value;
          await api("lozinka/", {metoda: "POST", tijelo});
          pocetna("Lozinka je promijenjena.");
        } catch (e) {
          greska.replaceChildren(poruka("greska", e.message));
          gumb.disabled = false;
        }
      }},
        stara ? [el("label", {for: "stara"}, "Trenutna lozinka"), stara] : null,
        el("label", {for: "nova"}, "Nova lozinka (barem 8 znakova)"), nova,
        el("label", {for: "ponovo"}, "Ponovite novu lozinku"), ponovo,
        gumb,
      ),
      obavezno ? null : el("button", {klasa: "gumb", type: "button", onclick: () => pocetna()}, "Odustani"),
    );
  }

  function odjaviLokalno() {
    token = null;
    ja = null;
    spremi(KLJUC_TOKENA, null);
  }

  async function odjava() {
    if (!window.confirm("Odjaviti se iz aplikacije? Podsjetnici na ovom uređaju se isključuju.")) return;
    try { await iskljuciObavijesti(); } catch (e) { /* nastavlja se s odjavom */ }
    try { await api("odjava/", {metoda: "POST"}); } catch (e) { /* token se ionako briše */ }
    odjaviLokalno();
    prijava("Odjavljeni ste.");
  }

  // --- Početni ekran ------------------------------------------------------------------------------

  function stanjeVodomjera(vodomjer) {
    const o = vodomjer.ocitanje_ovaj_mjesec;
    if (!o) return {oznaka: el("span", {klasa: "oznaka ne"}, "Nije očitano"), gumb: "Očitaj vodomjer"};
    if (o.status === "potvrdeno") {
      return {oznaka: el("span", {klasa: "oznaka potvrdeno"}, "Potvrđeno"), opis: `Predano stanje ${broj(o.novo_stanje)} m³`};
    }
    if (o.status === "odbijeno") {
      return {oznaka: el("span", {klasa: "oznaka odbijeno"}, "Odbijeno"),
        opis: "Predstavnik je odbio očitanje. Očitajte vodomjer ponovno.", gumb: "Očitaj ponovno"};
    }
    return {oznaka: el("span", {klasa: "oznaka predano"}, "Predano"),
      opis: `Predano stanje ${broj(o.novo_stanje)} m³, potrošnja ${broj(o.razlika)} m³. Dok ga predstavnik ne potvrdi, možete ga ispraviti.`,
      gumb: "Ispravi očitanje"};
  }

  function karticaStana(stan, zgrada, viseZgrada) {
    const kartica = el("section", {klasa: "kartica"},
      el("h2", {}, `Stan ${stan.broj_stana}`),
      viseZgrada && zgrada ? el("p", {klasa: "tiho"}, zgrada.adresa) : null,
    );
    if (!stan.vodomjeri.length) {
      dodaj(kartica, el("p", {klasa: "tiho"}, "Stan nema aktivni vodomjer. Javite se ovlaštenom predstavniku."));
    }
    for (const vodomjer of stan.vodomjeri) {
      const s = stanjeVodomjera(vodomjer);
      dodaj(kartica, 
        stan.vodomjeri.length > 1 ? el("p", {klasa: "tiho"}, `Vodomjer ${vodomjer.oznaka || vodomjer.serijski_broj}`) : null,
        el("div", {klasa: "red"},
          el("div", {}, el("div", {klasa: "tiho"}, "Prethodno stanje"), el("div", {klasa: "velik"}, `${broj(vodomjer.prethodno_stanje)} m³`)),
          s.oznaka,
        ),
        s.opis ? el("p", {klasa: "tiho"}, s.opis) : null,
        s.gumb ? el("button", {klasa: "gumb glavni", type: "button", onclick: () => ocitanje(stan, vodomjer, zgrada)}, s.gumb) : null,
      );
    }
    return kartica;
  }

  async function pocetna(obavijest) {
    if (!token) return prijava();
    prikaziIzbornik(true);
    ucitavanje();
    try {
      ja = await api("ja/");
    } catch (e) {
      if (e.status === 401) return;
      return prikazi(poruka("greska", e.message),
        el("button", {klasa: "gumb glavni", type: "button", onclick: () => pocetna()}, "Pokušaj ponovno"));
    }
    if (ja.mora_promijeniti_lozinku) return promjenaLozinke(true);
    const zgrade = new Map((ja.zgrade || []).map((z) => [z.id, z]));
    const d = new Date();
    const danas = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const rokovi = (ja.zgrade || []).map((z) => {
      const rok = z.podsjetnik && z.podsjetnik.rok;
      if (!rok) return null;
      const prosao = rok < danas;
      const tekst = (zgrade.size > 1 ? `${z.adresa}: ` : "") +
        (prosao ? `rok za očitanje bio je ${datum(rok)}` : `rok za očitanje je ${datum(rok)}`);
      return el("p", {klasa: prosao ? "" : "tiho"}, tekst.charAt(0).toUpperCase() + tekst.slice(1));
    });
    prikazi(
      el("h1", {}, ja.ime ? `Pozdrav, ${ja.ime}` : "Očitanje vode"),
      obavijest ? poruka("uspjeh", obavijest) : null,
      rokovi,
      ja.stanovi.length
        ? ja.stanovi.map((s) => karticaStana(s, zgrade.get(s.zgrada), zgrade.size > 1))
        : poruka("info", "Nemate upisan stan. Javite se ovlaštenom predstavniku suvlasnika."),
      karticaObavijesti(),
      karticaInstalacije(false),
    );
    uskladiPretplatu();
  }

  // --- Očitanje: fotografija i stanje -------------------------------------------------------------

  function smanjiSliku(datoteka) {
    // Fotografija s iPhonea ima i 5 MB; smanjena na 1600 px dovoljna je za provjeru, a šalje se brže.
    return new Promise((ok) => {
      const url = URL.createObjectURL(datoteka);
      const slika = new Image();
      slika.onload = () => {
        const omjer = Math.min(1, MAKS_STRANICA_SLIKE / Math.max(slika.naturalWidth, slika.naturalHeight));
        const platno = document.createElement("canvas");
        platno.width = Math.round(slika.naturalWidth * omjer);
        platno.height = Math.round(slika.naturalHeight * omjer);
        platno.getContext("2d").drawImage(slika, 0, 0, platno.width, platno.height);
        URL.revokeObjectURL(url);
        platno.toBlob((blob) => ok(blob || datoteka), "image/jpeg", 0.85);
      };
      slika.onerror = () => { URL.revokeObjectURL(url); ok(datoteka); };
      slika.src = url;
    });
  }

  function procitajBroj(tekst) {
    const t = (tekst || "").trim().replace(/\s/g, "").replace(",", ".");
    if (!/^\d{1,7}(\.\d{1,3})?$/.test(t)) return null;
    return t;
  }

  function ocitanje(stan, vodomjer, zgrada) {
    prikaziIzbornik(true);
    let fotografija = null;
    let urlPregleda = null;
    const prethodno = Number(vodomjer.prethodno_stanje);
    const greska = el("div");
    const pregled = el("div");
    const izKamere = el("input", {type: "file", accept: "image/*", capture: "environment", klasa: "skriveno", id: "kamera"});
    const izGalerije = el("input", {type: "file", accept: "image/*", klasa: "skriveno", id: "galerija"});
    const odabir = el("div", {},
      el("label", {for: "kamera", klasa: "kamera"}, el("span", {"aria-hidden": "true"}, "📷"), "Otvori kameru"),
      el("label", {for: "galerija", klasa: "gumb tihi"}, "Odaberi postojeću fotografiju"),
    );
    const stanje = el("input", {id: "stanje", klasa: "stanje", inputmode: "decimal", autocomplete: "off",
      placeholder: "npr. 1234,567", "aria-describedby": "potrosnja"});
    const potrosnja = el("p", {id: "potrosnja", klasa: "tiho"}, " ");
    const napomena = el("textarea", {id: "napomena", maxlength: "500", placeholder: "Nije obavezno"});
    const gumb = el("button", {klasa: "gumb glavni", type: "submit"}, "Pošalji očitanje");
    const postojece = vodomjer.ocitanje_ovaj_mjesec;
    if (postojece && postojece.status === "predano") stanje.value = String(postojece.novo_stanje).replace(".", ",");

    function osvjeziPotrosnju() {
      const b = procitajBroj(stanje.value);
      if (b === null) { potrosnja.textContent = " "; return; }
      const razlika = Number(b) - prethodno;
      potrosnja.textContent = razlika < 0
        ? `Upisano stanje je manje od prethodnog (${broj(prethodno)} m³). Provjerite broj.`
        : `Potrošnja ovaj mjesec: ${broj(razlika)} m³`;
    }
    stanje.addEventListener("input", osvjeziPotrosnju);
    osvjeziPotrosnju();

    async function odabrana(d) {
      const datoteka = d.target.files && d.target.files[0];
      d.target.value = "";
      if (!datoteka) return;
      greska.replaceChildren();
      pregled.replaceChildren(el("p", {klasa: "tiho"}, "Pripremam fotografiju…"));
      fotografija = await smanjiSliku(datoteka);
      if (urlPregleda) URL.revokeObjectURL(urlPregleda);
      urlPregleda = URL.createObjectURL(fotografija);
      pregled.replaceChildren(
        el("img", {klasa: "slika", src: urlPregleda, alt: "Fotografija vodomjera"}),
        el("label", {for: "kamera", klasa: "gumb tihi"}, "Fotografiraj ponovno"),
      );
      odabir.hidden = true;
      stanje.focus();
    }
    izKamere.addEventListener("change", odabrana);
    izGalerije.addEventListener("change", odabrana);

    async function posalji(potvrdiManje) {
      const b = procitajBroj(stanje.value);
      if (!fotografija) {
        greska.replaceChildren(poruka("greska", "Fotografirajte vodomjer tako da se vide svi brojevi."));
        return;
      }
      if (b === null) {
        greska.replaceChildren(poruka("greska", "Upišite stanje vodomjera brojkama, s najviše tri decimale (npr. 1234,567)."));
        stanje.focus();
        return;
      }
      const podaci = new FormData();
      podaci.append("vodomjer", vodomjer.id);
      podaci.append("novo_stanje", b);
      podaci.append("napomena", napomena.value.trim());
      podaci.append("fotografija", fotografija, "vodomjer.jpg");
      if (potvrdiManje) podaci.append("potvrdi_manje", "true");
      gumb.disabled = true;
      gumb.textContent = "Šaljem…";
      try {
        const o = await api("ocitanja/", {metoda: "POST", tijelo: podaci});
        if (urlPregleda) URL.revokeObjectURL(urlPregleda);
        potvrda(stan, o);
      } catch (e) {
        gumb.disabled = false;
        gumb.textContent = "Pošalji očitanje";
        if (e.kod === "manje_od_prethodnog" && !potvrdiManje) {
          if (window.confirm(e.message + "\n\nJe li upisani broj ipak točan? (npr. vodomjer je zamijenjen)")) posalji(true);
          return;
        }
        if (e.status !== 401) greska.replaceChildren(poruka("greska", e.message));
      }
    }

    prikazi(
      el("h1", {}, `Očitanje – stan ${stan.broj_stana}`),
      zgrada && ja && ja.zgrade.length > 1 ? el("p", {klasa: "tiho"}, zgrada.adresa) : null,
      greska,
      el("form", {klasa: "kartica", novalidate: true, onsubmit: (d) => { d.preventDefault(); posalji(false); }},
        el("h2", {}, "1. Fotografirajte vodomjer"),
        el("p", {klasa: "tiho"}, "Uhvatite cijeli brojčanik, ravno i bez odsjaja. Ako je mračno, upalite svjetlo."),
        pregled,
        izKamere, izGalerije,
        odabir,
        el("h2", {style: "margin-top:22px"}, "2. Upišite stanje"),
        el("p", {klasa: "tiho"}, `Prethodno stanje: ${broj(prethodno)} m³. Upišite crne brojke (kubike), a crvene kao decimale.`),
        stanje,
        potrosnja,
        el("label", {for: "napomena"}, "Napomena za predstavnika"),
        napomena,
        gumb,
      ),
      el("button", {klasa: "gumb", type: "button", onclick: () => pocetna()}, "Odustani"),
    );
  }

  function potvrda(stan, o) {
    const tekst = o.zakasnjelo
      ? "Očitanje je predano nakon roka, pa ga predstavnik vidi kao zakašnjelo."
      : "Predstavnik će ga provjeriti. Dok ga ne potvrdi, možete ga ispraviti.";
    prikazi(
      el("h1", {}, "Hvala!"),
      poruka("uspjeh", `Očitanje za stan ${stan.broj_stana} je predano.`),
      el("div", {klasa: "kartica"},
        el("div", {klasa: "red"}, el("span", {klasa: "tiho"}, "Stanje"), el("b", {}, `${broj(o.novo_stanje)} m³`)),
        el("div", {klasa: "red"}, el("span", {klasa: "tiho"}, "Potrošnja"), el("b", {}, `${broj(o.razlika)} m³`)),
        o.za_provjeru ? el("p", {klasa: "tiho", style: "margin-top:10px"}, "Potrošnja je veća nego inače, pa će je predstavnik posebno provjeriti.") : null,
        el("p", {klasa: "tiho", style: "margin-top:10px"}, tekst),
      ),
      el("button", {klasa: "gumb glavni", type: "button", onclick: () => pocetna()}, "Gotovo"),
    );
  }

  // --- Povijest -----------------------------------------------------------------------------------

  const STATUSI = {predano: "Predano", potvrdeno: "Potvrđeno", odbijeno: "Odbijeno"};

  async function povijest() {
    prikaziIzbornik(true);
    ucitavanje();
    let popis;
    try {
      popis = await api("ocitanja/");
    } catch (e) {
      if (e.status === 401) return;
      return prikazi(poruka("greska", e.message), el("button", {klasa: "gumb", type: "button", onclick: () => pocetna()}, "Natrag"));
    }
    prikazi(
      el("h1", {}, "Povijest očitanja"),
      popis.length
        ? el("div", {klasa: "kartica"}, el("ul", {klasa: "popis"}, popis.map((o) => el("li", {},
            el("div", {klasa: "red"}, el("b", {}, `${mjesec(o.razdoblje)} · stan ${o.broj_stana}`),
              el("span", {klasa: "oznaka " + o.status}, STATUSI[o.status] || o.status)),
            el("div", {klasa: "tiho"}, `Stanje ${broj(o.novo_stanje)} m³ · potrošnja ${broj(o.razlika)} m³` +
              (o.zakasnjelo ? " · zakašnjelo" : "")),
          ))))
        : poruka("info", "Još nema očitanja."),
      el("button", {klasa: "gumb", type: "button", onclick: () => pocetna()}, "Natrag"),
    );
  }

  // --- Obavijesti (podsjetnici na rok) ------------------------------------------------------------

  function pushPodrzan() {
    return "serviceWorker" in navigator && "PushManager" in window && "Notification" in window && POSTAVKE.vapid;
  }

  function kljucPosluzitelja() {
    const b64 = POSTAVKE.vapid.replace(/-/g, "+").replace(/_/g, "/");
    const niz = atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4));
    return Uint8Array.from(niz, (z) => z.charCodeAt(0));
  }

  async function registracija() {
    if (!("serviceWorker" in navigator)) return null;
    return navigator.serviceWorker.ready;
  }

  async function trenutnaPretplata() {
    if (!pushPodrzan()) return null;
    const reg = await registracija();
    return reg ? reg.pushManager.getSubscription() : null;
  }

  function opisUredaja() {
    const ua = navigator.userAgent;
    if (/iPhone/.test(ua)) return "iPhone";
    if (/iPad/.test(ua) || jeIos()) return "iPad";
    if (/Android/.test(ua)) return "Android";
    if (/Mac/.test(ua)) return "Mac";
    if (/Windows/.test(ua)) return "Windows";
    return "Preglednik";
  }

  async function ukljuciObavijesti() {
    const dopustenje = await Notification.requestPermission();
    if (dopustenje !== "granted") throw new Error("Obavijesti nisu dopuštene. Uključite ih u Postavkama → Obavijesti → Očitanje vode.");
    const reg = await registracija();
    let pretplata = await reg.pushManager.getSubscription();
    if (!pretplata) {
      pretplata = await reg.pushManager.subscribe({userVisibleOnly: true, applicationServerKey: kljucPosluzitelja()});
    }
    await api("obavijesti/pretplata/", {metoda: "POST", tijelo: {...pretplata.toJSON(), uredaj: opisUredaja()}});
  }

  async function iskljuciObavijesti() {
    const pretplata = await trenutnaPretplata();
    if (!pretplata) return;
    try { await api("obavijesti/pretplata/", {metoda: "DELETE", tijelo: {endpoint: pretplata.endpoint}}); } catch (e) { /* ništa */ }
    await pretplata.unsubscribe();
  }

  async function uskladiPretplatu() {
    // Poslužitelj zaboravlja pretplate koje push servis odbije; ovo ih obnavlja pri svakom otvaranju.
    try {
      const pretplata = await trenutnaPretplata();
      if (pretplata && Notification.permission === "granted") {
        await api("obavijesti/pretplata/", {metoda: "POST", tijelo: {...pretplata.toJSON(), uredaj: opisUredaja()}});
      }
    } catch (e) { /* nije bitno za rad aplikacije */ }
  }

  function karticaObavijesti() {
    const kartica = el("section", {klasa: "kartica"}, el("h2", {}, "Podsjetnici na rok"));
    if (!pushPodrzan()) {
      dodaj(kartica, el("p", {klasa: "tiho"}, jeIos() && !jeInstalirana()
        ? "Podsjetnici na iPhoneu rade kad aplikaciju dodate na početni zaslon i otvorite je preko ikone (iOS 16.4 ili noviji)."
        : "Ovaj preglednik ne podržava obavijesti. Podsjetnik ćete dobiti e-mailom ako je predstavnik to uključio."));
      return kartica;
    }
    const sadrzaj = el("div", {}, el("p", {klasa: "tiho"}, "Provjeravam…"));
    dodaj(kartica, sadrzaj);
    (async () => {
      const pretplata = await trenutnaPretplata().catch(() => null);
      const ukljuceno = pretplata && Notification.permission === "granted";
      if (ukljuceno) {
        const stanjeProbe = el("div");
        sadrzaj.replaceChildren(
          el("p", {}, "Uključeno. Obavijest stiže u dane podsjetnika dok vodomjer ne očitate."),
          stanjeProbe,
          el("button", {klasa: "gumb tihi", type: "button", onclick: async () => {
            try {
              await api("obavijesti/proba/", {metoda: "POST"});
              stanjeProbe.replaceChildren(poruka("uspjeh", "Probna obavijest je poslana. Trebala bi stići za nekoliko sekundi."));
            } catch (e) { stanjeProbe.replaceChildren(poruka("greska", e.message)); }
          }}, "Pošalji probnu obavijest"),
          el("button", {klasa: "gumb tihi", type: "button", onclick: async () => {
            await iskljuciObavijesti().catch(() => null);
            kartica.replaceWith(karticaObavijesti());
          }}, "Isključi podsjetnike"),
        );
      } else if (Notification.permission === "denied") {
        sadrzaj.replaceChildren(el("p", {klasa: "tiho"},
          "Obavijesti su zabranjene. Uključite ih u Postavkama mobitela → Obavijesti → Očitanje vode, pa otvorite aplikaciju ponovno."));
      } else {
        const greska = el("div");
        sadrzaj.replaceChildren(
          el("p", {klasa: "tiho"}, "Dobit ćete obavijest na mobitel kad je vrijeme za očitanje, ako vodomjer još niste očitali."),
          greska,
          el("button", {klasa: "gumb glavni", type: "button", onclick: async (d) => {
            d.target.disabled = true;
            try {
              await ukljuciObavijesti();
              kartica.replaceWith(karticaObavijesti());
            } catch (e) {
              d.target.disabled = false;
              greska.replaceChildren(poruka("greska", e.message));
            }
          }}, "Uključi podsjetnike"),
        );
      }
    })();
    return kartica;
  }

  // --- Pokretanje ---------------------------------------------------------------------------------

  if ("serviceWorker" in navigator && POSTAVKE.sw) {
    navigator.serviceWorker.register(POSTAVKE.sw, {scope: "/app/"}).catch(() => { /* aplikacija radi i bez njega */ });
  }
  if (token) pocetna(); else prijava();
})();
