# Fire Pipe Velocity Checker

A Streamlit app for checking velocities in critical fire sprinkler pipes:

- **Main ICV** (feeder)
- **Header** pipe
- **Ranger** pipe

The tool flags any pipe exceeding **6 m/s** and recommends the minimum internal
bore required. Results can be exported to PDF for record-keeping.

## How it works

Flow basis:

```
Q_per_head = density (mm/min) × area_per_head (m²)   [L/min]
Q_ranger   = Q_per_head × N_ranger
Q_header   = Q_per_head × N_header
Q_ICV      = Q_per_head × N_total + Q_hydrant
```

Velocity:

```
v (m/s) = Q (L/min) / 60 000  ÷  (π/4 × (D_mm/1000)²)
```

## Run locally

```bash
pip install -r requirements.txt
streamlit run fire_pipe_v_app.py
```

## Deploy on Streamlit Community Cloud

1. Push this repo to GitHub (public).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Click **New app**, pick this repo, branch `main`, main file `fire_pipe_v_app.py`.
4. Click **Deploy**.

## Notes

This is a critical-pipe velocity check only. It is **not** a substitute for a
full hydraulic calculation.

---

© ViKO Consulting Engineers
