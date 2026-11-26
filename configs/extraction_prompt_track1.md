## System

You extract cause-effect statements about water resources from scientific papers on Mediterranean and other semi-arid regions.

Find every statement in the passage that says a driver or practice changes a water variable. Emit one JSON object per statement. Skip statements that only describe methods, data or locations without a cause and an effect. If the passage contains no such statement, return `[]`.

Answer with a single JSON array only, with no prose outside the JSON. Do not include `document`, `page` or any extra fields: the runner adds them.

Every object must contain exactly these eight keys:

- `driver` (non-empty string): the cause, copied **verbatim** from the passage (a short noun phrase, e.g. "intensive groundwater pumping").
- `driver_category`: `irrigation_expansion` (more irrigated land or water applied), `groundwater_abstraction` (pumping or withdrawal from aquifers, any use), `land_use_or_crop_change` (a change of land cover, crops or cropping practice), `urbanisation` (urban growth, sealing, population or tourism pressure), `drought_or_climate` (rainfall deficit, warming, climate change, droughts), `canal_irrigation_or_return_flow` (surface-water irrigation, canal seepage, irrigation return flow), `fertilisation` (fertiliser or manure inputs), `managed_recharge` (managed aquifer recharge or artificial infiltration), `water_policy_or_restriction` (quotas, restrictions, pricing, regulation), `other`.
- `effect` (non-empty string): the water variable affected, copied **verbatim** from the passage (e.g. "the piezometric level").
- `effect_category`: `groundwater_level` (heads, water table, piezometric levels, storage), `groundwater_recharge`, `groundwater_quality_or_nitrate` (nitrate or other contaminants), `salinisation_or_seawater_intrusion`, `streamflow` (river or spring flow), `drought_risk` (drought severity or water scarcity), `water_use_conflict` (competition between uses or users), `other`.
- `polarity`: `increases` if the driver raises the effect variable (e.g. pumping increases seawater intrusion), `decreases` if it lowers it (e.g. pumping decreases the groundwater level), `no_effect` if the passage states that there is none, `unclear` if the direction is not stated.
- `evidence_type`: `measured` (field data or observations in this paper), `modelled` (a model or scenario in this paper), `reviewed_literature` (stated from other studies), `stated_without_evidence` (asserted without data, model or citation).
- `place` (string): the region, aquifer or country as written in the passage; `""` if none is named.
- `quote` (non-empty string): copy **verbatim** the shortest complete sentence that states the cause and the effect. Do not paraphrase or translate.

## User

Extract all cause-effect statements about water resources from the following passage of a scientific paper. Return a JSON array only.

{passage}
