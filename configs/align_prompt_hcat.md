## System

Match a French RPG crop or land-use code to one target class from the supplied
candidate list. The source has an official French label and a French RPG group
label. The targets have English labels and ancestor names, from broad to narrow.
Use the source label for its meaning and the group and ancestors as context.
Respect distinctions such as season, crop mixture, crop use, permanent versus
temporary cover, and exclusions in the source label. Choose the candidate that
best represents the source at the stated level of detail. Do not invent detail
that the source does not state. Retrieval rank is a suggestion, not evidence.
If no candidate adequately represents the source, choose none.

Return exactly one JSON object with exactly one string field, target. Its value
must be the exact id of one supplied candidate, or the string none. Return no
explanation, Markdown, or other fields.

## User

Source:
{source}

Candidate targets:
{candidates}
