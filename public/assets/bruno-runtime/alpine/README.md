# Alpine reference assets

默认场景已加载 Eiger 压缩高程模型及 Snow 02 的颜色细节、法线。最终颜色、雪线、雾和昼夜变化由 Bruno runtime 的 `MeshDefaultMaterial` / TSL 链路控制；其余扫描素材仍为候选。

## 当前目录

- `mountainside-2k/`：Poly Haven Mountainside 的 2K glTF 版本，包含高精度崖壁几何、法线、颜色和 ARM 贴图。它用于山体细节参考和后续局部断崖，不直接替换整套远景山脉。
- `snow-02-2k/`：Poly Haven Snow 02 的 2K diffuse、normal、roughness、displacement 贴图。
- `ambientcg-snow006/`：ambientCG Snow 006 的 1K 多格式材质包，作为雪面法线、粗糙度和位移的第二套参考。
- `dem/`：从 AWS elevation-tiles-prod/skadi 的 HGT 高程分发生成 Matterhorn 和 Eiger 两个候选，各包含 97,410 / 24,130 三角形两档。运行时使用 `*-compressed.glb`，原始 GLB 用于复核。

## 许可证

- Poly Haven 资产：CC0，来源页分别为 [Mountainside](https://polyhaven.com/a/mountainside) 和 [Snow 02](https://polyhaven.com/a/snow_02)。
- ambientCG Snow 006：CC0，来源页为 [Snow 006](https://ambientcg.com/view?id=Snow006)，完整许可见 [ambientCG License](https://docs.ambientcg.com/license)。

## 使用边界

- 不把原始写实 diffuse 直接当成场景最终颜色；使用 Bruno 调色板和 TSL 三平面/坡度材质重映射。
- 不把这个目录里的崖壁模型当作低模云或主山脉；主山脉候选来自 `3D/alpine-source/dem/srtm/` 的真实高程数据。
- LOD、Draco、材质重绑和尺寸校准已经接入；JPEG 启用 mipmap，KTX2 编码仍是后续优化项。
- `dem/*.json` 保留每个候选的经纬度范围、采样网格和三角形数量，便于重新生成或替换区域。
