# Dynamics analyses

Read this file for modal, harmonic response, random vibration (PSD), or
transient structural analysis.

## Modal

```python
modal = model.AddModalAnalysis()
modal.MaximumModesToFind = 10
modal.LimitSearchToRange = True
modal.RangeMinimum = 0.0    # Hz
modal.RangeMaximum = 2000.0  # Hz
modal.Solve()

freqs = modal.Solution.AddTotalDeformation()  # per-mode deformation
```

Report mode count found versus requested, the frequency range actually
searched, and mass participation factors if available — a mode search that
returns fewer modes than requested inside the stated range is worth flagging,
not silently accepting.

## Harmonic response

Requires an upstream modal solve (linked analysis system) unless using full
method:

```python
harmonic = model.AddHarmonicResponseAnalysis()
harmonic.RangeMinimum = 0.0     # Hz
harmonic.RangeMaximum = 500.0   # Hz
harmonic.SolutionIntervals = 200
harmonic.SolutionMethod = "ModeSuperposition"  # or "Full"
```

State explicitly: forcing frequency sweep range and resolution, damping input
source (constant damping ratio, modal damping, or material damping), and
which upstream modal solve it links to (mode count/range used there bounds
what mode-superposition harmonic can represent).

## Random vibration (PSD)

Requires an upstream modal solve. The PSD input is a frequency/amplitude
table, applied as a base excitation (most common) or an applied-force PSD:

```python
random_vib = model.AddRandomVibrationAnalysis()
psd_load = random_vib.AddPSDBaseExcitation()
# table shape: paired (frequency_Hz, PSD_amplitude) rows
psd_load.Frequencies = [1, 10, 100, 1000]
psd_load.Amplitudes = [0.001, 0.01, 0.01, 0.001]  # e.g. g^2/Hz — confirm units
```

Always confirm and report the PSD amplitude units (acceleration²/Hz vs
displacement²/Hz, etc.) — this is a common silent misconfiguration.

## Transient structural

```python
transient = model.AddTransientStructuralAnalysis()
transient.AutomaticTimeStepping = "On"
transient.InitialTimeStep = 1e-4   # s
transient.MinimumTimeStep = 1e-6
transient.MaximumTimeStep = 1e-3
transient.EndTime = 0.1
```

State the initial condition source (zero, or carried over from a prior static
step), whether nonlinearity (large deflection, nonlinear material) is on, and
the actual time-step behavior used versus requested if auto-stepping adjusted
it.

## Linked analysis systems

Dynamic analyses that build on a static or modal solve (harmonic via mode
superposition, random vibration, prestressed modal) reference the upstream
system explicitly in the object model — verify the link exists and points at
a solved, current upstream analysis before trusting a downstream solve.
