# SignalDojo Quick Start

1. Launch SignalDojo and choose **File → Open Example → Noise Filter Example**, or start a blank project.
2. Drag **Import Data** from **Inputs & Outputs** onto the canvas.
3. Select the block, choose a CSV file, and set **Time column** and **Signal columns**. Use **Workflow → Preview Selected Import** to inspect the first rows.
4. Drag **Low-Pass Filter** onto the canvas. Connect Import output 1 to the filter input.
5. Select the filter and set a cut-off below the Nyquist frequency. Use **Workflow → Preview Selected Filter Response**.
6. Add a **Scope**. Connect the raw signal to Scope input 1 and the filtered signal to Scope input 2.
7. Press **F5**. The scope opens in a dock. Move cursors A and B, drag the measurement region, zoom and pan.
8. Add **Export Data**, connect the filtered signal, choose a `.csv` path and run again.
9. Save with **Ctrl+S** as a `.sdojo` project.
10. Reopen the project and press **F5** to reproduce the result.

SignalDojo never silently resamples or truncates incompatible signals. Insert **Resample** or **Synchronise Signals** explicitly when time axes differ.

## Test campaign quick start

1. Add **Publish Metric** after the RMS and dominant-frequency outputs of a workflow.
2. Choose **Campaign → New Test Campaign**.
3. Select a folder, extensions and recursive scanning; preview the discovered files.
4. Map **Run file** to the workflow's Import Data block.
5. Select the published metrics and configure limits.
6. Save the `.sdojo` project and press **Ctrl+Shift+F5**.
7. Use the dashboard to filter failures, set a reference and compare selected runs.
8. Choose **Generate Campaign Report** for PDF, Excel and CSV.

The complete motor-current procedure is in `TEST_CAMPAIGNS.md` and `examples/motor_current_campaign/`.
