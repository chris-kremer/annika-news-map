const svg = d3.select("#world-map");
const atlasStage = document.querySelector(".atlas-stage");
const mapStatus = document.getElementById("map-status");
const conflictToggle = document.getElementById("conflict-toggle");
const importantToggle = document.getElementById("important-toggle");
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
const storySectionLabel = document.getElementById("story-section-label");
const storyList = document.getElementById("story-list");

const sampleCountryData = window.appData.countries;
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
let showConflictHotspots = true;
let importantSpots = [];
let importantSpotNodes;
let showImportantSpots = false;

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

function isInteractiveElement(target) {
  return Boolean(
    target?.closest?.(".country, .conflict-hotspot, .important-spot, .country-sheet, .layer-switches"),
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
  storySectionLabel.textContent = "Recent stories";
}

function showSpotFacts() {
  factStrip.hidden = true;
  storySectionLabel.textContent = "Current coverage";
}

function renderStories(stories) {
  storyList.innerHTML = stories
    .map(
      (story) => `
        <article class="story-card">
          <div class="story-meta">
            <span>${story.source}</span>
            <span>${story.time}</span>
          </div>
          <h3 class="story-title">
            ${
              story.url
                ? `<a class="story-link" href="${story.url}" target="_blank" rel="noreferrer">${story.title}</a>`
                : story.title
            }
          </h3>
          <p class="story-copy">${story.summary}</p>
          <div class="story-tags">
            ${(story.tags || []).map((tag) => `<span>${tag}</span>`).join("")}
          </div>
        </article>
      `,
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
  detailRegion.textContent = spotBriefing.kind || "Important spot";
  detailConflictLabel.classList.remove("is-hoverable");
  detailConflictLabel.onmouseenter = null;
  detailConflictLabel.onmouseleave = null;
  detailConflictLabel.onfocus = null;
  detailConflictLabel.onblur = null;
  detailConflict.replaceChildren();
  renderStories(spotBriefing.stories || []);
}

function setSpotLoadingState(spot) {
  showSpotFacts();
  detailCountry.textContent = spot.label;
  detailRegion.textContent = spot.kind.replace("-", " ");
  detailConflictLabel.classList.remove("is-hoverable");
  detailConflict.replaceChildren();
  renderStories([
    {
      source: "System",
      time: "Now",
      title: "Loading spot coverage",
      summary: "This important spot refreshes on click and then stays cached for 24 hours.",
      tags: ["Cache", "Spot", "On demand"],
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
  }
}

function refreshPaths() {
  sphereLayer.attr("d", path({ type: "Sphere" }));
  countryLayer.selectAll("path").attr("d", path);
  borderLayer.attr("d", path(borders));
  graticuleLayer.attr("d", path(d3.geoGraticule10()));
  updateHotspotPositions();
  updateImportantSpotPositions();
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

function openImportantSpot(spot) {
  autoRotate = false;
  clearConflictHover();
  setMetricHover(null);
  activeSpotId = spot.id;
  setActiveCountry(null);
  focusCoordinates(spot.lon, spot.lat);
  countrySheet.classList.remove("is-hidden");
  mapStatus.textContent = spot.label;
  activeSheetRequestId += 1;
  activeSheetKey = `spot:${spot.id}`;
  const requestId = activeSheetRequestId;
  setSpotLoadingState(spot);
  refreshSpotBriefing(spot.id, requestId);
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
      group.append("circle").attr("class", "hotspot-halo");
      group.append("circle").attr("class", "hotspot-core");
      group.append("title");
      return group;
    });

  hotspotNodes
    .style("pointer-events", () => (showConflictHotspots ? "auto" : "none"))
    .attr("aria-label", (hotspot) => hotspot.label)
    .on("mouseenter", (_, hotspot) => {
      mapStatus.textContent = hotspot.label;
    })
    .on("mouseleave", () => {
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("focus", (_, hotspot) => {
      mapStatus.textContent = hotspot.label;
    })
    .on("blur", () => {
      mapStatus.textContent = getDefaultMapStatus();
    })
    .on("click", (event, hotspot) => {
      event.stopPropagation();
      if (hotspot.sourceUrl) {
        window.open(hotspot.sourceUrl, "_blank", "noreferrer");
      }
    });

  hotspotNodes
    .select(".hotspot-halo")
    .attr("r", (hotspot) => Math.max(8, hotspot.weight * 1.5));

  hotspotNodes
    .select(".hotspot-core")
    .attr("r", (hotspot) => Math.max(2.2, Math.min(6.5, hotspot.weight * 0.45)));

  hotspotNodes
    .select("title")
    .text((hotspot) => `${hotspot.label} — ${hotspot.conflict}`);

  updateHotspotPositions();
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
      group.append("circle").attr("class", "important-ring");
      group.append("circle").attr("class", "important-core");
      group.append("title");
      return group;
    });

  importantSpotNodes
    .style("pointer-events", () => (showImportantSpots ? "auto" : "none"))
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
      openImportantSpot(spot);
    })
    .on("keydown", (event, spot) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openImportantSpot(spot);
      }
    });

  importantSpotNodes.select(".important-ring").attr("r", 8.5);
  importantSpotNodes.select(".important-core").attr("r", 3.25);
  importantSpotNodes.select("title").text((spot) => `${spot.label} — ${spot.title}`);

  updateImportantSpotPositions();
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
  try {
    const response = await fetch("data/generated/important_spots.json", { cache: "no-store" });
    if (!response.ok) {
      importantSpots = [];
      return;
    }
    const payload = await response.json();
    importantSpots = Array.isArray(payload.spots) ? payload.spots : [];
  } catch (error) {
    console.error("Important spots unavailable", error);
    importantSpots = [];
  }
}

function animate(timestamp) {
  if (autoRotate && lastTimestamp) {
    const delta = timestamp - lastTimestamp;
    const rotation = projection.rotate();
    projection.rotate([rotation[0] + delta * 0.0038, rotation[1], rotation[2]]);
    refreshPaths();
  }

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
    await Promise.all([loadCountryFacts(), loadConflictEvents(), loadImportantSpots()]);

    renderCountries();
    renderConflictHotspots();
    renderImportantSpots();
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
syncConflictToggle();
syncImportantToggle();

loadGlobe();
