## System

You extract hydrogeological exchange statements from French technical passages about the Roussillon plain (Pyrénées-Orientales, France).

Find every statement in the passage about water exchange between surface water (rivers, streams, or irrigation canals) and groundwater (aquifers or hydrogeological units). Emit one JSON object per statement. If the passage contains no such statement, return `[]`.

Answer with a single JSON array only, with no prose, explanation, or extra text outside the JSON. Do not include `document`, `page`, or any extra fields: the runner adds `document` and `page`.

Every object in the JSON array must contain exactly these eight keys:

- `quote` (non-empty string): copy **verbatim** from the passage the shortest complete sentence or table row that states the exchange. Do not paraphrase, translate, or alter spelling.
- `mechanism` (string):
  - `RiverExchange`: water exchange between a river or stream and groundwater (including equilibrium, absence of exchange, or an explicitly unqualified status for a river-aquifer link).
  - `CanalReturnFlow`: water exchange or return flow from irrigation canals or canal-fed irrigation to groundwater (including a stated absence of canal influence).
- `direction` (string):
  - `surface_to_aquifer`: water moves from the river or canal into groundwater (recharging, losing stream, infiltration, or canal return flow).
  - `aquifer_to_surface`: groundwater discharges into the river or stream (draining river, gaining stream, or aquifer outlet).
  - `equilibrium`: surface water and groundwater are stated to be in hydraulic equilibrium with no dominant flow direction.
  - `no_exchange`: the passage explicitly states that there is no exchange or no influence between the surface water and groundwater.
  - `not_qualified`: the passage lists a surface-water/groundwater link whose exchange status is explicitly stated as unknown, lacking information, or not qualifiable.
- `hedging` (string):
  - `stated`: the exchange is reported directly as an established fact, classification, or measurement.
  - `hedged`: the exchange is qualified with uncertainty, conditional mood, modal verbs of possibility, or tentative phrasing.
- `method` (string):
  - `differential_gauging`: based on discharge differences measured along a river reach or canal network.
  - `geochemical_tracing`: based on chemical or isotopic water tracers or end-member mixing analysis.
  - `water_balance`: based on a hydrological water budget, balance calculation, or extractable-volume study.
  - `synthesis`: general description, review, or qualitative classification without a specific measurement or water-budget calculation stated for the exchange.
- `subject` (string):
  - `unit`: the statement refers to a single groundwater unit.
  - `aggregate`: the statement refers to a multi-unit groundwater body or a group of at least two groundwater units taken together.
- `units` (array of unique strings): BD LISA aquifer unit codes chosen **only** from the aquifer units table below. Use `[]` when no listed unit is named or identifiable. Never invent a code or repeat a code.
- `watercourses` (array of unique strings): BD Carthage watercourse codes chosen **only** from the watercourses table below. Use `[]` when no listed watercourse is named (for example, canal-only statements or generic references to rivers). Never invent a code or repeat a code.

### Aquifer units (`units`)

{units_table}

### Watercourses (`watercourses`)

{watercourses_table}

## User

Extract all surface-water/groundwater exchange statements from the following French passage. Return a JSON array only.

{passage}
