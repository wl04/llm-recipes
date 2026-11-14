# Vision check image

The shared [amdgpu_top screenshot](../assets/checks/amdgpu-top.png) provides a fixed input for screenshot-reading checks. The Strata vision helper uses it by default; `--image` selects another PNG or JPEG.

Useful details to compare with the answer:

| Field | Visible value |
|---|---|
| Application | amdgpu_top v0.11.5 |
| GPU | AMD Radeon RX 9070 XT |
| Architecture | GFX1201 |
| Device VRAM | 15,737 / 16,304 MiB |
| Device GTT | 116 / 30,328 MiB |
| Strata process | strata-host |
| Process VRAM | 15,419 M, as displayed |
| Panel headings | GRBM, GRBM2, Memory Usage, Activity, fdinfo, Sensors, GPU Metrics v1.3 |

Review the response against the image. The check requests a description and visible text, with a 256-token output cap; it may finish before listing every detail. Record the image used, image-token settings, and output cap when comparing results. The displayed memory values belong to the captured screenshot, not to the server currently processing it.

The Unsloth initial result used a different image of `gpu-switcher`; this shared screenshot is the default for subsequent checks.

---

[All recipes](../README.md) · [Strata runtime](runtimes/strata.md) · [Authoring](authoring.md)
