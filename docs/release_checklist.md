# Release Checklist

Target release: HydroLite Studio v0.5.0-alpha

- [ ] Git status is clean except intentionally ignored generated outputs.
- [ ] `python -m hydrolite version` passes.
- [ ] `python -m hydrolite healthcheck` passes or reports warnings only.
- [ ] `pytest -q` passes.
- [ ] Project workflow passes:
  - [ ] `python -m hydrolite project validate projects/demo_project`
  - [ ] `python -m hydrolite project batch projects/demo_project`
  - [ ] `python -m hydrolite project compare projects/demo_project`
  - [ ] `python -m hydrolite project export projects/demo_project`
- [ ] Legacy workflow passes:
  - [ ] `python -m hydrolite validate cases/`
  - [ ] `python -m hydrolite run cases/demo_gee.yaml`
  - [ ] `python -m hydrolite batch cases/`
  - [ ] `python -m hydrolite compare output/`
- [ ] OpenHydroNet input package generation passes.
- [ ] Streamlit starts from `streamlit_app.py`.
- [ ] No secrets are tracked.
- [ ] No external OpenHydroNet repository is tracked.
- [ ] No model weights or checkpoints are tracked.
- [ ] Demo project export succeeds.
- [ ] GitHub push is completed when the worktree is clean and remote is configured.
- [ ] Tag `v0.5.0-alpha` is created.
- [ ] Suggested release assets:
  - [ ] `release/demo_project_package.zip`
  - [ ] `release/release_notes_v0.5.0-alpha.md`
  - [ ] `release/installation_guide.md`
  - [ ] `release/demo_walkthrough.md`
  - [ ] `release/known_limitations.md`
  - [ ] `release/release_manifest.json`
