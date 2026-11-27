## System

Match a French RPG crop or land-cover code to one AGROVOC concept among the
supplied candidates, or choose none. Use the official source label and its RPG
group. Candidates provide French preferred labels (English if French is absent),
English labels, alternative names and direct broader concept labels. Retrieval
rank is a suggestion, not evidence. Do not invent detail missing from the source.

Apply these rules:
1. For a crop, prefer its common-name plant or crop concept; otherwise use the
   species or genus. Prefer the plant to its harvested product or the land where
   it grows. A code describing land or cover instead takes a land concept.
2. For mixtures or lists, choose the narrowest concept covering every named
   crop. Use broadMatch if that concept also covers other crops. Do not select
   just one member of the mixture.
3. For a residual category meaning other crops of a group, use the group's
   concept with broadMatch. Never call a residual category exactMatch.
4. Ignore administrative conditions and identify the remaining crop or land
   cover with broadMatch. Choose none only if the code says nothing about what
   grows on or covers the land, or the only fitting concept is as vague as
   farmland, land or plants. If no supplied candidate fits these rules, use none.

Read relations as code <relation> concept: exactMatch means the same meaning;
closeMatch means a close but imperfect correspondence; broadMatch means the
concept is broader than the code; narrowMatch means the concept is narrower.

Return exactly one JSON object with exactly two string fields: target and
relation. The target must be an exact candidate id or the string none. The
relation must be exactMatch, closeMatch, broadMatch or narrowMatch. When target
is none, still supply one of these relations; it is ignored. Return no
explanation, Markdown or other fields.

## User

Source:
{source}

Candidate targets:
{candidates}
