# Motor Current Automated Test Campaign

Open `motor_current_campaign.sdojo` to explore SignalDojo 1.2 automated campaigns.

The example applies one conditioning/FFT workflow to eight generated recordings:

- Four normal units that pass.
- `TEST-E001_excessive_rms.csv`, which fails the 2 A RMS limit.
- `TEST-F001_abnormal_frequency.csv`, which fails the 48–52 Hz requirement.
- `TEST-Z001_noisy.csv`, which produces a warning for current variation.
- `TEST-M001_malformed.csv`, which lacks the required `current` column and demonstrates failure isolation.

The campaign publishes RMS current, dominant frequency and current standard deviation. A normal run is already selected as the reference. Completed results, checksums and compact comparison signals are embedded in the project, so the dashboard opens without recalculating unchanged files.

Use **Campaign → Campaign Setup** to inspect mappings, metadata rules, requirements, execution settings and report sections. Use **Campaign → Run Campaign** to verify result reuse, **Compare Selected Runs** for overlays/differences, and **Generate Campaign Report** to create PDF, Excel and CSV outputs.

Run `python generate_example.py` from the repository root to regenerate the recordings and project deterministically.
