const svg = d3.select("#world-map");
const atlasStage = document.querySelector(".atlas-stage");
const hotspotPopup = document.getElementById("hotspot-popup");
const popupLabel = document.getElementById("popup-label");
const popupConflict = document.getElementById("popup-conflict");
const popupCountries = document.getElementById("popup-countries");
const popupMarket = document.getElementById("popup-market");
const popupLink = document.getElementById("popup-link");

const connectorLayer = document.getElementById("connector-layer");

let hotspotHideTimer = null;

function cancelHotspotHide() {
  if (hotspotHideTimer) {
    clearTimeout(hotspotHideTimer);
    hotspotHideTimer = null;
  }
}

function scheduleHotspotHide() {
  cancelHotspotHide();
  hotspotHideTimer = setTimeout(() => closeHotspotPopup(), 220);
}

hotspotPopup.addEventListener("mouseenter", cancelHotspotHide);
hotspotPopup.addEventListener("mouseleave", scheduleHotspotHide);
const mapStatus = document.getElementById("map-status");
const conflictToggle = document.getElementById("conflict-toggle");
const importantToggle = document.getElementById("important-toggle");
const aiPicksToggle = document.getElementById("ai-picks-toggle");
const carrierToggle = document.getElementById("carrier-toggle");
const countrySheet = document.getElementById("country-sheet");
const closeButton = document.getElementById("sheet-close");
const detailCountry = document.getElementById("detail-country");
const detailRegion = document.getElementById("detail-region");
const detailDemocracyLabel = document.getElementById("detail-democracy-label");
const detailDemocracyIndex = document.getElementById("detail-democracy-index");
const detailEconomicGrowthLabel = document.getElementById("detail-economic-growth-label");
const detailEconomicGrowth = document.getElementById("detail-economic-growth");
const detailConflictLabel = document.getElementById("detail-conflict-label");
const detailConflict = document.getElementById("detail-conflict");
const factStrip = document.querySelector(".fact-strip");
const spotContext = document.getElementById("spot-context");
const storySectionLabel = document.getElementById("story-section-label");
const storyList = document.getElementById("story-list");

const sampleCountryData = window.appData.countries;
const fallbackImportantSpots = window.appData.importantSpots || [];
const sampleCountryByName = new Map(
  Object.values(sampleCountryData).map((country) => [country.name, country]),
);
const countryNameAliases = new Map([["United States of America", "United States"]]);

let projection;
let path;
let sphereLayer;
let countryLayer;
let borderLayer;
let graticuleLayer;
let hotspotLayer;
let importantLayer;
let aiPicksLayer;
let carrierLayer;
let features = [];
let borders;
let lastTimestamp = 0;
let autoRotate = true;
let activeFeatureId = null;
let activeSpotId = null;
let countryStore = new Map();
let activeSheetRequestId = 0;
let activeSheetKey = "";
let countryPaths;
let conflictHoverRoles = new Map();
let metricHoverMode = null;
let conflictHotspots = [];
let hotspotNodes;
let showConflictHotspots = false;
let importantSpots = [];
let importantSpotNodes;
let showImportantSpots = true;
let aiPicks = [];
let aiPickNodes;
let showAiPicks = true;
let carrierSpots = [];
let carrierSpotNodes;
let showCarrierSpots = false;

function getCanonicalCountryName(countryName) {
  return countryNameAliases.get(countryName) || countryName;
}

function getDefaultMapStatus() {
  if (activeFeatureId !== null) {
    const activeFeature = features.find((feature) => feature.id === activeFeatureId);
    if (activeFeature) {
      return activeFeature.properties.name;
    }
  }
  return "Drag the globe. Click a country.";
}

function syncConflictToggle() {
  conflictToggle.classList.toggle("is-active", showConflictHotspots);
  conflictToggle.setAttribute("aria-pressed", String(showConflictHotspots));
}

function syncImportantToggle() {
  importantToggle.classList.toggle("is-active", showImportantSpots);
  importantToggle.setAttribute("aria-pressed", String(showImportantSpots));
}

function syncAiPicksToggle() {
  aiPicksToggle.classList.toggle("is-active", showAiPicks);
  aiPicksToggle.setAttribute("aria-pressed", String(showAiPicks));
}

function syncCarrierToggle() {
  carrierToggle.classList.toggle("is-active", showCarrierSpots);
  carrierToggle.setAttribute("aria-pressed", String(showCarrierSpots));
}

function isInteractiveElement(target) {
  return Boolean(
    target?.closest?.(
      ".country, .conflict-hotspot, .important-spot, .ai-pick, .carrier-spot, .country-sheet, .layer-switches, .hotspot-popup",
    ),
  );
}

function createBaseCountry(countryName) {
  return {
    name: getCanonicalCountryName(countryName),
    region: "Briefing not populated yet",
    tagline:
      "The globe is wired for this country. News and conflict details will fill in as the live pipeline expands.",
    democracyIndex: "Pending score source",
    economicGrowth: "No recent World Bank data",
    economicGrowthValue: null,
    economicGrowthYear: null,
    conflict: "Pending live metadata",
    conflicts: [],
    stories: [
      {
        source: "System",
        time: "Now",
        title: "Country record created successfully",
        summary:
          "This is the scalable base state for countries that do not yet have a populated briefing. The next pass attaches live sources.",
        tags: ["Country", "Pending"],
      },
    ],
  };
}

function getDemocracyBucketColor(bucket) {
  switch (bucket) {
    case "70+":
      return "#7ee6b8";
    case "60-70":
      return "#4dd2c2";
    case "50-60":
      return "#d8b06a";
    case "<50":
      return "#b96b63";
    default:
      return "#355261";
  }
}

function getEconomicGrowthColor(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "#355261";
  }
  if (value >= 5) {
    return "#7ee6b8";
  }
  if (value >= 2) {
    return "#4dd2c2";
  }
  if (value >= 0) {
    return "#d8b06a";
  }
  if (value >= -2) {
    return "#c97a65";
  }
  return "#b55f68";
}

function getMetricFill(feature) {
  const record = getCountryRecord(feature.properties.name);
  if (metricHoverMode === "democracy") {
    return getDemocracyBucketColor(record.democracyIndex);
  }
  if (metricHoverMode === "growth") {
    return getEconomicGrowthColor(record.economicGrowthValue);
  }
  return "#355261";
}

