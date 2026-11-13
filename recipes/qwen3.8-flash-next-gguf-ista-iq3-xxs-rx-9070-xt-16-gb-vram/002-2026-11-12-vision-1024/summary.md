# 002 · 2026-11-12 — CPU vision with 1,024 image tokens

## Workload

Repeated the vision check on the same `amdgpu_top` screenshot used in the [initial results](../001-2026-11-12-initial-checks/summary.md), after restarting Strata with `vision.min_tokens: 1024` and `vision.max_tokens: 1024`. The original configuration used the CPU default maximum of 300 image tokens and no explicit minimum.

The prompt remained “Describe the image and read its visible text.” The request used temperature 0, thinking disabled, and a 256-output-token cap. MTP, CPU vision, and the 131,072-token context allocation remained enabled.

## Results

| Metric | Initial 300-token maximum | 1,024-token minimum and maximum |
|---|---:|---:|
| Total prompt tokens | 309 | 1,023 |
| Generated tokens | 256 | 256 |
| Reused prompt tokens | 0 | 0 |
| End-to-end request time | 4.75 s | 9.72 s |
| Engine prefill time | 0.4911 s | 0.8247 s |
| Prefill speed | 629.2 tok/s | 1,240.5 tok/s |
| Engine generation time | 2.8812 s | 2.4277 s |
| Generation speed | 88.9 tok/s | 105.4 tok/s |
| Accepted / proposed drafts | 135 / 209 (64.6%) | 163 / 219 (74.4%) |
| Finish reason | length | length |

Rates and engine times are from the API responses. Prompt counts include text and image representation; they are not a direct measurement of image tokens alone. Draft acceptance is accepted proposals divided by proposed drafts.

End-to-end time increased by about 4.98 seconds. Time outside reported prefill and generation increased from approximately 1.37 to 6.47 seconds. This is consistent with increased CPU image-encoding work, but includes other request overhead; separate encoder timing was not recorded.

## Observations

The follow-up correctly read the application version, RX 9070 XT model, `GFX1201` architecture, memory specifications, `GRBM` heading, and the visible Graphics Pipe value. The original response recognized the application but included incorrect panel names such as “GPU12” and “IdleGPU”.

Both responses reached the output cap before completing the broad description. The follow-up supports improved reading of several visible labels on this screenshot; it does not establish accuracy for every panel or a general performance gain. A focused transcription prompt can compare additional fields within the same output allowance.

---

[Recipe](../recipe.md) · [Configuration](configuration.md) · [Build and run](../setup.md) · [Profile YAML](profile.yaml)
