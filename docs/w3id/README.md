# Requesting the w3id.org redirect for the ontology (for Assil, about 5 minutes)

**Status: postponed (Assil, 2026-11-16: "will publish the stuff later").** The request waits until the
ontology is published. Nothing in the project breaks meanwhile: the IRIs stay as they are
(provisional), our scripts read the local files through `ontology/catalog-v001.xml`, and the OOPS!
scan sends the merged network without its `owl:imports` (`src/kg/oops_scan.py`). Send it a few weeks
before the paper is submitted, so that the addresses work when reviewers click them (a merge can take
days). The files and the steps below stay ready.

**Why.** Every IRI of the ontology starts with `https://w3id.org/lulcw` (CLAUDE.md §3: a permanent
address). Today those addresses lead nowhere, so a tool that loads the ontology and follows its
`owl:imports` fails: the OOPS! scan of 2026-11-16 did, until the imports were removed by hand. w3id.org
is a free service that redirects permanent addresses to wherever the files live; adding one is a pull
request to its GitHub repository. Only you can open it (it is your GitHub account and your name as
maintainer).

**What is ready.** `docs/w3id/lulcw/.htaccess` (17 redirects: the 15 addresses of
`ontology/catalog-v001.xml`, the shapes and the rules, each to its file in this public repository,
checked 2026-11-16: every target exists and GitHub serves it) and `docs/w3id/lulcw/README.md` (what the
addresses are, the maintainer).

## Steps

1. Open https://github.com/perma-id/w3id.org and click **Fork** (top right).
2. In your fork, click **Add file → Upload files**, and upload the folder `docs/w3id/lulcw/` from this
   repository so that it lands as `lulcw/.htaccess` and `lulcw/README.md` at the top of the fork.
   (The `.htaccess` file is hidden in most file browsers: in the upload dialog, show hidden files, or
   create the file in GitHub with **Add file → Create new file**, name `lulcw/.htaccess`, and paste its
   content.)
3. Commit to a new branch and open a **pull request** to `perma-id/w3id.org`, for example:
   - title: `Add lulcw: LULC-Water ontology network`
   - text: `Permanent identifiers for the LULC-Water network of ontologies (land use, land cover and
     groundwater; SAVE Water project, PRIMA), developed for a Master's thesis at ISAMM, Université de la
     Manouba. Redirects to the ontology files in https://github.com/assil-bouzaine/Master_2026
     (CC BY 4.0). Maintainer: @assil-bouzaine.`
4. The w3id maintainers merge such requests, usually within days. Then `curl -I https://w3id.org/lulcw`
   should answer `302` with the address of `lulcw.ttl`. Tell Claude: the OOPS! scan can then keep the
   imports, and the docs can drop "provisional namespace".

## Notes

- The redirects point to the `main` branch, so the addresses always give the newest files. The version
  IRIs (`https://w3id.org/lulcw/0.7.1`) are not redirected yet: that needs a git tag per ontology version
  (for example `lulcw-0.7.1`) and one more rule; it can come with the analysis plan's tag before Phase 4.
- `raw.githubusercontent.com` serves the files as `text/plain`; RDF tools that read the `.ttl` extension
  load them. If a tool insists on the Turtle media type, the folder can be published with GitHub Pages
  and the target address changed in one line of the `.htaccess`.
- If the ontology later moves to a repository of its own, only the `.htaccess` changes (another pull
  request); the IRIs stay the same, which is the point of w3id.
- The repository is public (checked 2026-11-16), which the redirect needs. Whether project outputs may
  be public before the paper is point 17 of `docs/gate3_decisions.md`.
