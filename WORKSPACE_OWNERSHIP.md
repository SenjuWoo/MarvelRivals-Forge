# Workspace ownership

- Project root: `.` (this file's directory; one owner shared by every agent).
- Project: MarvelRivals-Forge, an agent-facing toolkit (CLI `mrforge`) for making Marvel Rivals skin mods.
- Active source (once built): `src/mrforge/` (package, knowledge data, templates), `skills/`, `tests/`, `tools.lock.json`.
- Versioning: Git on `main`, tags `vX.Y.Z`; the version lives in `src/mrforge/__init__.py`.
- Repository: GitHub `MarvelRivals-Forge` (public, MIT), created by PLAN.md T28.
- Publication intent: public GitHub repository for the forge itself. Mods made with the forge stay local until the owner publishes them.
- Read-only inputs: the installed game, the mod manager's staging and deployed `~mods` folders (except the forge's own `*-mrforge-*` deploy folders, written only by `mrforge deploy`), the third-party tool collection, supplied references.
- Forge-owned writes: this repository, `.mrforge/` (tools, caches, receipts, logs; git-ignored), `projects/` (mod projects; git-ignored).
- Machine-specific paths: `LOCAL.md` (git-ignored, never published).
- Release staging: release ZIP is built from tracked files only; mod packages contain the `.pak/.utoc/.ucas` triple only.
- Recovery: read STATE.md, then PLAN.md; keep the last known-good artifact.

Read the existing evidence and update the active-source/version fields before substantive edits. Do not create another owner or move files merely to match a template.
