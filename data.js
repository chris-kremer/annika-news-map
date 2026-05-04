window.appData = {
  sourceStack: [
    {
      layer: "Map discovery",
      provider: "GDELT",
      rationale:
        "Best fit for country-aware discovery, multilingual monitoring, and rapid global coverage.",
    },
    {
      layer: "Article metadata",
      provider: "The News API",
      rationale:
        "Cleaner article objects, source filtering, and better handoff into clustering and summaries.",
    },
    {
      layer: "Political facts",
      provider: "Wikidata + IFES",
      rationale:
        "Wikidata covers political structure; IFES is stronger for upcoming election timelines.",
    },
    {
      layer: "Conflict status",
      provider: "ACLED",
      rationale:
        "Use a sourced conflict dataset instead of letting the model infer war status.",
    },
  ],
  importantSpots: [
    {
      id: "hormuz",
      label: "Strait of Hormuz",
      lat: 26.57,
      lon: 56.25,
      kind: "chokepoint",
      title: "Shipping and energy risk around Hormuz",
    },
    {
      id: "taiwan-strait",
      label: "Taiwan Strait",
      lat: 24.0,
      lon: 119.4,
      kind: "military",
      title: "Military signaling around Taiwan",
    },
    {
      id: "south-china-sea",
      label: "South China Sea",
      lat: 12.0,
      lon: 114.5,
      kind: "maritime",
      title: "Maritime pressure in the South China Sea",
    },
    {
      id: "red-sea",
      label: "Red Sea / Bab el-Mandeb",
      lat: 13.3,
      lon: 43.2,
      kind: "shipping",
      title: "Shipping risk in the Red Sea corridor",
    },
    {
      id: "suez",
      label: "Suez Canal",
      lat: 30.5,
      lon: 32.35,
      kind: "chokepoint",
      title: "Canal transit and rerouting pressure",
    },
    {
      id: "cuba",
      label: "Cuba",
      lat: 23.13,
      lon: -82.35,
      kind: "flashpoint",
      title: "US-Cuba tension and internal pressure",
    },
    {
      id: "kashmir",
      label: "Kashmir",
      lat: 34.08,
      lon: 74.79,
      kind: "border",
      title: "India-Pakistan tension around Kashmir",
    },
  ],
  countries: {
    ukraine: {
      name: "Ukraine",
      region: "Eastern Europe",
      updated: "Updated April 27, 2026",
      tagline:
        "Recent reporting centers on large-scale strikes, air defense pressure, and the war's wider nuclear and diplomatic risks.",
      democracyIndex: "50-60",
      election: "Presidential election not scheduled during martial law",
      conflict: "Active international armed conflict — Russia",
      languages: "Ukrainian, Russian",
      mix: "War, governance, energy",
      risk: "High-volatility coverage",
      sourceNote: "Curated from Reuters reporting published between April 22 and April 26, 2026.",
      stories: [
        {
          source: "Reuters",
          time: "Apr 25",
          title: "Russian barrage hits Dnipro and other regions after overnight missile and drone wave",
          summary:
            "A large overnight attack killed civilians in Dnipro and Chernihiv and again pushed air defense needs to the top of Ukraine's news cycle.",
          tags: ["War", "Air defense", "Civilian impact"],
          url: "https://wsau.com/2026/04/25/major-russian-attack-on-ukraine-kills-four-wounds-dozens/",
        },
        {
          source: "Reuters",
          time: "Apr 23",
          title: "Kyiv warns a longer Iran conflict could complicate access to Patriot-class missile defenses",
          summary:
            "Zelenskyy linked Middle East escalation to the risk of tighter competition for anti-missile systems that Ukraine still needs in high volume.",
          tags: ["Defense", "Diplomacy", "Supply"],
          url: "https://wsau.com/2026/04/22/a-longer-iran-conflict-could-boost-risk-for-ukraine-securing-missile-defences-zelenskiy-says/",
        },
        {
          source: "Reuters",
          time: "Apr 26",
          title: "Chornobyl anniversary coverage returns wartime nuclear risk to the forefront",
          summary:
            "Commemoration of the 1986 disaster doubled as a warning about missile flight paths and the persistent danger around Ukrainian nuclear infrastructure.",
          tags: ["Nuclear", "History", "Security"],
          url: "https://wsau.com/2026/04/25/ukraine-marks-40th-anniversary-of-chornobyl-disaster-under-cloud-of-war/",
        },
      ],
    },
    usa: {
      name: "United States",
      region: "North America",
      updated: "Updated April 27, 2026",
      tagline:
        "The current U.S. picture is dominated by inflation anxiety, soft household sentiment, and a still uneven growth outlook.",
      democracyIndex: "70+",
      election: "Midterm elections — November 3, 2026",
      conflict: "No declared war",
      languages: "English, Spanish",
      mix: "Politics, industry, state reporting",
      risk: "High volume, high duplication",
      sourceNote: "Curated from Reuters reporting published between April 9 and April 24, 2026.",
      stories: [
        {
          source: "Reuters",
          time: "Apr 24",
          title: "Consumer sentiment falls to a record low as households stay focused on inflation",
          summary:
            "Even after a ceasefire abroad, survey data showed Americans still bracing for higher prices and weaker purchasing power.",
          tags: ["Inflation", "Consumers", "Economy"],
          url: "https://wsau.com/2026/04/24/us-consumer-sentiment-drops-to-near-four-year-low-in-april/",
        },
        {
          source: "Reuters",
          time: "Apr 23",
          title: "Business activity improves in April but supply disruptions keep price pressures elevated",
          summary:
            "Fresh PMI data suggested output picked up, but factory delivery delays and war-related input costs remain a central concern.",
          tags: ["PMI", "Prices", "Industry"],
          url: "https://wsau.com/2026/04/23/us-business-activity-recovers-in-april-war-with-iran-is-boosting-prices-sp-global-survey-shows/",
        },
        {
          source: "Reuters",
          time: "Apr 9",
          title: "Fourth-quarter GDP is revised lower, underscoring how soft the economy entered 2026",
          summary:
            "A downward revision to late-2025 growth reinforced the sense that the economy was already losing momentum before the latest shocks.",
          tags: ["GDP", "Growth", "Macro"],
          url: "https://wsau.com/2026/04/09/us-fourth-quarter-gdp-growth-revised-lower-to-a-0-5-rate/",
        },
      ],
    },
    brazil: {
      name: "Brazil",
      region: "South America",
      updated: "Updated April 27, 2026",
      tagline:
        "Brazil's current mix leans toward trade diplomacy, industrial policy, and monetary caution rather than a single dominant political crisis.",
      democracyIndex: "60-70",
      election: "General election — October 4, 2026",
      conflict: "No active war classification",
      languages: "Portuguese",
      mix: "Politics, climate, security",
      risk: "Translation and regional balance",
      sourceNote: "Curated from Reuters and AP reporting published between April 15 and April 24, 2026.",
      stories: [
        {
          source: "Reuters",
          time: "Apr 24",
          title: "Brasilia rejects calls for a state-run critical minerals company",
          summary:
            "Industry officials argued the existing regulatory framework is enough and pushed back against state-level mineral diplomacy with Washington.",
          tags: ["Mining", "Industry", "US ties"],
          url: "https://wsau.com/2026/04/24/brazil-rejects-calls-for-state-run-critical-minerals-firm-questions-state-deal-with-us/",
        },
        {
          source: "AP",
          time: "Apr 23",
          title: "The Mercosur-EU trade deal is framed in Brasilia as a buffer against a rougher global market",
          summary:
            "Vice President Geraldo Alckmin cast the agreement as a strategic opening for exports while political and environmental objections remain active.",
          tags: ["Trade", "EU", "Exports"],
          url: "https://apnews.com/article/06dd091ea37ab4ab281b76283cabe896",
        },
        {
          source: "Reuters",
          time: "Apr 15",
          title: "Central bank officials defend a cautious easing cycle as uncertainty stays high",
          summary:
            "Policymakers signaled they want inflation control to remain credible even as markets look for more rate relief.",
          tags: ["Central bank", "Inflation", "Rates"],
          url: "https://wsau.com/2026/04/15/brazil-central-banks-caution-has-paid-off-amid-rising-uncertainties-director-says/",
        },
      ],
    },
    germany: {
      name: "Germany",
      region: "Western Europe",
      updated: "Updated April 27, 2026",
      tagline:
        "German coverage is currently dominated by weak sentiment, downgraded growth expectations, and tension inside the governing coalition.",
      democracyIndex: "70+",
      election: "Federal election expected by 2029 unless snap election",
      conflict: "No active war classification",
      languages: "German",
      mix: "Coalition politics, economy, Europe",
      risk: "Context-heavy political coverage",
      sourceNote: "Curated from Reuters reporting published between April 21 and April 27, 2026.",
      stories: [
        {
          source: "Reuters",
          time: "Apr 27",
          title: "Consumer sentiment sinks to its weakest level since early 2023",
          summary:
            "A fresh survey pointed to collapsing income expectations as energy-linked inflation weighs on households heading into May.",
          tags: ["Consumers", "Inflation", "Energy"],
          url: "https://wsau.com/2026/04/27/energy-prices-drag-german-consumer-sentiment-to-three-year-low-finds-survey/",
        },
        {
          source: "Reuters",
          time: "Apr 22",
          title: "Berlin halves its 2026 growth forecast and lifts its inflation outlook",
          summary:
            "The government formally acknowledged that higher energy and raw-material costs are delaying the recovery it had expected this year.",
          tags: ["Growth", "Inflation", "Forecast"],
          url: "https://wsau.com/2026/04/22/germany-halves-2026-growth-forecast-raises-inflation-outlook-amid-iran-war/",
        },
        {
          source: "Reuters",
          time: "Apr 21",
          title: "Merz's coalition is publicly sparring over tax, pension, and health reforms",
          summary:
            "Political friction inside the ruling alliance is becoming a major story in its own right as reform deadlines approach.",
          tags: ["Coalition", "Reforms", "Politics"],
          url: "https://wsau.com/2026/04/21/germanys-ruling-coalition-at-odds-over-reform-push/",
        },
      ],
    },
    nigeria: {
      name: "Nigeria",
      region: "West Africa",
      updated: "Updated April 27, 2026",
      tagline:
        "Nigeria's current picture mixes security shocks, courtroom politics, and economic pressure from inflation and fuel costs.",
      democracyIndex: "<50",
      election: "General election — 2027",
      conflict: "Multiple armed conflicts and insurgencies",
      languages: "English, Hausa, Yoruba, Igbo",
      mix: "Cost of living, security, reform",
      risk: "Subnational conflict granularity",
      sourceNote: "Curated from Reuters reporting published between April 16 and April 22, 2026.",
      stories: [
        {
          source: "Reuters",
          time: "Apr 22",
          title: "Former security officials plead not guilty in a high-profile coup plot case",
          summary:
            "The arraignment put treason and internal-security concerns back on front pages as prosecutors pushed for a fast trial.",
          tags: ["Security", "Courts", "Politics"],
          url: "https://wsau.com/2026/04/22/six-suspected-nigerian-coup-plotters-plead-not-guilty-as-court-adjourns-trial/",
        },
        {
          source: "Reuters",
          time: "Apr 22",
          title: "Fresh attacks in the northeast kill villagers as Boko Haram violence intensifies",
          summary:
            "The attacks highlighted how insurgent violence continues to shape the national briefing well beyond Abuja politics.",
          tags: ["Insurgency", "Borno", "Security"],
          url: "https://wsau.com/2026/04/22/suspected-boko-haram-militants-kill-20-in-northeast-nigeria-attacks/",
        },
        {
          source: "Reuters",
          time: "Apr 16",
          title: "Authorities warn that flood risk is elevated across most of the country this year",
          summary:
            "Hydrology officials flagged thousands of vulnerable communities, making disaster preparedness part of the core national story mix.",
          tags: ["Floods", "Climate", "Infrastructure"],
          url: "https://wsau.com/2026/04/16/nigeria-warns-of-widespread-floods-in-2026-flags-risks-in-33-states/",
        },
      ],
    },
    india: {
      name: "India",
      region: "South Asia",
      updated: "Updated April 27, 2026",
      tagline:
        "India's recent story mix is led by growth resilience, inflation risk, and the tension between digital governance and market friction.",
      democracyIndex: "60-70",
      election: "General election expected in 2029",
      conflict: "No declared war",
      languages: "Hindi, English, regional languages",
      mix: "States, climate, trade",
      risk: "Scale and language fragmentation",
      sourceNote: "Curated from Reuters reporting published between April 17 and April 23, 2026.",
      stories: [
        {
          source: "Reuters",
          time: "Apr 23",
          title: "April PMI data points to a rebound in private-sector activity",
          summary:
            "Manufacturing and services both improved in the new fiscal year, though the backdrop still includes war-related cost pressure.",
          tags: ["PMI", "Growth", "Economy"],
          url: "https://wsau.com/2026/04/23/factory-rebound-lifts-indias-private-sector-growth-in-april-pmi-shows/",
        },
        {
          source: "Reuters",
          time: "Apr 23",
          title: "The central bank says inflation risks are rising because of supply disruptions",
          summary:
            "The RBI's latest report emphasized that external shocks and weather uncertainty could still push prices higher from here.",
          tags: ["Inflation", "RBI", "Supply chains"],
          url: "https://wsau.com/2026/04/23/indias-inflation-risks-rise-on-supply-side-disruptions-central-bank-says/",
        },
        {
          source: "Reuters",
          time: "Apr 17",
          title: "New Delhi backs away from a push to mandate the Aadhaar app on smartphones",
          summary:
            "After resistance from device makers, the government stepped back from a proposal that would have expanded state digital identity deeper into consumer hardware.",
          tags: ["Technology", "Policy", "Aadhaar"],
          url: "https://wsau.com/2026/04/17/exclusive-india-drops-proposal-to-mandate-national-id-app-aadhaar-on-smartphones-after-pushback/",
        },
      ],
    },
    japan: {
      name: "Japan",
      region: "East Asia",
      updated: "Updated April 27, 2026",
      tagline:
        "Japan's current briefing is dominated by the uneasy coexistence of strong factory demand and rising anxiety over energy and market exposure.",
      democracyIndex: "70+",
      election: "House of Councillors election expected by 2028",
      conflict: "No active war classification",
      languages: "Japanese",
      mix: "Cabinet, industry, security",
      risk: "Domestic nuance lost in translation",
      sourceNote: "Curated from Reuters reporting published between April 15 and April 27, 2026.",
      stories: [
        {
          source: "Reuters",
          time: "Apr 27",
          title: "Investors are watching whether the Middle East conflict derails Japan's stock-market run",
          summary:
            "Strong recent earnings and AI-driven enthusiasm are now being tested by worries over oil, inflation, and guidance cuts.",
          tags: ["Markets", "Earnings", "Energy"],
          url: "https://wsau.com/2026/04/26/japans-record-bull-run-under-threat-as-mideast-war-clouds-earnings-season/",
        },
        {
          source: "Reuters",
          time: "Apr 23",
          title: "Manufacturing activity posts its strongest April reading in four years",
          summary:
            "Factories boosted output partly to get ahead of possible supply shortages, even as cost pressures intensified.",
          tags: ["Manufacturing", "PMI", "Supply chain"],
          url: "https://wsau.com/2026/04/22/japans-factory-activity-expands-at-strongest-pace-in-4-years-pmi-shows/",
        },
        {
          source: "Reuters",
          time: "Apr 15",
          title: "Manufacturers' confidence posts its sharpest monthly drop in more than three years",
          summary:
            "The Reuters Tankan poll showed how quickly energy and shipping worries are feeding into business sentiment.",
          tags: ["Confidence", "Industry", "Outlook"],
          url: "https://wsau.com/2026/04/14/japan-manufacturers-confidence-dips-most-in-three-years-on-middle-east-concerns-reuters-poll/",
        },
      ],
    },
  },
  pins: [
    { id: "usa", label: "United States", x: 21, y: 34 },
    { id: "brazil", label: "Brazil", x: 31, y: 62 },
    { id: "germany", label: "Germany", x: 55, y: 29 },
    { id: "ukraine", label: "Ukraine", x: 61, y: 30 },
    { id: "nigeria", label: "Nigeria", x: 52, y: 49 },
    { id: "india", label: "India", x: 69, y: 43 },
    { id: "japan", label: "Japan", x: 83, y: 36 },
  ],
};