function getConflictRoleColor(role) {
  switch (role) {
    case "ally":
      return "#d4a15c";
    case "enemy":
      return "#b55f68";
    case "secondary":
      return "#8f657c";
    default:
      return null;
  }
}

function mergeRole(existingRole, nextRole) {
  const priority = { enemy: 3, ally: 2, secondary: 1 };
  if (!existingRole) {
    return nextRole;
  }
  return priority[nextRole] > priority[existingRole] ? nextRole : existingRole;
}

function syncCountryClasses() {
  if (!countryPaths) {
    return;
  }

  countryPaths
    .classed("is-active", (feature) => feature.id === activeFeatureId)
    .classed("is-conflict-ally", (feature) => conflictHoverRoles.get(feature.properties.name) === "ally")
    .classed("is-conflict-enemy", (feature) => conflictHoverRoles.get(feature.properties.name) === "enemy")
    .classed("is-conflict-secondary", (feature) => conflictHoverRoles.get(feature.properties.name) === "secondary")
    .classed("is-democracy-hover", () => metricHoverMode !== null)
    .style("fill", (feature) => {
      if (metricHoverMode) {
        return getMetricFill(feature);
      }
      if (feature.id === activeFeatureId) {
        return "";
      }
      const role = conflictHoverRoles.get(feature.properties.name);
      return role ? getConflictRoleColor(role) : "";
    })
    .style("stroke", (feature) => {
      if (metricHoverMode) {
        return "rgba(228, 244, 255, 0.24)";
      }
      const role = conflictHoverRoles.get(feature.properties.name);
      if (role === "enemy") {
        return "rgba(255, 220, 215, 0.55)";
      }
      if (role === "ally") {
        return "rgba(247, 229, 197, 0.5)";
      }
      if (role === "secondary") {
        return "rgba(233, 210, 222, 0.4)";
      }
      return "";
    })
    .style("filter", (feature) => {
      if (metricHoverMode && feature.id !== activeFeatureId) {
        return "drop-shadow(0 0 8px rgba(243, 239, 230, 0.08))";
      }
      const role = conflictHoverRoles.get(feature.properties.name);
      if (role === "enemy") {
        return "drop-shadow(0 0 12px rgba(255, 138, 101, 0.28))";
      }
      if (role === "ally") {
        return "drop-shadow(0 0 12px rgba(216, 168, 95, 0.22))";
      }
      if (role === "secondary") {
        return "drop-shadow(0 0 10px rgba(143, 101, 124, 0.18))";
      }
      return "";
    });
}

function setConflictHover(roleMap) {
  metricHoverMode = null;
  conflictHoverRoles = new Map(roleMap);
  syncCountryClasses();
}

function clearConflictHover() {
  conflictHoverRoles.clear();
  syncCountryClasses();
}

function setMetricHover(mode) {
  conflictHoverRoles.clear();
  metricHoverMode = mode;
  syncCountryClasses();
}

function bindConflictHoverHandlers(element, roleMap) {
  element.onmouseenter = () => setConflictHover(roleMap);
  element.onmouseleave = () => clearConflictHover();
  element.onfocus = () => setConflictHover(roleMap);
  element.onblur = () => clearConflictHover();
}

function uniqueCountryNames(countryNames) {
  return [...new Set(countryNames.filter(Boolean))];
}

function getConflictPeerCountries(conflictCountries, currentCountryName) {
  return uniqueCountryNames((conflictCountries || []).filter((name) => name !== currentCountryName));
}

function buildConflictRoleMap(conflict, currentCountryName) {
  const roleMap = new Map();
  const sides = Array.isArray(conflict.sides) ? conflict.sides : [];
  const selectedSideIndex = sides.findIndex((side) => (side.countries || []).includes(currentCountryName));

  if (selectedSideIndex >= 0) {
    for (const countryName of sides[selectedSideIndex].countries || []) {
      if (countryName !== currentCountryName) {
        roleMap.set(countryName, "ally");
      }
    }

    sides.forEach((side, index) => {
      if (index === selectedSideIndex) {
        return;
      }
      for (const countryName of side.countries || []) {
        if (countryName !== currentCountryName) {
          roleMap.set(countryName, mergeRole(roleMap.get(countryName), "enemy"));
        }
      }
    });

    const sideCountries = new Set(sides.flatMap((side) => side.countries || []));
    for (const countryName of conflict.countries || []) {
      if (countryName !== currentCountryName && !sideCountries.has(countryName)) {
        roleMap.set(countryName, mergeRole(roleMap.get(countryName), "secondary"));
      }
    }
    return roleMap;
  }

  for (const countryName of getConflictPeerCountries(conflict.countries || [], currentCountryName)) {
    roleMap.set(countryName, "secondary");
  }
  return roleMap;
}

function mergeRoleMaps(roleMaps) {
  const merged = new Map();
  for (const roleMap of roleMaps) {
    for (const [countryName, role] of roleMap.entries()) {
      merged.set(countryName, mergeRole(merged.get(countryName), role));
    }
  }
  return merged;
}

function renderConflictDetails(selected) {
  detailConflict.replaceChildren();
  detailConflictLabel.onmouseenter = null;
  detailConflictLabel.onmouseleave = null;
  detailConflictLabel.onfocus = null;
  detailConflictLabel.onblur = null;
  detailConflictLabel.classList.remove("is-hoverable");

  if (Array.isArray(selected.conflicts) && selected.conflicts.length > 0) {
    const allRoles = mergeRoleMaps(
      selected.conflicts.map((conflict) => buildConflictRoleMap(conflict, selected.name)),
    );

    detailConflictLabel.classList.add("is-hoverable");
    bindConflictHoverHandlers(detailConflictLabel, allRoles);

    for (const conflict of selected.conflicts) {
      const item = document.createElement("div");
      item.className = "conflict-item";

      const roleMap = buildConflictRoleMap(conflict, selected.name);
      const entry = conflict.url ? document.createElement("a") : document.createElement("span");
      entry.className = "conflict-link";
      entry.textContent = conflict.name;
      bindConflictHoverHandlers(entry, roleMap);

      if (entry instanceof HTMLAnchorElement) {
        entry.href = conflict.url;
        entry.target = "_blank";
        entry.rel = "noreferrer";
      }

      item.appendChild(entry);
      detailConflict.appendChild(item);
    }
    return;
  }

  const fallback = document.createElement("div");
  fallback.className = "conflict-empty";
  fallback.textContent = selected.conflict || "No live conflict listing";
  detailConflict.appendChild(fallback);
}

