# Third-party notices

The generated files under `bundle/` include these pinned direct dependencies:

| Package | Version | License |
|---|---:|---|
| MapLibre GL JS | 5.12.0 | BSD-3-Clause |
| `@deck.gl/core` | 9.3.7 | MIT |
| `@deck.gl/layers` | 9.3.7 | MIT |
| `@deck.gl/mapbox` | 9.3.7 | MIT |
| `@deck.gl/mesh-layers` | 9.3.7 | MIT |

The build-only dependency `esbuild` 0.21.5 is MIT licensed. Exact transitive versions and resolved package
URLs are recorded in `package-lock.json`. MapLibre's retained license comment is emitted to
`bundle/map.js.LEGAL.txt`; full license texts are available in each npm package and its linked upstream
repository.

The build does not fetch or embed online map tiles, fonts, access tokens, or CDN assets.

The offline low-poly truck under `ui/assets/models/truck/` is by Arifido._ and distributed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). See the model-local README for source and
checksums.
