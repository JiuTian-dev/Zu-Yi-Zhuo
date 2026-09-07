# 远景雪山素材准备记录

日期：2026-09-07

## 本次已准备

### 运行时候选素材

放在 `public/assets/bruno-runtime/alpine/`：

- `mountainside-2k/`：Poly Haven Mountainside 2K glTF、几何 buffer 和三张贴图。`mountainside_2k.gltf` 已确认引用 `mountainside.bin` 和 `textures/` 下的纹理。
- `snow-02-2k/`：Poly Haven Snow 02 的 2K diffuse、GL normal、roughness、displacement。
- `ambientcg-snow006/`：ambientCG Snow 006 的 1K Color、NormalGL、Roughness、Displacement、AO 以及原始材质描述文件。

运行时现已使用 Eiger 高程山脊及 Snow 02 颜色细节/法线，重绑 Bruno 材质。Mountainside 和 Snow 006 保留为候选，不会额外下载到当前场景。

### 离线地形源

放在被 `.gitignore` 忽略的 `3D/alpine-source/`：

- `dem/srtm/N45E007.hgt.gz`：Matterhorn 附近。
- `dem/srtm/N46E007.hgt.gz`：Eiger–Mönch–Jungfrau 西侧。
- `dem/srtm/N46E008.hgt.gz`：Eiger–Mönch–Jungfrau 东侧。
- `materials/Snow006_1K-JPG.zip`：ambientCG 原始下载包，便于之后复核来源和重新处理。

高程源实际下载自 AWS `elevation-tiles-prod/skadi` 的 HGT 分发，不能将其冒称为直接下载的 NASADEM 产品。原始高程不进入浏览器；运行时只加载处理后的 GLB。

### 已生成的第一版灰模

已使用 `scripts/build-alpine-dem.mjs` 生成：

- `matterhorn-ridge.glb`、`eiger-ridge.glb`：各 97,410 三角形。
- `*-lod.glb`：各 24,130 三角形。
- `*-compressed.glb`：Draco 压缩，16 位位置、12 位法线；Eiger 主档约 246 KB、远档约 71 KB，运行时只请求这两个档位。

已修正生成器的逐点高程基准漂移、反向三角形和缺失位置边界；山脚按裁切边界平滑沉入地面，法线从最终几何重新计算。默认使用 Eiger，`?alpine=matterhorn` 可比较另一个山脊，`?alpine=legacy` 可比较旧占位山。

## 来源和许可

- 高程实际分发地址：`https://s3.amazonaws.com/elevation-tiles-prod/skadi/N46/N46E007.hgt.gz`，另外两块采用同样目录规则。保留分发来源，不将复合高程分发等同于 NASA 原始产品。
- [Poly Haven Mountainside](https://polyhaven.com/a/mountainside)：CC0。
- [Poly Haven Snow 02](https://polyhaven.com/a/snow_02)：CC0。
- [ambientCG Snow 006](https://ambientcg.com/view?id=Snow006)：CC0；[许可说明](https://docs.ambientcg.com/license)。

## 复现与验收

1. `node scripts/build-alpine-dem.mjs` 生成两个候选与 LOD。
2. 对每个 GLB 执行 `npx --yes @gltf-transform/cli@4.5.0 draco <input.glb> <name-compressed.glb> --quantize-position 16 --quantize-normal 12`。
3. 启动 Vite 后执行 `npx --yes --package @playwright/cli playwright-cli -s=alpine open http://127.0.0.1:5174/`，再执行 `npx --yes --package @playwright/cli playwright-cli -s=alpine run-code --filename scripts/review-alpine-browser.js`。

本轮材质采用带 mipmap 的 JPEG，不宣称已完成 KTX2。当前没有可用的 toktx 编码器；KTX2 作为后续显存/传输优化，画面正确性与之无关。

云采用 48³ 单通道三维密度纹理（约 108 KB 显存）和局部光线步进；桌面 40 步、移动端 20 步，按不透明深度裁切。山脚高度雾融入山体材质，复用现有昼夜光照和单 Renderer。没有新增 VDB 解析依赖。