function showCountryFacts() {
  factStrip.hidden = false;
  spotContext.classList.add("is-hidden");
  spotContext.replaceChildren();
  storySectionLabel.textContent = "Recent stories";
}

function showSpotFacts() {
  factStrip.hidden = true;
  storySectionLabel.textContent = "Current coverage";
}

function showAiPickFacts() {
  factStrip.hidden = true;
  storySectionLabel.textContent = "Source trail";
}

function renderMarketCard(cardRoot, marketCard, compact = false) {
  cardRoot.replaceChildren();
  if (!marketCard) {
    cardRoot.classList.add("is-hidden");
    return;
  }

  const marketUrl = safeExternalUrl(marketCard.url);
  const card = document.createElement("article");
  card.className = compact ? "market-card market-card--compact" : "market-card";
  card.innerHTML = `
    <p class="market-card__kicker">Market Signal</p>
    <h3 class="market-card__title">${escapeHtml(marketCard.title)}</h3>
    <p class="market-card__prediction">Current prediction: <span>${escapeHtml(marketCard.yesProbability)}</span></p>
    ${
      marketUrl
        ? `<a class="market-card__link" href="${marketUrl}" target="_blank" rel="noreferrer">Open Polymarket</a>`
        : ""
    }
  `;
  cardRoot.appendChild(card);
  cardRoot.classList.remove("is-hidden");
}

function renderSpotContext(spotBriefing) {
  renderMarketCard(spotContext, spotBriefing.marketCard);
}

function formatOverlapLabel(overlap) {
  const type = String(overlap?.type || "").replace(/-/g, " ");
  const label = overlap?.label || "Related coverage";
  return type ? `Also in ${type}: ${label}` : `Also covered: ${label}`;
}

function renderAiPickContext(pick) {
  spotContext.replaceChildren();
  const card = document.createElement("article");
  const overlaps = Array.isArray(pick.overlap) ? pick.overlap : [];
  const metaItems = [
    pick.freshness,
    pick.category || "Global story",
    `Importance ${Math.round((pick.importance || 0) * 100)}%`,
    `Location confidence ${Math.round((pick.confidence || 0) * 100)}%`,
    ...overlaps.map(formatOverlapLabel),
  ].filter(Boolean);
  card.className = "ai-context-card";
  card.innerHTML = `
    <p class="ai-context-card__kicker">Underlooked AI pick</p>
    ${pick.angle ? `<p class="ai-context-card__angle">${escapeHtml(pick.angle)}</p>` : ""}
    <p class="ai-context-card__body">${escapeHtml(pick.whyItMatters || pick.summary)}</p>
    <div class="ai-context-card__meta">
      ${metaItems.map((item) => `<span>${escapeHtml(item)}</span>`).join("")}
    </div>
  `;
  spotContext.appendChild(card);
  spotContext.classList.remove("is-hidden");
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function safeExternalUrl(value) {
  const url = String(value || "").trim();
  return /^https?:\/\//i.test(url) ? url : "";
}

function renderStories(stories) {
  if (!Array.isArray(stories) || stories.length === 0) {
    storyList.innerHTML = `
      <article class="story-card story-card--empty">
        <div class="story-meta">
          <span>System</span>
          <span>Now</span>
        </div>
        <h3 class="story-title">No stories returned</h3>
        <p class="story-copy">The API returned an empty briefing for this selection.</p>
      </article>
    `;
    return;
  }

  storyList.innerHTML = stories
    .map(
      (story) => {
        const storyUrl = safeExternalUrl(story.url);
        return `
        <article class="story-card">
          <div class="story-meta">
            <span>${escapeHtml(story.source)}</span>
            <span>${escapeHtml(story.time)}</span>
          </div>
          <h3 class="story-title">
            ${
              storyUrl
                ? `<a class="story-link" href="${escapeHtml(storyUrl)}" target="_blank" rel="noreferrer">${escapeHtml(story.title)}</a>`
                : escapeHtml(story.title)
            }
          </h3>
          <p class="story-copy">${escapeHtml(story.summary)}</p>
          <div class="story-tags">
            ${(story.tags || []).map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}
          </div>
        </article>
      `;
      },
    )
    .join("");
}

function buildCountryStore() {
  countryStore = new Map(
    features.map((feature) => [feature.properties.name, createBaseCountry(feature.properties.name)]),
  );

  for (const country of Object.values(sampleCountryData)) {
    const matchedName = features.find((feature) => {
      const canonical = getCanonicalCountryName(feature.properties.name);
      return canonical === country.name;
    })?.properties.name;

    if (matchedName) {
      countryStore.set(matchedName, { ...countryStore.get(matchedName), ...country });
    } else {
      countryStore.set(country.name, country);
    }
  }
}

function mergeCountryFacts(payload) {
  if (!payload || !payload.countries) {
    return;
  }

  for (const [countryName, facts] of Object.entries(payload.countries)) {
    const existing = countryStore.get(countryName) || createBaseCountry(countryName);
    countryStore.set(countryName, { ...existing, ...facts });
  }
}

async function loadCountryFacts() {
  try {
    const response = await fetch("data/generated/country_facts.json", { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    mergeCountryFacts(payload);
  } catch (error) {
    console.error("Country facts unavailable", error);
  }
}

function getCountryRecord(countryName) {
  return countryStore.get(countryName) || createBaseCountry(countryName);
}

function bindMetricHoverHandlers(element, mode) {
  element.classList.add("is-hoverable");
  element.addEventListener("mouseenter", () => setMetricHover(mode));
  element.addEventListener("mouseleave", () => setMetricHover(null));
  element.addEventListener("focus", () => setMetricHover(mode));
  element.addEventListener("blur", () => setMetricHover(null));
}

function updateSheet(countryName) {
  const selected = getCountryRecord(countryName);

  showCountryFacts();
  detailCountry.textContent = selected.name;
  detailRegion.textContent = selected.region || "Metadata not populated yet";
  detailDemocracyIndex.textContent = selected.democracyIndex || "Pending score source";
  detailEconomicGrowth.textContent = selected.economicGrowth || "No recent World Bank data";
  renderConflictDetails(selected);
  renderStories(selected.stories);
}

function setLoadingState(countryName) {
  const selected = getCountryRecord(countryName);
  showCountryFacts();
  detailCountry.textContent = selected.name;
  detailRegion.textContent = selected.region || "Metadata not populated yet";
  detailDemocracyIndex.textContent = selected.democracyIndex || "Pending score source";
  detailEconomicGrowth.textContent = selected.economicGrowth || "No recent World Bank data";
  renderConflictDetails(selected);
  renderStories([
    {
      source: "System",
      time: "Now",
      title: "Loading briefing",
      summary: "This country only refreshes when clicked. Results stay cached for 24 hours.",
      tags: ["Cache", "On demand"],
      url: "",
    },
  ]);
}

function updateSpotSheet(spotBriefing) {
  showSpotFacts();
  detailCountry.textContent = spotBriefing.label || spotBriefing.name;
  detailRegion.textContent = spotBriefing.kind || "Key area";
  detailConflictLabel.classList.remove("is-hoverable");
  detailConflictLabel.onmouseenter = null;
  detailConflictLabel.onmouseleave = null;
  detailConflictLabel.onfocus = null;
  detailConflictLabel.onblur = null;
  detailConflict.replaceChildren();
  renderSpotContext(spotBriefing);
  renderStories(spotBriefing.stories || []);
}

function updateAiPickSheet(pick) {
  showAiPickFacts();
  detailCountry.textContent = pick.title;
  detailRegion.textContent = pick.place || pick.country || "AI pick";
  detailConflictLabel.classList.remove("is-hoverable");
  detailConflictLabel.onmouseenter = null;
  detailConflictLabel.onmouseleave = null;
  detailConflictLabel.onfocus = null;
  detailConflictLabel.onblur = null;
  detailConflict.replaceChildren();
  renderAiPickContext(pick);
  const sources = Array.isArray(pick.sources) ? pick.sources : [];
  const overlapTags = Array.isArray(pick.overlap)
    ? pick.overlap.map((item) => item.label || item.type).filter(Boolean)
    : [];
  renderStories(
    sources.length
      ? sources.map((source) => ({
          source: "Source",
          time: pick.generatedAtLabel || "Recent",
          title: source.title || pick.title,
          summary: pick.summary,
          tags: [pick.freshness, pick.region, pick.country, ...overlapTags].filter(Boolean),
          url: source.url || "",
        }))
      : [
          {
            source: "AI Picks",
            time: "Recent",
            title: pick.title,
            summary: pick.summary,
            tags: [pick.freshness, pick.category, pick.region, ...overlapTags].filter(Boolean),
            url: "",
          },
        ],
  );
}

let activePopupHotspot = null;

function clearConnector() {
  while (connectorLayer.firstChild) connectorLayer.removeChild(connectorLayer.firstChild);
}

function drawConnector(dotX, dotY, popupEl, flipped) {
  clearConnector();
  const rect = popupEl.getBoundingClientRect();
  const stageRect = atlasStage.getBoundingClientRect();
  // Popup position relative to stage
  const px = rect.left - stageRect.left;
  const py = rect.top - stageRect.top;
  const pw = rect.width;
  const ph = rect.height;

  // Connect hotspot dot → nearest popup edge midpoint
  const targetX = flipped ? px + pw : px;
  const targetY = py + ph / 2;

  const ns = "http://www.w3.org/2000/svg";

  const line = document.createElementNS(ns, "line");
  line.setAttribute("class", "connector-line");
  line.setAttribute("x1", dotX);
  line.setAttribute("y1", dotY);
  line.setAttribute("x2", targetX);
  line.setAttribute("y2", targetY);
  connectorLayer.appendChild(line);

  const dot = document.createElementNS(ns, "circle");
  dot.setAttribute("class", "connector-dot");
  dot.setAttribute("cx", dotX);
  dot.setAttribute("cy", dotY);
  dot.setAttribute("r", 2.5);
  connectorLayer.appendChild(dot);
}

function closeHotspotPopup() {
  hotspotPopup.classList.add("is-hidden");
  popupMarket.classList.add("is-hidden");
  popupMarket.replaceChildren();
  activePopupHotspot = null;
  clearConnector();
}

function refreshConnector() {
  if (!activePopupHotspot || hotspotPopup.classList.contains("is-hidden")) return;

  const svgEl = document.getElementById("world-map");
  const svgRect = svgEl.getBoundingClientRect();
  const stageRect = atlasStage.getBoundingClientRect();
  const projected = projection([activePopupHotspot.lon, activePopupHotspot.lat]);

  // Hide popup if hotspot rotates behind the globe
  if (!projected || !isPointVisible(activePopupHotspot.lon, activePopupHotspot.lat)) {
    hotspotPopup.classList.add("is-hidden");
    clearConnector();
    return;
  }

  hotspotPopup.classList.remove("is-hidden");
  const scaleX = svgRect.width / 1440;
  const scaleY = svgRect.height / 900;
  const screenX = svgRect.left - stageRect.left + projected[0] * scaleX;
  const screenY = svgRect.top - stageRect.top + projected[1] * scaleY;
  const flipLeft = hotspotPopup.classList.contains("is-flipped");
  drawConnector(screenX, screenY, hotspotPopup, flipLeft);
}

function openConflictHotspot(hotspot, clickEvent, isClick = false) {
  if (isClick) autoRotate = false;
  mapStatus.textContent = hotspot.label;

  // Fill popup content
  popupLabel.textContent = hotspot.label;
  popupConflict.textContent = hotspot.conflict;
  popupCountries.textContent = (hotspot.countries || []).join(" · ");
  renderMarketCard(popupMarket, hotspot.marketCard, true);

  if (hotspot.sourceUrl) {
    popupLink.href = hotspot.sourceUrl;
    popupLink.classList.remove("is-hidden");
  } else {
    popupLink.classList.add("is-hidden");
  }

  // Position popup near the hotspot using SVG projected coordinates
  const svgEl = document.getElementById("world-map");
  const svgRect = svgEl.getBoundingClientRect();
  const stageRect = atlasStage.getBoundingClientRect();

  const projected = projection([hotspot.lon, hotspot.lat]);
  if (!projected) return;

  const scaleX = svgRect.width / 1440;
  const scaleY = svgRect.height / 900;

  const screenX = svgRect.left - stageRect.left + projected[0] * scaleX;
  const screenY = svgRect.top - stageRect.top + projected[1] * scaleY;

  const popupW = hotspotPopup.offsetWidth || 270;
  const offset = 18;
  const flipThreshold = stageRect.width - popupW - 48;

  const flipLeft = screenX > flipThreshold;
  hotspotPopup.classList.toggle("is-flipped", flipLeft);

  const left = flipLeft ? screenX - popupW - offset : screenX + offset;
  const top = screenY - 28;

  hotspotPopup.style.left = `${left}px`;
  hotspotPopup.style.top = `${top}px`;
  hotspotPopup.classList.remove("is-hidden");
  activePopupHotspot = hotspot;

  // Draw connector after popup is placed
  requestAnimationFrame(() => drawConnector(screenX, screenY, hotspotPopup, flipLeft));
}

function setSpotLoadingState(spot) {
  showSpotFacts();
  detailCountry.textContent = spot.label;
  detailRegion.textContent = spot.kind.replace("-", " ");
  detailConflictLabel.classList.remove("is-hoverable");
  detailConflict.replaceChildren();
  spotContext.classList.add("is-hidden");
  spotContext.replaceChildren();
  renderStories([
    {
      source: "System",
      time: "Now",
      title: "Loading key area coverage",
      summary: "This key area refreshes on click and then stays cached for 24 hours.",
      tags: ["Cache", "Key area", "On demand"],
      url: "",
    },
  ]);
}

function mergeRemoteBriefing(countryName, briefing) {
  const existing = countryStore.get(countryName) || createBaseCountry(countryName);
  countryStore.set(countryName, { ...existing, ...briefing });
}

async function refreshCountryBriefing(countryName, requestId) {
  const sheetKey = `country:${countryName}`;
  try {
    const response = await fetch(`/api/briefing?country=${encodeURIComponent(countryName)}`, {
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `Briefing request failed: ${response.status}`);
    }
    if (requestId !== activeSheetRequestId || activeSheetKey !== sheetKey) {
      return;
    }
    mergeRemoteBriefing(countryName, payload.briefing);
    updateSheet(countryName);
  } catch (error) {
    console.error("Briefing refresh failed", error);
    if (requestId !== activeSheetRequestId || activeSheetKey !== sheetKey) {
      return;
    }
    renderStories([
      {
        source: "System",
        time: "Now",
        title: "Live briefing failed",
        summary: error.message || "The deployed API could not refresh this country.",
        tags: ["API", "Live fetch"],
        url: "",
      },
    ]);
  }
}

async function refreshSpotBriefing(spotId, requestId) {
  const sheetKey = `spot:${spotId}`;
  try {
    const response = await fetch(`/api/important-spot?spot=${encodeURIComponent(spotId)}`, {
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.error || `Spot request failed: ${response.status}`);
    }
    if (requestId !== activeSheetRequestId || activeSheetKey !== sheetKey) {
      return;
    }
    updateSpotSheet(payload.briefing);
  } catch (error) {
    console.error("Spot refresh failed", error);
    if (requestId !== activeSheetRequestId || activeSheetKey !== sheetKey) {
      return;
    }
    renderStories([
      {
        source: "System",
        time: "Now",
        title: "Key area refresh failed",
        summary: error.message || "The deployed API could not refresh this key area.",
        tags: ["API", "Key area"],
        url: "",
      },
    ]);
  }
}

function refreshPaths() {
  sphereLayer.attr("d", path({ type: "Sphere" }));
  countryLayer.selectAll("path").attr("d", path);
  borderLayer.attr("d", path(borders));
  graticuleLayer.attr("d", path(d3.geoGraticule10()));
  updateHotspotPositions();
  updateImportantSpotPositions();
  updateAiPickPositions();
  updateCarrierPositions();
}

function setActiveCountry(featureId) {
  activeFeatureId = featureId;
  syncCountryClasses();
}

function isPointVisible(lon, lat) {
  const rotation = projection.rotate();
  const center = [-rotation[0], -rotation[1]];
  return d3.geoDistance([lon, lat], center) <= Math.PI / 2;
}

function updateHotspotPositions() {
  if (!hotspotNodes) {
    return;
  }

  hotspotNodes
    .style("display", (hotspot) => {
      if (!showConflictHotspots) {
        return "none";
      }
      return isPointVisible(hotspot.lon, hotspot.lat) ? null : "none";
    })
    .attr("transform", (hotspot) => {
      const projected = projection([hotspot.lon, hotspot.lat]);
      return projected ? `translate(${projected[0]}, ${projected[1]})` : "translate(-9999,-9999)";
    });
}

function updateImportantSpotPositions() {
  if (!importantSpotNodes) {
    return;
  }

  importantSpotNodes
    .style("display", (spot) => {
      if (!showImportantSpots) {
        return "none";
      }
      return isPointVisible(spot.lon, spot.lat) ? null : "none";
    })
    .attr("transform", (spot) => {
      const projected = projection([spot.lon, spot.lat]);
      return projected ? `translate(${projected[0]}, ${projected[1]})` : "translate(-9999,-9999)";
    });
}

function updateAiPickPositions() {
  if (!aiPickNodes) {
    return;
  }

  aiPickNodes
    .style("display", (pick) => {
      if (!showAiPicks) {
        return "none";
      }
      return isPointVisible(pick.lon, pick.lat) ? null : "none";
    })
    .attr("transform", (pick) => {
      const projected = projection([pick.lon, pick.lat]);
      return projected ? `translate(${projected[0]}, ${projected[1]})` : "translate(-9999,-9999)";
    });
}

function updateCarrierPositions() {
  if (!carrierSpotNodes) {
    return;
  }

  carrierSpotNodes
    .style("display", (spot) => {
      if (!showCarrierSpots) {
        return "none";
      }
      return isPointVisible(spot.lon, spot.lat) ? null : "none";
    })
    .attr("transform", (spot) => {
      const projected = projection([spot.lon, spot.lat]);
      return projected ? `translate(${projected[0]}, ${projected[1]})` : "translate(-9999,-9999)";
    });
}

function setConflictHotspotsVisible(active) {
  showConflictHotspots = active;
  syncConflictToggle();
  if (hotspotLayer) {
    hotspotLayer.style("display", showConflictHotspots ? null : "none");
  }
  updateHotspotPositions();
}

function setImportantSpotsVisible(active) {
  showImportantSpots = active;
  syncImportantToggle();
  if (importantLayer) {
    importantLayer.style("display", showImportantSpots ? null : "none");
  }
  updateImportantSpotPositions();
}

function setAiPicksVisible(active) {
  showAiPicks = active;
  syncAiPicksToggle();
  if (aiPicksLayer) {
    aiPicksLayer.style("display", showAiPicks ? null : "none");
  }
  updateAiPickPositions();
}

function setCarrierSpotsVisible(active) {
  showCarrierSpots = active;
  syncCarrierToggle();
  if (carrierLayer) {
    carrierLayer.style("display", showCarrierSpots ? null : "none");
  }
  updateCarrierPositions();
}

function focusCountry(feature) {
  const centroid = d3.geoCentroid(feature);
  const currentRotation = projection.rotate();
  projection.rotate([-centroid[0], -centroid[1], currentRotation[2]]);
  refreshPaths();
}

function focusCoordinates(lon, lat) {
  const currentRotation = projection.rotate();
  projection.rotate([-lon, -lat, currentRotation[2]]);
  refreshPaths();
}

function openCountry(feature) {
  autoRotate = false;
  clearConflictHover();
  setMetricHover(null);
  activeSpotId = null;
  focusCountry(feature);
  updateSheet(feature.properties.name);
  setActiveCountry(feature.id);
  countrySheet.classList.remove("is-hidden");
  mapStatus.textContent = feature.properties.name;
  activeSheetRequestId += 1;
  activeSheetKey = `country:${feature.properties.name}`;
  const requestId = activeSheetRequestId;
  setLoadingState(feature.properties.name);
  refreshCountryBriefing(feature.properties.name, requestId);
}

function openImportantSpot(spot, options = {}) {
  const { hoverPreview = false } = options;
  if (!hoverPreview) {
    autoRotate = false;
  }
  clearConflictHover();
  setMetricHover(null);
  closeHotspotPopup();
  activeSpotId = spot.id;
  setActiveCountry(null);
  if (!hoverPreview) {
    focusCoordinates(spot.lon, spot.lat);
  }
  countrySheet.classList.remove("is-hidden");
  mapStatus.textContent = spot.label;
  if (activeSheetKey === `spot:${spot.id}` && hoverPreview) {
    return;
  }
  activeSheetRequestId += 1;
  activeSheetKey = `spot:${spot.id}`;
  const requestId = activeSheetRequestId;
  setSpotLoadingState(spot);
  refreshSpotBriefing(spot.id, requestId);
}

function openAiPick(pick, options = {}) {
  const { hoverPreview = false } = options;
  if (!hoverPreview) {
    autoRotate = false;
  }
  clearConflictHover();
  setMetricHover(null);
  closeHotspotPopup();
  activeSpotId = null;
  setActiveCountry(null);
  if (!hoverPreview) {
    focusCoordinates(pick.lon, pick.lat);
  }
  countrySheet.classList.remove("is-hidden");
  mapStatus.textContent = pick.title;
  if (activeSheetKey === `ai:${pick.id}` && hoverPreview) {
    return;
  }
  activeSheetRequestId += 1;
  activeSheetKey = `ai:${pick.id}`;
  updateAiPickSheet(pick);
}

function closeCountrySheet() {
  clearConflictHover();
  setMetricHover(null);
  activeSpotId = null;
  activeFeatureId = null;
  activeSheetRequestId += 1;
  activeSheetKey = "";
  countrySheet.classList.add("is-hidden");
  syncCountryClasses();
  mapStatus.textContent = getDefaultMapStatus();
}

function buildGlobe() {
  const defs = svg.append("defs");
  const oceanGradient = defs
    .append("radialGradient")
    .attr("id", "ocean-gradient")
    .attr("cx", "45%")
    .attr("cy", "35%");

  oceanGradient.append("stop").attr("offset", "0%").attr("stop-color", "#123140");
  oceanGradient.append("stop").attr("offset", "65%").attr("stop-color", "#0b1f2c");
  oceanGradient.append("stop").attr("offset", "100%").attr("stop-color", "#071118");

  svg
    .append("circle")
    .attr("class", "globe-glow")
    .attr("cx", 720)
    .attr("cy", 450)
    .attr("r", 335);

  svg
    .append("path")
    .datum({ type: "Sphere" })
    .attr("class", "globe-sphere");

  sphereLayer = svg.select(".globe-sphere");

  graticuleLayer = svg.append("path").attr("class", "globe-graticule");
  countryLayer = svg.append("g").attr("class", "country-layer");
  borderLayer = svg.append("path").attr("class", "country-boundary");
  hotspotLayer = svg.append("g").attr("class", "hotspot-layer");
  importantLayer = svg.append("g").attr("class", "important-layer");
  aiPicksLayer = svg.append("g").attr("class", "ai-picks-layer");
  carrierLayer = svg.append("g").attr("class", "carrier-layer");
}

function resizeProjection() {
  const width = 1440;
  const height = 900;
  projection = d3
    .geoOrthographic()
    .translate([width / 2, height / 2])
    .scale(Math.min(width, height) * 0.36)
    .clipAngle(90)
    .precision(0.5)
    .rotate([-12, -18, 0]);

  path = d3.geoPath(projection);
}

function attachInteraction() {
  const dragBehavior = d3
    .drag()
    .on("start", () => {
      autoRotate = false;
    })
    .on("drag", (event) => {
      const rotation = projection.rotate();
      const sensitivity = 0.22;
      projection.rotate([
        rotation[0] + event.dx * sensitivity,
        rotation[1] - event.dy * sensitivity,
        rotation[2],
      ]);
      refreshPaths();
    });

  svg.call(dragBehavior);
  atlasStage.addEventListener("click", (event) => {
    if (!isInteractiveElement(event.target)) {
      closeCountrySheet();
      closeHotspotPopup();
    }
  });
  atlasStage.addEventListener("dblclick", (event) => {
    if (isInteractiveElement(event.target)) {
      return;
    }
    autoRotate = true;
    mapStatus.textContent = getDefaultMapStatus();
  });
}

function renderCountries() {
  countryPaths = countryLayer
    .selectAll("path")
    .data(features)
    .join("path")
    .attr("class", "country is-supported")
    .attr("tabindex", 0)
    .attr("aria-label", (feature) => feature.properties.name)
    .on("click", (_, feature) => openCountry(feature))
    .on("keydown", (event, feature) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openCountry(feature);
      }
    });

  countryPaths.selectAll("title").remove();
  countryPaths.append("title").text((feature) => `${feature.properties.name}: click to open`);

  syncCountryClasses();
}

function syncHotspotAnimations() {
  const blastDuration = 2000;
  const flickerDuration = 1800;
  const phase1 = -(performance.now() % blastDuration) / 1000;
  const phase2 = phase1 - 0.65;
  const phaseCore = -(performance.now() % flickerDuration) / 1000;

  document.querySelectorAll(".hotspot-halo--1").forEach((el) => {
    el.style.animationDelay = `${phase1}s`;
  });
  document.querySelectorAll(".hotspot-halo--2").forEach((el) => {
    el.style.animationDelay = `${phase2}s`;
  });
  document.querySelectorAll(".hotspot-core").forEach((el) => {
    el.style.animationDelay = `${phaseCore}s`;
  });
}

function renderConflictHotspots() {
  if (!hotspotLayer) {
    return;
  }

  hotspotLayer.style("display", showConflictHotspots ? null : "none");

  hotspotNodes = hotspotLayer
    .selectAll("g")
    .data(conflictHotspots, (hotspot) => hotspot.id)
    .join((enter) => {
      const group = enter.append("g").attr("class", "conflict-hotspot").attr("tabindex", 0);
      group.append("circle").attr("class", "hotspot-halo hotspot-halo--1");
      group.append("circle").attr("class", "hotspot-halo hotspot-halo--2");
      group.append("circle").attr("class", "hotspot-core");
      group.append("title");
      return group;
    });

  hotspotNodes
    .style("pointer-events", () => (showConflictHotspots ? "auto" : "none"))
    .attr("aria-label", (hotspot) => hotspot.label)
    .on("mouseenter", (event, hotspot) => {
      cancelHotspotHide();
      mapStatus.textContent = hotspot.label;
      openConflictHotspot(hotspot, event, false);
    })
    .on("mouseleave", (_, hotspot) => {
      scheduleHotspotHide();
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("focus", (event, hotspot) => {
      cancelHotspotHide();
      mapStatus.textContent = hotspot.label;
      openConflictHotspot(hotspot, event, false);
    })
    .on("blur", () => {
      scheduleHotspotHide();
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("click", (event, hotspot) => {
      event.stopPropagation();
      openConflictHotspot(hotspot, event, true);
    })
    .on("keydown", (event, hotspot) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openConflictHotspot(hotspot, event);
      }
    });

  hotspotNodes
    .select(".hotspot-halo--1")
    .attr("r", (hotspot) => Math.max(10, hotspot.weight * 1.8));

  hotspotNodes
    .select(".hotspot-halo--2")
    .attr("r", (hotspot) => Math.max(10, hotspot.weight * 1.8));

  hotspotNodes
    .select(".hotspot-core")
    .attr("r", (hotspot) => Math.max(3, Math.min(7.5, hotspot.weight * 0.55)));

  hotspotNodes
    .select("title")
    .text((hotspot) => `${hotspot.label} — ${hotspot.conflict}`);

  updateHotspotPositions();
  syncHotspotAnimations();
}

function renderImportantSpots() {
  if (!importantLayer) {
    return;
  }

  importantLayer.style("display", showImportantSpots ? null : "none");

  importantSpotNodes = importantLayer
    .selectAll("g")
    .data(importantSpots, (spot) => spot.id)
    .join((enter) => {
      const group = enter.append("g").attr("class", "important-spot").attr("tabindex", 0);
      group.append("circle").attr("class", "important-hit");
      group.append("circle").attr("class", "important-ring");
      group.append("circle").attr("class", "important-core");
      group.append("title");
      return group;
    });

  importantSpotNodes
    .style("pointer-events", () => (showImportantSpots ? "all" : "none"))
    .attr("aria-label", (spot) => spot.label)
    .on("mouseenter", (_, spot) => {
      mapStatus.textContent = `${spot.label}: ${spot.title}`;
    })
    .on("mouseleave", () => {
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("focus", (_, spot) => {
      mapStatus.textContent = `${spot.label}: ${spot.title}`;
    })
    .on("blur", () => {
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("click", (event, spot) => {
      event.stopPropagation();
      openImportantSpot(spot, { hoverPreview: false });
    })
    .on("keydown", (event, spot) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openImportantSpot(spot, { hoverPreview: false });
      }
    });

  importantSpotNodes
    .select(".important-hit")
    .on("click", (event, spot) => {
      event.preventDefault();
      event.stopPropagation();
      openImportantSpot(spot, { hoverPreview: false });
    })
    .on("pointerup", (event, spot) => {
      event.preventDefault();
      event.stopPropagation();
      openImportantSpot(spot, { hoverPreview: false });
    });

  importantSpotNodes.select(".important-hit").attr("r", 19);
  importantSpotNodes.select(".important-ring").attr("r", 10.5);
  importantSpotNodes.select(".important-core").attr("r", 5);
  importantSpotNodes.select("title").text((spot) => `${spot.label} — ${spot.title}`);

  updateImportantSpotPositions();
}

function renderAiPicks() {
  if (!aiPicksLayer) {
    return;
  }

  aiPicksLayer.style("display", showAiPicks ? null : "none");

  aiPickNodes = aiPicksLayer
    .selectAll("g")
    .data(aiPicks, (pick) => pick.id)
    .join((enter) => {
      const group = enter.append("g").attr("class", "ai-pick").attr("tabindex", 0);
      group.append("circle").attr("class", "ai-pick-hit");
      group.append("circle").attr("class", "ai-pick-ring");
      group.append("circle").attr("class", "ai-pick-core");
      group.append("title");
      return group;
    });

  aiPickNodes
    .style("pointer-events", () => (showAiPicks ? "all" : "none"))
    .attr("aria-label", (pick) => pick.title)
    .on("mouseenter", (_, pick) => {
      mapStatus.textContent = `${pick.place}: ${pick.title}`;
      openAiPick(pick, { hoverPreview: true });
    })
    .on("mouseleave", () => {
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("focus", (_, pick) => {
      mapStatus.textContent = `${pick.place}: ${pick.title}`;
      openAiPick(pick, { hoverPreview: true });
    })
    .on("blur", () => {
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("click", (event, pick) => {
      event.stopPropagation();
      openAiPick(pick);
    })
    .on("keydown", (event, pick) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openAiPick(pick);
      }
    });

  aiPickNodes.select(".ai-pick-hit").attr("r", 20);
  aiPickNodes.select(".ai-pick-ring").attr("r", (pick) => 8 + (pick.importance || 0.6) * 6);
  aiPickNodes.select(".ai-pick-core").attr("r", (pick) => 3.6 + (pick.importance || 0.6) * 2.8);
  aiPickNodes.select("title").text((pick) => `${pick.place} — ${pick.title}`);

  updateAiPickPositions();
}

function renderCarrierSpots() {
  if (!carrierLayer) {
    return;
  }

  carrierLayer.style("display", showCarrierSpots ? null : "none");

  carrierSpotNodes = carrierLayer
    .selectAll("g")
    .data(carrierSpots, (spot) => spot.id)
    .join((enter) => {
      const group = enter.append("g").attr("class", "carrier-spot").attr("tabindex", 0);
      group.append("circle").attr("class", "carrier-hit");
      group.append("circle").attr("class", "carrier-ring");
      group.append("circle").attr("class", "carrier-core");
      group.append("title");
      return group;
    });

  carrierSpotNodes
    .style("pointer-events", () => (showCarrierSpots ? "all" : "none"))
    .attr("aria-label", (spot) => spot.name)
    .on("mouseenter", (_, spot) => {
      mapStatus.textContent = `${spot.name}: ${spot.area}`;
    })
    .on("mouseleave", () => {
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("focus", (_, spot) => {
      mapStatus.textContent = `${spot.name}: ${spot.area}`;
    })
    .on("blur", () => {
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("click", (event, spot) => {
      event.stopPropagation();
      if (spot.sourceUrl) {
        window.open(spot.sourceUrl, "_blank", "noreferrer");
      }
    })
    .on("keydown", (event, spot) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        if (spot.sourceUrl) {
          window.open(spot.sourceUrl, "_blank", "noreferrer");
        }
      }
    });

  carrierSpotNodes.select(".carrier-hit").attr("r", 13);
  carrierSpotNodes.select(".carrier-ring").attr("r", 9);
  carrierSpotNodes.select(".carrier-core").attr("r", 4.2);
  carrierSpotNodes
    .select("title")
    .text((spot) => `${spot.name} — ${spot.area} — ${spot.status}`);

  updateCarrierPositions();
}

async function loadConflictEvents() {
  try {
    const response = await fetch("data/generated/conflict_events.json", { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    conflictHotspots = Array.isArray(payload.hotspots) ? payload.hotspots : [];
  } catch (error) {
    console.error("Conflict events unavailable", error);
  }
}

async function loadImportantSpots() {
  importantSpots = fallbackImportantSpots;
  try {
    const response = await fetch("data/generated/important_spots.json", { cache: "no-store" });
    if (!response.ok) {
      return;
    }
    const payload = await response.json();
    const spots = Array.isArray(payload.spots) ? payload.spots : [];
    importantSpots = spots.length ? spots : fallbackImportantSpots;
  } catch (error) {
    console.error("Important spots unavailable", error);
    importantSpots = fallbackImportantSpots;
  }
}

async function loadAiPicks() {
  try {
    const response = await fetch("data/generated/ai_picks.json", { cache: "no-store" });
    if (!response.ok) {
      aiPicks = [];
      return;
    }
    const payload = await response.json();
    aiPicks = Array.isArray(payload.picks)
      ? payload.picks.filter(
          (pick) =>
            pick &&
            typeof pick.lat === "number" &&
            typeof pick.lon === "number" &&
            pick.id &&
            pick.title,
        )
      : [];
  } catch (error) {
    console.error("AI picks unavailable", error);
    aiPicks = [];
  }
}

async function loadCarrierSpots() {
  try {
    const response = await fetch("data/generated/us_carriers.json", { cache: "no-store" });
    if (!response.ok) {
      carrierSpots = [];
      return;
    }
    const payload = await response.json();
    carrierSpots = Array.isArray(payload.carriers) ? payload.carriers : [];
  } catch (error) {
    console.error("Carrier spots unavailable", error);
    carrierSpots = [];
  }
}

function animate(timestamp) {
  if (autoRotate && lastTimestamp) {
    const delta = timestamp - lastTimestamp;
    const rotation = projection.rotate();
    projection.rotate([rotation[0] + delta * 0.0038, rotation[1], rotation[2]]);
    refreshPaths();
  }

  refreshConnector();
  lastTimestamp = timestamp;
  requestAnimationFrame(animate);
}

async function loadGlobe() {
  try {
    resizeProjection();
    buildGlobe();

    const world = await d3.json("data/countries-110m.json");
    features = topojson.feature(world, world.objects.countries).features;
    borders = topojson.mesh(world, world.objects.countries, (a, b) => a !== b);
    buildCountryStore();
    await Promise.all([
      loadCountryFacts(),
      loadConflictEvents(),
      loadImportantSpots(),
      loadAiPicks(),
      loadCarrierSpots(),
    ]);

    renderCountries();
    renderConflictHotspots();
    renderImportantSpots();
    renderAiPicks();
    renderCarrierSpots();
    refreshPaths();
    attachInteraction();
    requestAnimationFrame(animate);
    mapStatus.textContent = "Drag the globe. Click a country.";
  } catch (error) {
    console.error(error);
    mapStatus.textContent = "Globe assets failed to load.";
  }
}

closeButton.addEventListener("click", closeCountrySheet);
bindMetricHoverHandlers(detailDemocracyLabel, "democracy");
bindMetricHoverHandlers(detailEconomicGrowthLabel, "growth");
conflictToggle.addEventListener("click", () => setConflictHotspotsVisible(!showConflictHotspots));
importantToggle.addEventListener("click", () => setImportantSpotsVisible(!showImportantSpots));
aiPicksToggle.addEventListener("click", () => setAiPicksVisible(!showAiPicks));
carrierToggle.addEventListener("click", () => setCarrierSpotsVisible(!showCarrierSpots));
syncConflictToggle();
syncImportantToggle();
syncAiPicksToggle();
syncCarrierToggle();

loadGlobe();
